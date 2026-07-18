"""Isi ReturCustomer.sales_header untuk retur lama yang headernya kosong.

Header sebelumnya hanya alat bantu filter di form dan boleh kosong, sehingga
banyak retur tersimpan tanpa nomor penjualan meski item-itemnya jelas berasal
dari sebuah faktur. Turunkan dari item bila seluruh item satu SalesHeader.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    ReturCustomer = apps.get_model('inventory', 'ReturCustomer')
    for rtc in ReturCustomer.objects.filter(sales_header__isnull=True):
        header_ids = set(
            rtc.items.filter(sales_item__isnull=False)
            .values_list('sales_item__sales_eb__sales_header_id', flat=True)
        )
        if len(header_ids) == 1:
            rtc.sales_header_id = header_ids.pop()
            rtc.save(update_fields=['sales_header'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0018_itemreordersetting'),
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
