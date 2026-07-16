from decimal import Decimal

from django.db import migrations


# (kode, nama, dimension, factor_to_base, is_base)
NEW_UNITS = [
    # weight (base = g) — complete metric ladder + Indonesian commodity units
    ('cg', 'Sentigram', 'weight', Decimal('0.01'), False),
    ('dg', 'Desigram', 'weight', Decimal('0.1'), False),
    ('dag', 'Dekagram', 'weight', Decimal('10'), False),
    ('hg', 'Hektogram (Ons)', 'weight', Decimal('100'), False),
    ('kuintal', 'Kuintal', 'weight', Decimal('100000'), False),
    # volume (base = mL)
    ('cL', 'Sentiliter', 'volume', Decimal('10'), False),
    ('dL', 'Desiliter', 'volume', Decimal('100'), False),
    ('kL', 'Kiloliter', 'volume', Decimal('1000000'), False),
    # length (base = mm)
    ('dm', 'Desimeter', 'length', Decimal('100'), False),
    ('km', 'Kilometer', 'length', Decimal('1000000'), False),
    # area (base = m2)
    ('ha', 'Hektar', 'area', Decimal('10000'), False),
    ('km2', 'Kilometer Persegi', 'area', Decimal('1000000'), False),
]


def seed(apps, schema_editor):
    UnitOfMeasure = apps.get_model('uom', 'UnitOfMeasure')
    for kode, nama, dimension, factor, is_base in NEW_UNITS:
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
    UnitOfMeasure.objects.filter(kode__in=[kode for kode, *_ in NEW_UNITS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('uom', '0004_alter_itemuom_qty_in_stock_uom_and_more'),
    ]
    operations = [
        migrations.RunPython(seed, unseed),
    ]
