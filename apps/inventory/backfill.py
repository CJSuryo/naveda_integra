"""Backfill StockMovement inflow layers from existing FIFOBatch + InventoryRecord.

Driven by FIFOBatch (authoritative FIFO remaining/cost). EB attribution comes
from the batch's purchase_item.purchase_eb, or from a matching InventoryRecord
for saldo-awal batches. Historical outflows are NOT reconstructed; remaining_qty
is snapshotted from the current FIFOBatch state.
"""
from decimal import Decimal


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
