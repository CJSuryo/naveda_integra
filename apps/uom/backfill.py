"""Reusable backfill logic for default item UOM (also called by migration)."""


def backfill_default_uom(ItemModel, UnitModel):
    """Set stock/purchase/sales UOM to 'pcs' for any item missing them."""
    pcs = UnitModel.objects.filter(kode='pcs').first()
    if pcs is None:
        return
    for item in ItemModel.objects.filter(stock_uom__isnull=True):
        item.stock_uom = pcs
        if item.purchase_uom_id is None:
            item.purchase_uom = pcs
        if item.sales_uom_id is None:
            item.sales_uom = pcs
        item.save(update_fields=['stock_uom', 'purchase_uom', 'sales_uom'])
    # Items that have stock_uom but missing purchase/sales
    for item in ItemModel.objects.filter(purchase_uom__isnull=True):
        item.purchase_uom = pcs
        item.save(update_fields=['purchase_uom'])
    for item in ItemModel.objects.filter(sales_uom__isnull=True):
        item.sales_uom = pcs
        item.save(update_fields=['sales_uom'])
