# Generated manually for pos_catalog architecture pivot.
# Removes POSCategory, POSProduct, ProductStoreAvailability.
# Renames ProductModifierGroup.product (FK to POSProduct)
# to ProductModifierGroup.item (FK to purchase.ItemMasterPurchase).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos_catalog', '0001_initial'),
        ('purchase', '0003_add_nilai_residu_to_item_master'),
        # All FKs/M2Ms pointing to POSProduct must be removed before we delete the table.
        ('pos_orders', '0004_alter_orderitem_product'),
        ('pos_promotions', '0002_remove_campaign_applicable_categories_and_more'),
    ]

    operations = [
        # 1. Drop unique_together that references the old 'product' field
        migrations.AlterUniqueTogether(
            name='productmodifiergroup',
            unique_together=set(),
        ),

        # 2. Remove ProductStoreAvailability (depends on POSProduct)
        migrations.DeleteModel(
            name='ProductStoreAvailability',
        ),

        # 3. Remove the old FK field 'product' from ProductModifierGroup
        migrations.RemoveField(
            model_name='productmodifiergroup',
            name='product',
        ),

        # 4. Remove POSProduct (depends on POSCategory)
        migrations.DeleteModel(
            name='POSProduct',
        ),

        # 5. Remove POSCategory
        migrations.DeleteModel(
            name='POSCategory',
        ),

        # 6. Add new FK field 'item' pointing to purchase.ItemMasterPurchase
        migrations.AddField(
            model_name='productmodifiergroup',
            name='item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='modifier_links',
                to='purchase.itemmasterpurchase',
            ),
            preserve_default=False,
        ),

        # 7. Restore unique_together with the new field name
        migrations.AlterUniqueTogether(
            name='productmodifiergroup',
            unique_together={('item', 'modifier_group')},
        ),
    ]
