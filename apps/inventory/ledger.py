"""Authoritative stock ledger engine — inflow, consumption, reversal, queries.

All quantities are in the item's base uom (Decimal). Bulk items (RMB/FGB/ITMB)
use the existing value-based convention (qty=1, unit_cost=total_value).
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import StockMovement, StockConsumption

OUTFLOW_MOVEMENT_TYPES = {
    'sale_out', 'production_out',
    'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier',
}

_METHOD_ALIASES = {
    '': 'fifo',
    'fifo': 'fifo',
    'lifo': 'lifo',
    'average': 'average',
    'weighted_moving_average': 'average',
}


def _normalize_method(metode) -> str:
    """Petakan pilihan metode item ke strategi engine ('fifo'|'lifo'|'average').

    Kosong/None → 'fifo'. String tak dikenal → ValueError (jangan diam-diam FIFO).
    """
    key = (metode or '').strip().lower()
    if key not in _METHOD_ALIASES:
        raise ValueError(f'Metode biaya persediaan tak didukung: {metode!r}')
    return _METHOD_ALIASES[key]


class InsufficientStockError(ValueError):
    """Raised when consumption cannot be satisfied within the EB hierarchy."""


def _validate_warehouse_tenant(warehouse, eb_lv1):
    """Fail-loud jika gudang bukan milik bisnis (lv1) movement ini."""
    if warehouse is not None and warehouse.entitas_bisnis_id != eb_lv1.pk:
        raise ValueError(
            f'Gudang {warehouse.kode} milik bisnis lain, '
            f'bukan {eb_lv1} — stok tak boleh lintas bisnis.'
        )


def requested_level(eb_lv2, eb_lv3) -> str:
    if eb_lv3 is not None:
        return 'lv3'
    if eb_lv2 is not None:
        return 'lv2'
    return 'lv1'


def _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse=None, *, order='fifo'):
    """Return [(level_label, eb_name, queryset), ...] closest EB node first.

    Each queryset selects inflow layers (remaining_qty > 0) at that tier,
    ordered per `order` ('fifo' → oldest first, 'lifo' → newest first).
    Sibling branches are never included.

    When `warehouse` is given, layers are restricted to that exact warehouse
    (NULL-warehouse layers are excluded — no cross-warehouse fallback). When
    `warehouse` is None (default), no warehouse filter is applied — matches
    the pre-warehouse (Fase 2) behavior exactly.
    """
    base = StockMovement.objects.filter(item=item, remaining_qty__gt=0)
    if warehouse is not None:
        base = base.filter(warehouse=warehouse)
    order_by = ('tanggal', 'created_at') if order == 'fifo' else ('-tanggal', '-created_at')
    tiers = []
    if eb_lv3 is not None:
        tiers.append((
            'lv3', eb_lv3.nama,
            base.filter(entitas_bisnis_lv3=eb_lv3).order_by(*order_by),
        ))
    if eb_lv2 is not None:
        tiers.append((
            'lv2', eb_lv2.nama,
            base.filter(entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3__isnull=True)
                .order_by(*order_by),
        ))
    tiers.append((
        'lv1', eb_lv1.nama,
        base.filter(entitas_bisnis=eb_lv1, entitas_bisnis_lv2__isnull=True,
                    entitas_bisnis_lv3__isnull=True)
            .order_by(*order_by),
    ))
    return tiers


def get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None) -> Decimal:
    from django.db.models import Sum
    total = Decimal('0')
    for _level, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
        agg = qs.aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0')
        total += agg
    return total


def current_unit_cost(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None,
                      metode=None) -> 'Decimal | None':
    """Harga acuan per unit dari layer tersisa, mengikuti metode costing item.

    FIFO  -> unit_cost layer tersisa TERTUA (akan keluar berikutnya).
    LIFO  -> unit_cost layer tersisa TERBARU.
    average / weighted_moving_average -> rata-rata tertimbang layer tersisa.
    Kembalikan None bila tidak ada stok tersisa di scope (item baru / tanpa layer).
    """
    strategy = _normalize_method(metode if metode is not None else item.metode_biaya_persediaan)
    order = 'lifo' if strategy == 'lifo' else 'fifo'
    if strategy == 'average':
        total_qty = Decimal('0')
        total_val = Decimal('0')
        for _lvl, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
            for layer in qs:
                total_qty += layer.remaining_qty
                total_val += layer.remaining_qty * layer.unit_cost
        if total_qty <= 0:
            return None
        return (total_val / total_qty).quantize(Decimal('0.0001'))
    # FIFO / LIFO: layer pertama (per urutan) dari tier terdekat yang punya stok
    for _lvl, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse,
                                            order=order):
        layer = qs.first()
        if layer is not None:
            return layer.unit_cost
    return None


def record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal,
                  movement_type, source=None, *, warehouse=None,
                  legacy_fifo_batch=None, legacy_inventory_record=None):
    """Create one inflow StockMovement layer (remaining_qty = qty)."""
    _validate_warehouse_tenant(warehouse, eb_lv1)
    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    return StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        warehouse=warehouse,
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


def _take_tier_sequential(layers, remaining):
    """FIFO/LIFO: `layers` sudah terurut. Ambil di biaya asli tiap layer.

    Mengembalikan (picked, cost, taken) dengan
    picked = [(layer, take, alloc_unit_cost), ...].
    Meng-update remaining_qty tiap layer + mirror legacy secara in-place.
    """
    picked = []
    cost = Decimal('0')
    taken = Decimal('0')
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.remaining_qty, remaining)
        if take <= 0:
            continue
        layer.remaining_qty -= take
        layer.save(update_fields=['remaining_qty'])
        _mirror_decrement(layer, take, take * layer.unit_cost)
        picked.append((layer, take, layer.unit_cost))
        cost += take * layer.unit_cost
        taken += take
        remaining -= take
    return picked, cost, taken


def _take_tier_average(layers, remaining):
    """Moving weighted average dalam satu tier.

    Biaya = qty × rata-rata tertimbang tier (dihitung sebelum pengurangan).
    Qty dikurangi PROPORSIONAL di semua layer agar rata-rata sisa tetap benar
    untuk konsumsi berikutnya. Sisa pembulatan dibebankan ke layer terakhir.

    Mengembalikan (picked, cost, taken) dengan
    picked = [(layer, take, avg), ...].
    """
    Q = Decimal('0.0001')
    active = [l for l in layers if l.remaining_qty > 0]
    total_qty = sum((l.remaining_qty for l in active), Decimal('0'))
    if total_qty <= 0:
        return [], Decimal('0'), Decimal('0')
    total_value = sum((l.remaining_qty * l.unit_cost for l in active), Decimal('0'))
    avg = (total_value / total_qty).quantize(Q)
    take_total = min(remaining, total_qty)

    if take_total >= total_qty:
        per_layer = [(l, l.remaining_qty) for l in active]
    else:
        fraction = take_total / total_qty
        per_layer = [(l, (l.remaining_qty * fraction).quantize(Q, rounding=ROUND_DOWN))
                     for l in active]
        allocated = sum((t for _, t in per_layer), Decimal('0'))
        residual = take_total - allocated
        if residual != 0:
            l_last, t_last = per_layer[-1]
            per_layer[-1] = (l_last, t_last + residual)

    picked = []
    cost = Decimal('0')
    taken = Decimal('0')
    for layer, take in per_layer:
        if take <= 0:
            continue
        layer.remaining_qty -= take
        layer.save(update_fields=['remaining_qty'])
        _mirror_decrement(layer, take, take * avg)
        picked.append((layer, take, avg))
        cost += take * avg
        taken += take
    return picked, cost, taken


@transaction.atomic
def consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
                  source=None, metode='fifo', *, warehouse=None):
    """Consume `qty` (base uom) of `item` within the EB hierarchy, FIFO.

    Non-bulk path (tipe_item in RM/FG/ITM). Raises InsufficientStockError if
    the hierarchy cannot cover qty. Bulk items (RMB/FGB/ITMB) are routed to
    a value-based branch (implemented in a later task).

    When `warehouse` is given, consumption is locked to that exact warehouse
    (no fallback to other warehouses or to NULL-warehouse layers). When
    `warehouse` is None (default), behavior is unchanged from before
    warehouse-awareness (Fase 2).
    """
    _validate_warehouse_tenant(warehouse, eb_lv1)
    req_level = requested_level(eb_lv2, eb_lv3)
    req_rank = _LEVEL_RANK[req_level]

    is_bulk = item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if is_bulk:
        return _consume_stock_bulk(
            item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
            source, req_level, req_rank, warehouse=warehouse,
        )

    method = _normalize_method(metode)
    order = 'lifo' if method == 'lifo' else 'fifo'

    remaining = qty
    total_cost = Decimal('0')
    per_level = {}          # level -> {'eb_name': str, 'qty': Decimal}
    picked = []             # (layer, take, alloc_unit_cost)

    for level, eb_name, qs in _candidate_tiers(
        item, eb_lv1, eb_lv2, eb_lv3, warehouse, order=order,
    ):
        if remaining <= 0:
            break
        layers = list(qs.select_for_update())
        if method == 'average':
            tier_picked, tier_cost, tier_qty = _take_tier_average(layers, remaining)
        else:
            tier_picked, tier_cost, tier_qty = _take_tier_sequential(layers, remaining)
        if tier_qty <= 0:
            continue
        picked.extend(tier_picked)
        total_cost += tier_cost
        remaining -= tier_qty
        slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
        slot['qty'] += tier_qty

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
        warehouse=warehouse,
        tanggal=tanggal, movement_type=movement_type,
        qty=-qty, unit_cost=avg_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=take, unit_cost=alloc_unit_cost,
        )
        for layer, take, alloc_unit_cost in picked
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
                        movement_type, source, req_level, req_rank, *,
                        warehouse=None):
    """Bulk value-based consumption. Layer value = remaining_qty * unit_cost.

    `value` is the amount of stock VALUE to deduct (not a physical quantity).
    Deduct proportionally by reducing remaining_qty so remaining value drops
    by the taken amount, walking the same hierarchical tiers as non-bulk.
    """
    remaining_value = value
    total_cost = Decimal('0')
    per_level = {}
    picked = []  # (layer, value_taken)

    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
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
        warehouse=warehouse,
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
        movement_type__in=OUTFLOW_MOVEMENT_TYPES,
    )
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


INFLOW_MOVEMENT_TYPES = {
    'purchase_in', 'production_in', 'saldo_awal',
    'adjustment_in', 'opname_in', 'transfer_in', 'return_customer',
}


@transaction.atomic
def reverse_inflow_movements(source):
    """Delete inflow StockMovement rows produced by `source`.

    Unconditional delete, matching the legacy FIFOBatch/InventoryRecord reversal
    convention. Raises ProtectedError (via StockConsumption.in_movement PROTECT)
    if any layer was already consumed — this is intentional fail-loud behavior,
    not a bug to work around here.
    """
    ct = ContentType.objects.get_for_model(type(source))
    StockMovement.objects.filter(
        source_content_type=ct, source_object_id=source.pk,
        movement_type__in=INFLOW_MOVEMENT_TYPES,
    ).delete()
