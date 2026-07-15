from django.db import migrations


def forwards(apps, schema_editor):
    from apps.uom.backfill import backfill_default_uom
    ItemModel = apps.get_model('purchase', 'ItemMasterPurchase')
    UnitModel = apps.get_model('uom', 'UnitOfMeasure')
    backfill_default_uom(ItemModel, UnitModel)


def backwards(apps, schema_editor):
    # Non-destructive: leave data as-is on reverse.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('purchase', '0007_itemmasterpurchase_purchase_uom_and_more'),
        ('uom', '0003_seed_units'),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
