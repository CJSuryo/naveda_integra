from django.db import migrations

DEFAULT_RATES = [
    ('current',  'Belum Jatuh Tempo',  '0.00',  1),
    ('1_30',     'Lewat 1–30 Hari',    '5.00',  2),
    ('31_60',    'Lewat 31–60 Hari',   '15.00', 3),
    ('61_90',    'Lewat 61–90 Hari',   '25.00', 4),
    ('91_180',   'Lewat 91–180 Hari',  '50.00', 5),
    ('181_365',  'Lewat 181–365 Hari', '75.00', 6),
    ('over_365', 'Lewat > 365 Hari',   '100.00', 7),
]


def seed_rates(apps, schema_editor):
    PenyisihanRateConfig = apps.get_model('piutang', 'PenyisihanRateConfig')
    for key, label, rate, urutan in DEFAULT_RATES:
        PenyisihanRateConfig.objects.get_or_create(
            bucket_key=key,
            defaults={'label': label, 'rate_percent': rate, 'urutan': urutan},
        )


def reverse_seed(apps, schema_editor):
    PenyisihanRateConfig = apps.get_model('piutang', 'PenyisihanRateConfig')
    PenyisihanRateConfig.objects.filter(
        bucket_key__in=[r[0] for r in DEFAULT_RATES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0005_piutang_penyisihan_models'),
    ]
    operations = [
        migrations.RunPython(seed_rates, reverse_seed),
    ]
