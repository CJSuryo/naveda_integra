from decimal import Decimal
from datetime import date
from django.db import migrations


TARIF_SEED = [
    # (jenis_pajak, nama, tarif_persen, faktor_dpp)
    ('ppn_umum',             'PPN Umum — DPP Nilai Lain PMK 131/2024',  Decimal('12.0000'), Decimal('0.916667')),
    ('ppn_mewah',            'PPN Mewah (BKP Mewah)',                    Decimal('12.0000'), Decimal('1.000000')),
    ('ppn_ekspor',           'PPN Ekspor',                               Decimal('0.0000'),  Decimal('1.000000')),
    ('ppn_bm',               'PPnBM',                                    Decimal('10.0000'), Decimal('1.000000')),
    ('pph_23_jasa',          'PPh 23 Jasa',                              Decimal('2.0000'),  Decimal('1.000000')),
    ('pph_23_royalti',       'PPh 23 Royalti',                           Decimal('15.0000'), Decimal('1.000000')),
    ('pph_23_dividen',       'PPh 23 Dividen',                           Decimal('15.0000'), Decimal('1.000000')),
    ('pph_21_bukan_pegawai', 'PPh 21 Bukan Pegawai (lihat hitung_progresif)', Decimal('0.0000'), Decimal('1.000000')),
    ('pph_4_2_sewa',         'PPh 4(2) Sewa Tanah/Bangunan',            Decimal('10.0000'), Decimal('1.000000')),
    ('pph_4_2_bunga',        'PPh 4(2) Bunga Deposito',                 Decimal('20.0000'), Decimal('1.000000')),
    ('pph_umkm',             'PPh Final UMKM (PP 55/2022, PP 20/2026)', Decimal('0.5000'),  Decimal('1.000000')),
]

BRACKET_SEED = [
    # (batas_bawah, batas_atas, tarif_persen)
    (Decimal('0'),              Decimal('60000000'),    Decimal('5.00')),
    (Decimal('60000001'),       Decimal('250000000'),   Decimal('15.00')),
    (Decimal('250000001'),      Decimal('500000000'),   Decimal('25.00')),
    (Decimal('500000001'),      Decimal('5000000000'),  Decimal('30.00')),
    (Decimal('5000000001'),     None,                   Decimal('35.00')),
]

BERLAKU_MULAI_TARIF   = date(2025, 1, 1)
BERLAKU_MULAI_BRACKET = date(2022, 1, 1)


def seed_forward(apps, schema_editor):
    TarifPajak   = apps.get_model('pajak', 'TarifPajak')
    BracketPPhOP = apps.get_model('pajak', 'BracketPPhOP')

    for jenis, nama, tarif, faktor in TARIF_SEED:
        TarifPajak.objects.create(
            jenis_pajak=jenis,
            nama=nama,
            tarif_persen=tarif,
            faktor_dpp=faktor,
            berlaku_mulai=BERLAKU_MULAI_TARIF,
        )

    for bawah, atas, tarif in BRACKET_SEED:
        BracketPPhOP.objects.create(
            batas_bawah=bawah,
            batas_atas=atas,
            tarif_persen=tarif,
            berlaku_mulai=BERLAKU_MULAI_BRACKET,
        )


def seed_backward(apps, schema_editor):
    TarifPajak   = apps.get_model('pajak', 'TarifPajak')
    BracketPPhOP = apps.get_model('pajak', 'BracketPPhOP')
    TarifPajak.objects.filter(berlaku_mulai=BERLAKU_MULAI_TARIF).delete()
    BracketPPhOP.objects.filter(berlaku_mulai=BERLAKU_MULAI_BRACKET).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pajak', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
