"""Backfill StockMovement inflow layers from existing FIFOBatch + InventoryRecord.

Driven by FIFOBatch (authoritative FIFO remaining/cost). EB attribution comes
from the batch's purchase_item.purchase_eb, or from a matching InventoryRecord
for saldo-awal batches. Historical outflows are NOT reconstructed; remaining_qty
is snapshotted from the current FIFOBatch state.
"""


def _eb_from_purchase_item(pi):
    peb = pi.purchase_eb
    return peb.entitas_bisnis, peb.entitas_bisnis_lv2, peb.entitas_bisnis_lv3


def backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem):
    """Create one inflow StockMovement per FIFOBatch. Returns count created.

    Idempotent: skips batches that already have a linked StockMovement.
    """
    created = 0
    for batch in FIFOBatch.objects.all().iterator():
        if StockMovement.objects.filter(legacy_fifo_batch=batch).exists():
            continue
        eb1 = eb2 = eb3 = None
        rec = None
        if batch.purchase_item_id:
            pi = PurchaseItem.objects.select_related(
                'purchase_eb__entitas_bisnis',
                'purchase_eb__entitas_bisnis_lv2',
                'purchase_eb__entitas_bisnis_lv3',
            ).get(pk=batch.purchase_item_id)
            eb1, eb2, eb3 = _eb_from_purchase_item(pi)
            rec = InventoryRecord.objects.filter(purchase_item=pi).order_by('created_at').first()
        else:
            rec = InventoryRecord.objects.filter(
                item=batch.item, tanggal=batch.tanggal, unit_price=batch.unit_price,
            ).order_by('created_at').first()
            if rec is not None:
                eb1 = rec.entitas_bisnis
                eb2 = rec.entitas_bisnis_lv2
                eb3 = rec.entitas_bisnis_lv3
        if eb1 is None:
            # EB tak teratribusi — lewati; dilaporkan oleh reconcile command.
            continue
        movement_type = 'purchase_in' if batch.purchase_item_id else 'saldo_awal'
        # Deliberately do not set source_content_type/source_object_id: real-time
        # dual-write (Task 7/8/9, via ledger.record_inflow(source=...)) always sets
        # a source object, so leaving it null here is what lets
        # backfilled_movements_queryset() tell backfilled rows apart from rows the
        # normal application code created.
        StockMovement.objects.create(
            item=batch.item, entitas_bisnis=eb1,
            entitas_bisnis_lv2=eb2, entitas_bisnis_lv3=eb3,
            tanggal=batch.tanggal, movement_type=movement_type,
            qty=batch.quantity_in, unit_cost=batch.unit_price,
            remaining_qty=batch.remaining_qty,
            legacy_fifo_batch=batch, legacy_inventory_record=rec,
        )
        created += 1
    return created


def backfilled_movements_queryset(StockMovement):
    """Return the queryset of StockMovement rows created by backfill_stock_movements.

    Distinguishing signal: backfill never sets source_content_type/source_object_id
    (no `source=` is passed to StockMovement.objects.create above), whereas every
    real-time dual-write path (apps.purchase.services.create_stock_movements,
    apps.sales.services, apps.manufacturing.services) calls
    apps.inventory.ledger.record_inflow(..., source=<the originating record>),
    which always populates source_content_type. This makes the distinction
    structural rather than time-based, so it is safe to use in the migration's
    backwards() even long after the backfill ran, without risking deletion of
    legitimate StockMovement rows created by normal application traffic (whether
    created before or after the backfill migration itself was applied).
    """
    return StockMovement.objects.filter(
        legacy_fifo_batch__isnull=False,
        source_content_type__isnull=True,
    )
