"""Aset Tetap services — journal generation for asset transfer (intra-EB & antar-EB)."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from ..models import AssetTransfer
from .common import _next_journal_number, _resolve_asset_account


def process_asset_transfer(trf: 'AssetTransfer') -> 'JurnalHeader | None':
    """Intra-EB: update lokasi/dept/PIC (tanpa jurnal).
    Antar-EB: dua jurnal seimbang (EB asal & tujuan) via akun antar-entitas, carry-over HP & akumulasi.
    """
    aset = trf.aset
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas — transfer tidak dapat diproses.')

    # Snapshot asal
    trf.lokasi_asal = aset.lokasi_aset
    trf.dept_asal = aset.departemen
    trf.pic_lama = aset.pic

    if trf.jenis == 'intra_eb':
        with transaction.atomic():
            if trf.lokasi_tujuan_id:
                aset.lokasi_aset = trf.lokasi_tujuan
            if trf.dept_tujuan_id:
                aset.departemen = trf.dept_tujuan
            if trf.pic_baru:
                aset.pic = trf.pic_baru
            aset.save()
            trf.save()
        return None

    # antar_eb — divalidasi & dijurnal di fungsi terpisah
    return _process_transfer_antar_eb(trf)


def _process_transfer_antar_eb(trf: 'AssetTransfer') -> JurnalHeader:
    aset = trf.aset
    if not trf.eb_tujuan_id or trf.eb_tujuan_id == aset.entitas_bisnis_id:
        raise ValueError('EB tujuan harus berbeda dari EB asal.')
    if not trf.akun_antar_entitas_id:
        raise ValueError('Akun Antar-Entitas wajib dipilih untuk transfer antar entitas.')
    if not trf.akun_akumulasi_id:
        raise ValueError('Akun Akumulasi Penyusutan wajib dipilih.')
    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')

    hp = aset.total_value
    akum = aset.akumulasi_penyusutan
    nilai_buku = aset.nilai_buku
    if nilai_buku < 0:
        raise ValueError(
            f'Nilai buku aset negatif ({nilai_buku:,.0f}) — akumulasi penyusutan '
            f'({akum:,.0f}) melebihi harga perolehan ({hp:,.0f}). Transfer tidak dapat diproses.'
        )
    eb_asal = aset.entitas_bisnis

    with transaction.atomic():
        trf.eb_asal = eb_asal
        trf.perolehan = hp
        trf.akumulasi = akum

        # Jurnal EB asal: K Aset (HP), D Akumulasi (akum), D antar-entitas (nilai buku)
        h_asal = JurnalHeader.objects.create(
            tanggal=trf.tanggal, nomor_transaksi=_next_journal_number('TRX-TRF-'),
            uraian_transaksi=f'Transfer keluar {aset.aset_number} ke {trf.eb_tujuan.nama}',
            entitas_bisnis=eb_asal, is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=h_asal, akun=akun_aset, debit=Decimal('0'), kredit=hp),
            JurnalDetail(jurnal_header=h_asal, akun=trf.akun_akumulasi, debit=akum, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=h_asal, akun=trf.akun_antar_entitas, debit=nilai_buku, kredit=Decimal('0')),
        ])

        # Jurnal EB tujuan: D Aset (HP), K Akumulasi (akum), K antar-entitas (nilai buku)
        h_tujuan = JurnalHeader.objects.create(
            tanggal=trf.tanggal, nomor_transaksi=_next_journal_number('TRX-TRF-'),
            uraian_transaksi=f'Transfer masuk {aset.aset_number} dari {eb_asal.nama}',
            entitas_bisnis=trf.eb_tujuan, is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=h_tujuan, akun=akun_aset, debit=hp, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=h_tujuan, akun=trf.akun_akumulasi, debit=Decimal('0'), kredit=akum),
            JurnalDetail(jurnal_header=h_tujuan, akun=trf.akun_antar_entitas, debit=Decimal('0'), kredit=nilai_buku),
        ])

        # Pindahkan aset ke EB tujuan + lokasi/dept/PIC bila diisi
        aset.entitas_bisnis = trf.eb_tujuan
        if trf.lokasi_tujuan_id:
            aset.lokasi_aset = trf.lokasi_tujuan
        if trf.dept_tujuan_id:
            aset.departemen = trf.dept_tujuan
        if trf.pic_baru:
            aset.pic = trf.pic_baru
        aset.save()

        trf.jurnal_header_asal = h_asal
        trf.jurnal_header_tujuan = h_tujuan
        trf.save()
    return h_asal


def reverse_asset_transfer(trf: 'AssetTransfer', request=None) -> None:
    """Batalkan transfer. Antar-EB: hapus kedua jurnal & pulihkan EB/lokasi/dept/PIC. Intra-EB: pulihkan lokasi/dept/PIC."""
    from apps.jurnal.utils import log_jurnal_terhapus
    aset = trf.aset
    with transaction.atomic():
        for header in (trf.jurnal_header_asal, trf.jurnal_header_tujuan):
            if header:
                log_jurnal_terhapus(header, 'aset_tetap', request)
                header.details.all().delete()
                header.delete()
        if trf.jenis == 'antar_eb' and trf.eb_asal_id:
            aset.entitas_bisnis = trf.eb_asal
        aset.lokasi_aset = trf.lokasi_asal
        aset.departemen = trf.dept_asal
        aset.pic = trf.pic_lama
        aset.save()
        trf.delete()
