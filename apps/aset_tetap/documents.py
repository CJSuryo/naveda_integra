"""Helper dokumen/foto aset — reuse master_data.Bukti via referensi_eksternal (aset_number)."""
from apps.master_data.models import Bukti


def list_bukti_aset(aset):
    """QuerySet Bukti yang tertaut ke aset (berdasar aset_number)."""
    return Bukti.objects.filter(referensi_eksternal=aset.aset_number).order_by('-uploaded_at')


def attach_bukti_aset(aset, *, tipe: str, filepath: str, file_hash: str = '') -> Bukti:
    """Tautkan satu bukti (foto/dokumen) ke aset."""
    return Bukti.objects.create(
        referensi_eksternal=aset.aset_number,
        tipe_dokumen=tipe,
        filepath=filepath,
        file_hash=file_hash,
    )
