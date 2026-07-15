"""Authoritative stock ledger engine — inflow, consumption, reversal, queries.

All quantities are in the item's base uom (Decimal). Bulk items (RMB/FGB/ITMB)
use the existing value-based convention (qty=1, unit_cost=total_value).
"""
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

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


@dataclass
class ConsumptionReport:
    requested_level: str
    used_fallback: bool
    by_level: list


@dataclass
class ConsumptionResult:
    total_cost: Decimal
    allocations: list
    out_movement: object
    report: ConsumptionReport


_LEVEL_RANK = {'lv1': 1, 'lv2': 2, 'lv3': 3}


@transaction.atomic
def consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
                  source=None, metode='fifo'):
    """Consume `qty` (base uom) of `item` within the EB hierarchy, FIFO.

    Non-bulk path (tipe_item in RM/FG/ITM). Raises InsufficientStockError if
    the hierarchy cannot cover qty. Bulk items (RMB/FGB/ITMB) are routed to
    a value-based branch (implemented in a later task).
    """
    req_level = requested_level(eb_lv2, eb_lv3)
    req_rank = _LEVEL_RANK[req_level]

    is_bulk = item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if is_bulk:
        return _consume_stock_bulk(
            item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
            source, req_level, req_rank,
        )

    remaining = qty
    total_cost = Decimal('0')
    per_level = {}          # level -> {'eb_name': str, 'qty': Decimal}
    picked = []              # (in_layer, take)

    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        if remaining <= 0:
            break
        layers = qs.select_for_update()
        for layer in layers:
            if remaining <= 0:
                break
            take = min(layer.remaining_qty, remaining)
            if take <= 0:
                continue
            layer.remaining_qty -= take
            layer.save(update_fields=['remaining_qty'])
            _mirror_decrement(layer, take, take * layer.unit_cost)
            total_cost += take * layer.unit_cost
            picked.append((layer, take))
            slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
            slot['qty'] += take
            remaining -= take

    if remaining > 0:
        raise InsufficientStockError(
            f'Stok tidak mencukupi untuk {item.item_id}. '
            f'Diminta {qty}, tersedia {qty - remaining} dalam hierarki EB.'
        )

    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    avg_cost = (total_cost / qty) if qty else Decimal('0')
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=-qty, unit_cost=avg_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=take, unit_cost=layer.unit_cost,
        )
        for layer, take in picked
    ]

    used_fallback = any(_LEVEL_RANK[lvl] < req_rank for lvl in per_level)
    by_level = [
        {'level': lvl, 'eb_name': per_level[lvl]['eb_name'], 'qty': per_level[lvl]['qty']}
        for lvl in sorted(per_level, key=lambda l: -_LEVEL_RANK[l])
    ]
    report = ConsumptionReport(
        requested_level=req_level, used_fallback=used_fallback, by_level=by_level,
    )
    return ConsumptionResult(
        total_cost=total_cost, allocations=allocations,
        out_movement=out_movement, report=report,
    )


def _mirror_decrement(layer, take_qty, take_value):
    """Mirror a consumption decrement onto linked legacy rows.

    Non-bulk uses take_qty; bulk uses take_value (reduces InventoryRecord.total_value
    and FIFOBatch remaining value)."""
    batch = layer.legacy_fifo_batch
    rec = layer.legacy_inventory_record
    is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if batch is not None:
        if is_bulk:
            cur = batch.remaining_qty * batch.unit_price
            batch.remaining_qty = ((cur - take_value) / batch.unit_price
                                   if batch.unit_price else Decimal('0'))
        else:
            batch.remaining_qty -= take_qty
        batch.save(update_fields=['remaining_qty', 'batch_value'])
    if rec is not None:
        if is_bulk:
            rec.total_value = (rec.total_value or Decimal('0')) - take_value
            rec.unit_price = rec.total_value
            rec.save(update_fields=['total_value', 'unit_price'])
        else:
            rec.quantity -= take_qty
            rec.total_value = rec.quantity * rec.unit_price
            rec.save(update_fields=['quantity', 'total_value'])


def _mirror_restore(layer, take_qty, take_value):
    """Inverse of _mirror_decrement — restores legacy rows on reversal."""
    batch = layer.legacy_fifo_batch
    rec = layer.legacy_inventory_record
    is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if batch is not None:
        if is_bulk:
            cur = batch.remaining_qty * batch.unit_price
            batch.remaining_qty = ((cur + take_value) / batch.unit_price
                                   if batch.unit_price else Decimal('0'))
        else:
            batch.remaining_qty += take_qty
        batch.save(update_fields=['remaining_qty', 'batch_value'])
    if rec is not None:
        if is_bulk:
            rec.total_value = (rec.total_value or Decimal('0')) + take_value
            rec.unit_price = rec.total_value
            rec.save(update_fields=['total_value', 'unit_price'])
        else:
            rec.quantity += take_qty
            rec.total_value = rec.quantity * rec.unit_price
            rec.save(update_fields=['quantity', 'total_value'])


@transaction.atomic
def _consume_stock_bulk(item, eb_lv1, eb_lv2, eb_lv3, value, tanggal,
                        movement_type, source, req_level, req_rank):
    """Bulk value-based consumption. Layer value = remaining_qty * unit_cost.

    `value` is the amount of stock VALUE to deduct (not a physical quantity).
    Deduct proportionally by reducing remaining_qty so remaining value drops
    by the taken amount, walking the same hierarchical tiers as non-bulk.
    """
    remaining_value = value
    total_cost = Decimal('0')
    per_level = {}
    picked = []  # (layer, value_taken)

    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        if remaining_value <= 0:
            break
        for layer in qs.select_for_update():
            if remaining_value <= 0:
                break
            layer_value = layer.remaining_qty * layer.unit_cost
            take_value = min(layer_value, remaining_value)
            if take_value <= 0:
                continue
            # Guard is defensive/unreachable by construction: unit_cost == 0
            # forces layer_value == 0, so take_value <= 0 and the `continue`
            # above already skips this layer before the division would run.
            layer.remaining_qty = ((layer_value - take_value) / layer.unit_cost
                                   if layer.unit_cost else Decimal('0'))
            layer.save(update_fields=['remaining_qty'])
            _mirror_decrement(layer, Decimal('0'), take_value)
            total_cost += take_value
            picked.append((layer, take_value))
            slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
            slot['qty'] += take_value
            remaining_value -= take_value

    if remaining_value > 0:
        raise InsufficientStockError(
            f'Nilai stok bulk tidak mencukupi untuk {item.item_id}. '
            f'Diminta {value}, tersedia {value - remaining_value}.'
        )

    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=Decimal('0'), unit_cost=total_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
    # NOTE: unit_cost here is the layer's own original cost (bulk layers
    # have qty~=1 so this is effectively the layer's original total value),
    # not the value taken from it in this consumption. See out_movement.unit_cost
    # for the total value actually deducted across all layers.
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=take_value, unit_cost=layer.unit_cost,
        )
        for layer, take_value in picked
    ]
    used_fallback = any(_LEVEL_RANK[lvl] < req_rank for lvl in per_level)
    by_level = [
        {'level': lvl, 'eb_name': per_level[lvl]['eb_name'], 'qty': per_level[lvl]['qty']}
        for lvl in sorted(per_level, key=lambda l: -_LEVEL_RANK[l])
    ]
    report = ConsumptionReport(
        requested_level=req_level, used_fallback=used_fallback, by_level=by_level,
    )
    return ConsumptionResult(
        total_cost=total_cost, allocations=allocations,
        out_movement=out_movement, report=report,
    )


@transaction.atomic
def reverse_movements(source):
    """Reverse all outflow movements produced by `source`: restore inflow layers
    (and legacy mirrors), delete allocations and outflow rows."""
    ct = ContentType.objects.get_for_model(type(source))
    outflows = StockMovement.objects.filter(
        source_content_type=ct, source_object_id=source.pk,
        qty__lte=0,
    ).exclude(movement_type__in=('purchase_in', 'production_in', 'saldo_awal'))
    for out in outflows.select_for_update():
        for alloc in out.consumptions_out.select_related('in_movement').all():
            layer = alloc.in_movement
            is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            if is_bulk:
                take_value = alloc.qty  # bulk: qty column stores value taken
                cur = layer.remaining_qty * layer.unit_cost
                layer.remaining_qty = ((cur + take_value) / layer.unit_cost
                                       if layer.unit_cost else Decimal('0'))
                layer.save(update_fields=['remaining_qty'])
                _mirror_restore(layer, Decimal('0'), take_value)
            else:
                layer.remaining_qty += alloc.qty
                layer.save(update_fields=['remaining_qty'])
                _mirror_restore(layer, alloc.qty, Decimal('0'))
        out.consumptions_out.all().delete()
    outflows.delete()
