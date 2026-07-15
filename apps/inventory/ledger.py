"""Authoritative stock ledger engine — inflow, consumption, reversal, queries.

All quantities are in the item's base uom (Decimal). Bulk items (RMB/FGB/ITMB)
use the existing value-based convention (qty=1, unit_cost=total_value).
"""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from .models import StockMovement, StockConsumption


class InsufficientStockError(ValueError):
    """Raised when consumption cannot be satisfied within the EB hierarchy."""


def requested_level(eb_lv2, eb_lv3) -> str:
    if eb_lv3 is not None:
        return 'lv3'
    if eb_lv2 is not None:
        return 'lv2'
    return 'lv1'


def _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
    """Return [(level_label, eb_name, queryset), ...] closest EB node first.

    Each queryset selects inflow layers (remaining_qty > 0) at that tier,
    FIFO-ordered. Sibling branches are never included.
    """
    base = StockMovement.objects.filter(item=item, remaining_qty__gt=0)
    tiers = []
    if eb_lv3 is not None:
        tiers.append((
            'lv3', eb_lv3.nama,
            base.filter(entitas_bisnis_lv3=eb_lv3).order_by('tanggal', 'created_at'),
        ))
    if eb_lv2 is not None:
        tiers.append((
            'lv2', eb_lv2.nama,
            base.filter(entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3__isnull=True)
                .order_by('tanggal', 'created_at'),
        ))
    tiers.append((
        'lv1', eb_lv1.nama,
        base.filter(entitas_bisnis=eb_lv1, entitas_bisnis_lv2__isnull=True,
                    entitas_bisnis_lv3__isnull=True)
            .order_by('tanggal', 'created_at'),
    ))
    return tiers


def get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None) -> Decimal:
    from django.db.models import Sum
    total = Decimal('0')
    for _level, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        agg = qs.aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0')
        total += agg
    return total


def record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal,
                  movement_type, source=None, *,
                  legacy_fifo_batch=None, legacy_inventory_record=None):
    """Create one inflow StockMovement layer (remaining_qty = qty)."""
    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    return StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=qty, unit_cost=unit_cost, remaining_qty=qty,
        source_content_type=ct, source_object_id=obj_id,
        legacy_fifo_batch=legacy_fifo_batch,
        legacy_inventory_record=legacy_inventory_record,
    )
