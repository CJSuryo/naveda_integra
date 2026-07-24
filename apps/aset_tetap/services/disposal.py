"""Aset Tetap services — journal generation for asset disposal."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.master_data.models import Akun

from ..models import AssetDisposal
from .common import _next_journal_number, _resolve_asset_account


def process_asset_disposal(disposal: AssetDisposal) -> JurnalHeader:
    """Proses pelepasan aset: hitung snapshot, kurangi aset, buat jurnal pelepasan.

    Jurnal:
        Kredit Aset (perolehan dilepas)
        Debit  Akumulasi Penyusutan (akumulasi dilepas)
        Debit  Kas/Piutang (harga jual) -- hanya jenis 'jual' & harga_jual > 0
        Laba (kredit) / Rugi (debit) pada akun_laba_rugi -- selisih
    """
    quantize = Decimal('0.0001')
    aset = disposal.aset
    jenis = disposal.jenis
    quantity = disposal.quantity

    # Normalisasi non-jual
    if jenis != 'jual':
        disposal.harga_jual = Decimal('0')
        disposal.akun_kas = None
    harga_jual = disposal.harga_jual or Decimal('0')

    # Validasi
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas dan tidak dapat dilepas lagi.')
    if quantity is None or quantity <= 0:
        raise ValueError('Quantity pelepasan harus lebih dari 0.')
    if quantity > aset.quantity:
        raise ValueError(
            f'Quantity pelepasan ({quantity}) melebihi sisa quantity aset ({aset.quantity}).'
        )
    if harga_jual < 0:
        raise ValueError('Harga jual tidak boleh negatif.')
    if jenis == 'jual' and harga_jual > 0 and not disposal.akun_kas:
        raise ValueError('Akun Kas/Piutang wajib dipilih untuk pelepasan jenis jual.')
    if not disposal.akun_laba_rugi_id:
        raise ValueError('Akun Laba/Rugi Pelepasan wajib dipilih.')

    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')
    akumulasi_akun = Akun.objects.filter(kode_akun__startswith='1.2.7').first()
    if not akumulasi_akun:
        raise ValueError('Akun Akumulasi Penyusutan (1.2.7.xx) belum tersedia di Chart of Accounts.')

    # Snapshot pro-rata
    fraksi = quantity / aset.quantity
    perolehan_dilepas = (quantity * aset.harga_perolehan).quantize(quantize)
    akumulasi_dilepas = (aset.akumulasi_penyusutan * fraksi).quantize(quantize)
    residu_dilepas = (aset.nilai_residu * fraksi).quantize(quantize)
    nilai_buku_dilepas = perolehan_dilepas - akumulasi_dilepas
    laba_rugi = (harga_jual - nilai_buku_dilepas).quantize(quantize)

    # Baris jurnal: (akun, debit, kredit)
    lines = [
        (akun_aset, Decimal('0'), perolehan_dilepas),        # Kredit aset
        (akumulasi_akun, akumulasi_dilepas, Decimal('0')),   # Debit akumulasi
    ]
    if jenis == 'jual' and harga_jual > 0:
        lines.append((disposal.akun_kas, harga_jual, Decimal('0')))   # Debit kas
    if laba_rugi > 0:
        lines.append((disposal.akun_laba_rugi, Decimal('0'), laba_rugi))   # Kredit laba
    elif laba_rugi < 0:
        lines.append((disposal.akun_laba_rugi, -laba_rugi, Decimal('0')))  # Debit rugi

    total_debit = sum((d for _, d, _ in lines), Decimal('0'))
    total_kredit = sum((k for _, _, k in lines), Decimal('0'))
    if total_debit != total_kredit:
        raise ValueError(
            f'Jurnal pelepasan tidak balance: debit {total_debit} != kredit {total_kredit}.'
        )

    with transaction.atomic():
        disposal.perolehan_dilepas = perolehan_dilepas
        disposal.akumulasi_dilepas = akumulasi_dilepas
        disposal.residu_dilepas = residu_dilepas
        disposal.laba_rugi = laba_rugi

        aset.quantity -= quantity
        aset.akumulasi_penyusutan -= akumulasi_dilepas
        aset.nilai_residu -= residu_dilepas
        if aset.quantity <= 0:
            aset.status = 'dilepas'
        aset.save()

        header = JurnalHeader.objects.create(
            tanggal=disposal.tanggal,
            nomor_transaksi=_next_journal_number('TRX-DSP-'),
            uraian_transaksi=f'Pelepasan {aset.aset_number} ({jenis}) — {aset.item.nama}',
            entitas_bisnis=aset.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
            for akun, d, k in lines
        ])
        disposal.jurnal_header = header
        disposal.save()

    return header


def reverse_asset_disposal(disposal: AssetDisposal, request=None) -> None:
    """Batalkan pelepasan: hapus jurnal (dengan log), pulihkan state aset dari snapshot,
    lalu hapus record disposal. Boleh dilakukan kapan saja (tidak harus yang terakhir).
    """
    from apps.jurnal.utils import log_jurnal_terhapus

    aset = disposal.aset
    with transaction.atomic():
        header = disposal.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()

        aset.quantity += disposal.quantity
        aset.akumulasi_penyusutan += disposal.akumulasi_dilepas
        aset.nilai_residu += disposal.residu_dilepas
        aset.status = 'aktif'
        aset.save()

        disposal.delete()
