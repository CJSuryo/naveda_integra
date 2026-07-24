"""Aset Tetap services — journal generation for asset revaluation."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from ..models import AssetRevaluation
from .common import _next_journal_number, _resolve_asset_account


def default_metode_revaluasi(entitas_bisnis) -> str:
    """Default metode revaluasi berdasar SAK EB. Semua SAK -> eliminasi (dapat diubah user)."""
    return 'eliminasi'


def revaluation_warning(entitas_bisnis) -> str:
    """Peringatan bila EB memakai SAK EMKM (cost model). '' bila tidak perlu."""
    if getattr(entitas_bisnis, 'standar_akuntansi', '') == 'sak_emkm':
        return ('SAK EMKM menggunakan model biaya (cost model); revaluasi umumnya tidak '
                'diperkenankan. Lanjutkan hanya bila Anda yakin.')
    return ''


def process_asset_revaluation(rev: 'AssetRevaluation') -> JurnalHeader:
    quantize = Decimal('0.0001')
    aset = rev.aset
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas — revaluasi tidak dapat diproses.')
    if rev.nilai_wajar_baru < 0:
        raise ValueError('Nilai wajar baru tidak boleh negatif.')

    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')

    hp_lama = aset.total_value
    akum_lama = aset.akumulasi_penyusutan
    nb_lama = aset.nilai_buku
    selisih = (rev.nilai_wajar_baru - nb_lama).quantize(quantize)

    lines = []  # (akun, debit, kredit)
    if rev.metode_revaluasi == 'eliminasi':
        # 1) Eliminasi akumulasi lawan aset
        if akum_lama > 0:
            lines.append((rev.akun_akumulasi, akum_lama, Decimal('0')))  # D Akumulasi
            lines.append((akun_aset, Decimal('0'), akum_lama))           # K Aset
        # 2) Setel ke nilai wajar
        if selisih > 0:
            lines.append((akun_aset, selisih, Decimal('0')))                       # D Aset
            lines.append((rev.akun_surplus_revaluasi, Decimal('0'), selisih))      # K Surplus
        elif selisih < 0:
            lines.append((rev.akun_rugi_revaluasi, -selisih, Decimal('0')))        # D Rugi
            lines.append((akun_aset, Decimal('0'), -selisih))                      # K Aset
        perolehan_baru = rev.nilai_wajar_baru
        akumulasi_baru = Decimal('0')
    else:  # proporsional
        if nb_lama <= 0:
            raise ValueError('Nilai buku lama harus > 0 untuk metode proporsional.')
        rasio = rev.nilai_wajar_baru / nb_lama
        perolehan_baru = (hp_lama * rasio).quantize(quantize)
        akumulasi_baru = (akum_lama * rasio).quantize(quantize)
        d_aset = (perolehan_baru - hp_lama).quantize(quantize)
        d_akum = (akumulasi_baru - akum_lama).quantize(quantize)
        # net efek ke ekuitas = selisih
        if d_aset > 0:
            lines.append((akun_aset, d_aset, Decimal('0')))
        elif d_aset < 0:
            lines.append((akun_aset, Decimal('0'), -d_aset))
        if d_akum > 0:
            lines.append((rev.akun_akumulasi, Decimal('0'), d_akum))
        elif d_akum < 0:
            lines.append((rev.akun_akumulasi, -d_akum, Decimal('0')))
        if selisih > 0:
            lines.append((rev.akun_surplus_revaluasi, Decimal('0'), selisih))
        elif selisih < 0:
            lines.append((rev.akun_rugi_revaluasi, -selisih, Decimal('0')))

    if not lines:
        raise ValueError('Tidak ada perubahan nilai; revaluasi tidak diperlukan.')

    total_debit = sum((d for _, d, _ in lines), Decimal('0'))
    total_kredit = sum((k for _, _, k in lines), Decimal('0'))
    if total_debit != total_kredit:
        raise ValueError(f'Jurnal revaluasi tidak balance: debit {total_debit} != kredit {total_kredit}.')

    with transaction.atomic():
        rev.perolehan_lama = hp_lama
        rev.akumulasi_lama = akum_lama
        rev.nilai_buku_lama = nb_lama
        rev.perolehan_baru = perolehan_baru
        rev.akumulasi_baru = akumulasi_baru
        rev.selisih = selisih

        # total_value = quantity * harga_perolehan -> setel harga_perolehan per unit
        aset.harga_perolehan = (perolehan_baru / aset.quantity).quantize(quantize)
        aset.akumulasi_penyusutan = akumulasi_baru
        aset.save()

        header = JurnalHeader.objects.create(
            tanggal=rev.tanggal, nomor_transaksi=_next_journal_number('TRX-REV-'),
            uraian_transaksi=f'Revaluasi {aset.aset_number} ({rev.get_metode_revaluasi_display()})',
            entitas_bisnis=aset.entitas_bisnis, is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
            for akun, d, k in lines
        ])
        rev.jurnal_header = header
        rev.save()
    return header


def reverse_asset_revaluation(rev: 'AssetRevaluation', request=None) -> None:
    from apps.jurnal.utils import log_jurnal_terhapus
    quantize = Decimal('0.0001')
    aset = rev.aset
    with transaction.atomic():
        header = rev.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()
        aset.harga_perolehan = (rev.perolehan_lama / aset.quantity).quantize(quantize)
        aset.akumulasi_penyusutan = rev.akumulasi_lama
        aset.save()
        rev.delete()
