from decimal import Decimal

from django.db import migrations


# (kode, nama, dimension, factor_to_base, is_base)
UNITS = [
    # count
    ('pcs', 'Pieces', 'count', Decimal('1'), True),
    ('unit', 'Unit', 'count', Decimal('1'), False),
    ('lusin', 'Lusin', 'count', Decimal('12'), False),
    ('gross', 'Gross', 'count', Decimal('144'), False),
    ('box', 'Box', 'count', None, False),
    ('pack', 'Pack', 'count', None, False),
    ('carton', 'Karton', 'count', None, False),
    ('dus', 'Dus', 'count', None, False),
    ('roll', 'Roll', 'count', None, False),
    ('botol', 'Botol', 'count', None, False),
    # weight (base = g)
    ('g', 'Gram', 'weight', Decimal('1'), True),
    ('mg', 'Miligram', 'weight', Decimal('0.001'), False),
    ('kg', 'Kilogram', 'weight', Decimal('1000'), False),
    ('ton', 'Ton', 'weight', Decimal('1000000'), False),
    # volume (base = mL)
    ('mL', 'Mililiter', 'volume', Decimal('1'), True),
    ('cc', 'CC', 'volume', Decimal('1'), False),
    ('L', 'Liter', 'volume', Decimal('1000'), False),
    ('m3', 'Meter Kubik', 'volume', Decimal('1000000'), False),
    # length (base = mm)
    ('mm', 'Milimeter', 'length', Decimal('1'), True),
    ('cm', 'Sentimeter', 'length', Decimal('10'), False),
    ('m', 'Meter', 'length', Decimal('1000'), False),
    # area (base = m2)
    ('m2', 'Meter Persegi', 'area', Decimal('1'), True),
    ('cm2', 'Sentimeter Persegi', 'area', Decimal('0.0001'), False),
]


def seed(apps, schema_editor):
    UnitOfMeasure = apps.get_model('uom', 'UnitOfMeasure')
    for kode, nama, dimension, factor, is_base in UNITS:
        UnitOfMeasure.objects.update_or_create(
            kode=kode,
            defaults={
                'nama': nama,
                'dimension': dimension,
                'factor_to_base': factor,
                'is_base': is_base,
                'is_system': True,
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    UnitOfMeasure = apps.get_model('uom', 'UnitOfMeasure')
    UnitOfMeasure.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('uom', '0002_itemuom'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
