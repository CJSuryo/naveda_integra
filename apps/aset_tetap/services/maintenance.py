"""Aset Tetap services — journal generation for asset maintenance."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from ..models import AssetMaintenance
from .common import _next_journal_number


def process_asset_maintenance(mtn: AssetMaintenance) -> JurnalHeader:
    """Jurnal: D Beban Pemeliharaan, K Kas/Utang. Update kondisi aset bila diisi."""
    if mtn.biaya is None or mtn.biaya <= 0:
        raise ValueError('Biaya maintenance harus lebih dari 0.')
    aset = mtn.aset
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas — maintenance tidak dapat diproses.')

    with transaction.atomic():
        mtn.kondisi_sebelum = aset.kondisi
        if mtn.kondisi_setelah:
            aset.kondisi = mtn.kondisi_setelah
            aset.save()

        header = JurnalHeader.objects.create(
            tanggal=mtn.tanggal,
            nomor_transaksi=_next_journal_number('TRX-MTN-'),
            uraian_transaksi=f'Maintenance {aset.aset_number} ({mtn.get_jenis_display()})',
            entitas_bisnis=aset.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=mtn.akun_beban, debit=mtn.biaya, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=mtn.akun_kas_utang, debit=Decimal('0'), kredit=mtn.biaya),
        ])
        mtn.jurnal_header = header
        mtn.save()
    return header


def reverse_asset_maintenance(mtn: AssetMaintenance, request=None) -> None:
    """Batalkan maintenance: hapus jurnal, pulihkan kondisi aset, hapus record."""
    from apps.jurnal.utils import log_jurnal_terhapus
    aset = mtn.aset
    with transaction.atomic():
        header = mtn.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()
        if mtn.kondisi_sebelum:
            aset.kondisi = mtn.kondisi_sebelum
            aset.save()
        mtn.delete()
