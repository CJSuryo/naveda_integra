"""Jurnal utility helpers — shared across apps."""
from __future__ import annotations

from django.http import HttpRequest


def log_jurnal_terhapus(header, module: str, request: HttpRequest | None = None) -> None:
    """Create a JurnalTerhapus log entry capturing the journal before it is deleted.

    Call this *before* deleting the JurnalHeader so details are still queryable.
    """
    from .models import JurnalTerhapus  # local import to avoid circular

    details = list(
        header.details.select_related('akun').values(
            'akun__kode_akun', 'akun__nama', 'debit', 'kredit',
        )
    )
    # Decimal is not JSON-serialisable — convert to str
    for d in details:
        d['debit'] = str(d['debit'])
        d['kredit'] = str(d['kredit'])

    user = None
    if request and hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user

    JurnalTerhapus.objects.create(
        nomor_transaksi=header.nomor_transaksi,
        uraian_transaksi=header.uraian_transaksi,
        entitas_bisnis_nama=str(header.entitas_bisnis) if header.entitas_bisnis else '',
        tanggal=header.tanggal,
        module=module,
        deleted_by=user,
        detail_snapshot=details,
    )
