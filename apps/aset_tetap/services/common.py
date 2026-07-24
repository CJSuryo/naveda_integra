"""Aset Tetap services — shared helpers used across event modules."""
from apps.jurnal.models import JurnalHeader

from ..models import AsetTetapRecord


def _next_journal_number(prefix: str) -> str:
    """Generate sequential journal number for a given prefix (e.g. 'TRX-DEP-', 'TRX-DSP-')."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith=prefix)
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:03d}'


def _resolve_asset_account(record: AsetTetapRecord):
    """Akun aset yang didebit saat perolehan: purchase_item.coa_account -> item.coa_account."""
    if record.purchase_item_id and record.purchase_item and record.purchase_item.coa_account:
        return record.purchase_item.coa_account
    if record.item and record.item.coa_account:
        return record.item.coa_account
    return None
