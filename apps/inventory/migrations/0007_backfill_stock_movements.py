from django.db import migrations


def forwards(apps, schema_editor):
    from apps.inventory.backfill import backfill_stock_movements
    FIFOBatch = apps.get_model('purchase', 'FIFOBatch')
    InventoryRecord = apps.get_model('inventory', 'InventoryRecord')
    StockMovement = apps.get_model('inventory', 'StockMovement')
    PurchaseItem = apps.get_model('purchase', 'PurchaseItem')
    backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)


def backwards(apps, schema_editor):
    from apps.inventory.backfill import backfilled_movements_queryset
    StockMovement = apps.get_model('inventory', 'StockMovement')
    # Scoped to rows this migration's forwards() actually created (no source
    # object set) — NOT every StockMovement with legacy_fifo_batch set, since
    # normal Purchase/Sales/Manufacturing dual-write also sets that field.
    # See backfilled_movements_queryset() for the distinguishing signal.
    backfilled_movements_queryset(StockMovement).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0006_stockmovement_idx_sm_item_lv2_remaining_and_more'),
        ('purchase', '0008_backfill_item_uom'),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
