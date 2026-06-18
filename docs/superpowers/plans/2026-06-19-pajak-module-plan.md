# Pajak Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `apps/pajak` as a centralized tax management hub — computation engine, transaction ledger, journal posting, and master rate data — and refactor `apps/pendapatan` to delegate all tax logic to the new module.

**Architecture:** `apps/pajak` owns all tax logic (TarifPajak master data, PajakTransaksi ledger, MasaPajak period lock, BracketPPhOP progressive brackets). Other modules call `sync_pajak → confirm_pajak` after their own main journal, and `batal_pajak` on void. `apps/pendapatan` is the only module refactored in this phase; integration with sales/purchase/piutang/utang is scheduled for later phases. All journal entries use `JurnalHeader`/`JurnalDetail` from `apps/jurnal`.

**Tech Stack:** Django 6.x, Python 3.12, `decimal.Decimal`, `ROUND_HALF_UP`, `apps/jurnal` for journal entries, `apps/master_data.Akun` for chart of accounts.

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `apps/pajak/__init__.py` | App package marker |
| `apps/pajak/apps.py` | AppConfig (`name='apps.pajak'`, `verbose_name='Pajak'`) |
| `apps/pajak/exceptions.py` | `TarifPajakTidakDitemukan`, `MasaPajakTerkunciError`, `PajakStatusError` |
| `apps/pajak/models.py` | `TarifPajak`, `BracketPPhOP`, `MasaPajak`, `PajakTransaksi` |
| `apps/pajak/services.py` | `get_tarif_record`, `compute_pajak`, `hitung_progresif`, `sync_pajak`, `confirm_pajak`, `post_jurnal_pajak`, `batal_pajak`, `override_pajak` |
| `apps/pajak/admin.py` | Django admin for all four models |
| `apps/pajak/forms.py` | `OverridePajakForm` for manual intervention |
| `apps/pajak/views.py` | `PajakTransaksiListView`, `PajakTransaksiEditView`, `MasaPajakListView`, `MasaPajakDetailView`, `TarifPajakListView`, `TarifPajakCreateView` |
| `apps/pajak/urls.py` | URL patterns for above views |
| `apps/pajak/migrations/0001_initial.py` | Initial schema migration |
| `apps/pajak/migrations/0002_seed_tarif.py` | Data migration: TarifPajak + BracketPPhOP seed |
| `apps/pajak/tests/__init__.py` | Package marker |
| `apps/pajak/tests/test_services.py` | Unit tests for all service functions |
| `apps/pajak/tests/test_pendapatan_integration.py` | Integration tests for pendapatan refactor |
| `templates/pajak/transaksi_list.html` | PajakTransaksi list with filters |
| `templates/pajak/transaksi_edit.html` | Override form |
| `templates/pajak/masa_list.html` | MasaPajak list |
| `templates/pajak/masa_detail.html` | MasaPajak detail + lock button |
| `templates/pajak/tarif_list.html` | TarifPajak list |
| `templates/pajak/tarif_form.html` | TarifPajak create form |

### Modified files
| File | Change |
|------|--------|
| `naveda_integra/settings/base.py` | Add `'apps.pajak'` to `INSTALLED_APPS` |
| `naveda_integra/urls.py` | Add `path('pajak/', include('apps.pajak.urls', namespace='pajak'))` |
| `apps/pendapatan/services.py` | Refactor `_create_kp_journal` (remove include_tax), add `sync_pajak+confirm_pajak` calls in `confirm_pendapatan`, add `batal_pajak` calls in `void_pendapatan` |

---

## Task 1: App Scaffold + Exceptions

**Files:**
- Create: `apps/pajak/__init__.py`
- Create: `apps/pajak/apps.py`
- Create: `apps/pajak/exceptions.py`

- [ ] **Step 1: Create app package files**

`apps/pajak/__init__.py` — empty file.

`apps/pajak/apps.py`:
```python
from django.apps import AppConfig


class PajakConfig(AppConfig):
    name = 'apps.pajak'
    verbose_name = 'Pajak'
```

`apps/pajak/exceptions.py`:
```python
class TarifPajakTidakDitemukan(Exception):
    """No active TarifPajak found for given jenis_pajak and date."""


class MasaPajakTerkunciError(Exception):
    """Attempted to post to a locked MasaPajak period."""


class PajakStatusError(Exception):
    """PajakTransaksi is in an invalid status for the requested operation."""
```

- [ ] **Step 2: Register app in INSTALLED_APPS**

In `naveda_integra/settings/base.py`, add `'apps.pajak'` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'apps.pajak',
    ...
]
```

- [ ] **Step 3: Write a smoke test to verify the app loads**

In `apps/pajak/tests/__init__.py` — empty file.

In `apps/pajak/tests/test_services.py`:
```python
from django.test import TestCase
from apps.pajak.exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError


class ExceptionSmokeTest(TestCase):
    def test_exceptions_importable(self):
        self.assertTrue(issubclass(TarifPajakTidakDitemukan, Exception))
        self.assertTrue(issubclass(MasaPajakTerkunciError, Exception))
        self.assertTrue(issubclass(PajakStatusError, Exception))
```

- [ ] **Step 4: Run test**

```
python manage.py test apps.pajak.tests.test_services.ExceptionSmokeTest --settings=naveda_integra.settings.test
```

Expected: 1 test passed.

- [ ] **Step 5: Commit**

```bash
git add apps/pajak/ naveda_integra/settings/base.py
git commit -m "feat(pajak): scaffold app, AppConfig, exceptions"
```

---

## Task 2: Models

**Files:**
- Create: `apps/pajak/models.py`
- Create: `apps/pajak/migrations/0001_initial.py` (auto-generated)

- [ ] **Step 1: Write failing test for model creation**

In `apps/pajak/tests/test_services.py`, add after the existing class:
```python
from datetime import date
from decimal import Decimal


class TarifPajakModelTest(TestCase):
    def test_create_tarif_pajak(self):
        from apps.pajak.models import TarifPajak
        t = TarifPajak.objects.create(
            jenis_pajak='ppn_umum',
            nama='PPN Umum',
            tarif_persen=Decimal('12.0000'),
            faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )
        self.assertEqual(t.jenis_pajak, 'ppn_umum')
        self.assertIsNone(t.berlaku_sampai)

    def test_create_masa_pajak_unique(self):
        from apps.pajak.models import MasaPajak
        mp, created = MasaPajak.objects.get_or_create(tahun=2026, bulan=6)
        self.assertTrue(created)
        mp2, created2 = MasaPajak.objects.get_or_create(tahun=2026, bulan=6)
        self.assertFalse(created2)
        self.assertEqual(mp.pk, mp2.pk)

    def test_create_pajak_transaksi(self):
        from apps.pajak.models import TarifPajak, MasaPajak, PajakTransaksi
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp',
            source_id=1,
            masa_pajak=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            dpp=Decimal('10000000.0000'),
            tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000.0000'),
            sifat_pajak='potong_pungut',
            status='draft',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
        )
        self.assertEqual(pt.status, 'draft')
        self.assertFalse(pt.is_overridden)
        self.assertIsNone(pt.jurnal_header)
```

- [ ] **Step 2: Run test — expect ImportError (models not created yet)**

```
python manage.py test apps.pajak.tests.test_services.TarifPajakModelTest --settings=naveda_integra.settings.test
```

Expected: ERROR — `ModuleNotFoundError` or similar.

- [ ] **Step 3: Write models**

`apps/pajak/models.py`:
```python
from decimal import Decimal
from django.conf import settings
from django.db import models


JENIS_PAJAK_CHOICES = [
    ('ppn_umum',              'PPN Umum (BKP/JKP non-mewah)'),
    ('ppn_mewah',             'PPN Mewah (BKP Mewah 12%)'),
    ('ppn_ekspor',            'PPN Ekspor (0%)'),
    ('ppn_bm',                'PPnBM'),
    ('pph_23_jasa',           'PPh 23 Jasa (2%)'),
    ('pph_23_royalti',        'PPh 23 Royalti (15%)'),
    ('pph_23_dividen',        'PPh 23 Dividen (15%)'),
    ('pph_21_bukan_pegawai',  'PPh 21 Bukan Pegawai (progresif)'),
    ('pph_4_2_sewa',          'PPh 4(2) Sewa Tanah/Bangunan (10%)'),
    ('pph_4_2_bunga',         'PPh 4(2) Bunga Deposito (20%)'),
    ('pph_umkm',              'PPh Final UMKM (0,5%)'),
]

SOURCE_TYPE_CHOICES = [
    ('pendapatan_kp', 'Pendapatan — Kewajiban Pelaksanaan'),
    ('sales_item',    'Sales Item'),
    ('purchase_item', 'Purchase Item'),
    ('piutang_item',  'Piutang Item'),
    ('utang_item',    'Utang Item'),
]

SIFAT_PAJAK_CHOICES = [
    ('potong_pungut', 'Potong/Pungut — Dr akun_lawan | Cr akun_pajak'),
    ('prepaid',       'Prepaid/Dipotong Lawan — Dr akun_pajak | Cr akun_lawan'),
]

STATUS_CHOICES = [
    ('draft',      'Draft'),
    ('final',      'Final'),
    ('disetor',    'Disetor'),
    ('dibatalkan', 'Dibatalkan'),
]


class TarifPajak(models.Model):
    jenis_pajak    = models.CharField(max_length=40, choices=JENIS_PAJAK_CHOICES, db_index=True)
    nama           = models.CharField(max_length=100)
    tarif_persen   = models.DecimalField(max_digits=7, decimal_places=4)
    faktor_dpp     = models.DecimalField(
        max_digits=7, decimal_places=6, default=Decimal('1.000000'),
        help_text='Pengali DPP sebelum tarif diterapkan. ppn_umum (PMK 131/2024): 11/12 ≈ 0.916667',
    )
    berlaku_mulai  = models.DateField()
    berlaku_sampai = models.DateField(null=True, blank=True)
    keterangan     = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Tarif Pajak'
        verbose_name_plural = 'Tarif Pajak'
        indexes = [
            models.Index(fields=['jenis_pajak', 'berlaku_mulai'], name='idx_tarif_jenis_mulai'),
        ]

    def __str__(self):
        return f'{self.get_jenis_pajak_display()} — {self.tarif_persen}% (berlaku {self.berlaku_mulai})'


class BracketPPhOP(models.Model):
    batas_bawah   = models.DecimalField(max_digits=19, decimal_places=0)
    batas_atas    = models.DecimalField(max_digits=19, decimal_places=0, null=True, blank=True)
    tarif_persen  = models.DecimalField(max_digits=5, decimal_places=2)
    berlaku_mulai = models.DateField()

    class Meta:
        verbose_name = 'Bracket PPh OP'
        verbose_name_plural = 'Bracket PPh OP'
        ordering = ['berlaku_mulai', 'batas_bawah']

    def __str__(self):
        atas = f'{self.batas_atas:,}' if self.batas_atas else '∞'
        return f'{self.batas_bawah:,} – {atas} → {self.tarif_persen}%'


class MasaPajak(models.Model):
    tahun  = models.PositiveSmallIntegerField()
    bulan  = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=[('open', 'Open'), ('locked', 'Locked')], default='open')

    class Meta:
        verbose_name = 'Masa Pajak'
        verbose_name_plural = 'Masa Pajak'
        unique_together = ('tahun', 'bulan')
        ordering = ['-tahun', '-bulan']

    def __str__(self):
        return f'{self.tahun}-{self.bulan:02d} ({self.status})'


class PajakTransaksi(models.Model):
    source_type    = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
    source_id      = models.PositiveIntegerField(db_index=True)
    masa_pajak     = models.DateField(db_index=True)
    jenis_pajak    = models.CharField(max_length=40, choices=JENIS_PAJAK_CHOICES)
    dpp            = models.DecimalField(max_digits=19, decimal_places=4)
    tarif_persen   = models.DecimalField(max_digits=7, decimal_places=4)
    jumlah_pajak   = models.DecimalField(max_digits=19, decimal_places=4)
    sifat_pajak    = models.CharField(max_length=20, choices=SIFAT_PAJAK_CHOICES)
    status         = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    is_overridden  = models.BooleanField(default=False)
    akun_pajak     = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pajak_transaksi_pajak_set',
    )
    akun_lawan     = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pajak_transaksi_lawan_set',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_set',
    )
    jurnal_header  = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_set',
    )
    created_at     = models.DateTimeField(auto_now_add=True)
    modified_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pajak_transaksi_modified_set',
    )
    modified_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Pajak Transaksi'
        verbose_name_plural = 'Pajak Transaksi'
        indexes = [
            models.Index(fields=['source_type', 'source_id'], name='idx_pajak_trx_source'),
            models.Index(fields=['masa_pajak', 'jenis_pajak'], name='idx_pajak_trx_masa_jenis'),
            models.Index(fields=['status'], name='idx_pajak_trx_status'),
        ]

    def __str__(self):
        return f'{self.get_jenis_pajak_display()} — {self.source_type}:{self.source_id} — {self.jumlah_pajak}'
```

- [ ] **Step 4: Create and apply migration**

```
python manage.py makemigrations pajak --settings=naveda_integra.settings.test
python manage.py migrate --settings=naveda_integra.settings.test
```

Expected: migration created and applied with no errors.

- [ ] **Step 5: Run model tests**

```
python manage.py test apps.pajak.tests.test_services.TarifPajakModelTest --settings=naveda_integra.settings.test
```

Expected: 3 tests passed.

- [ ] **Step 6: Commit**

```bash
git add apps/pajak/models.py apps/pajak/migrations/
git commit -m "feat(pajak): add TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi models"
```

---

## Task 3: Migration + Seed Data

**Files:**
- Create: `apps/pajak/migrations/0002_seed_tarif.py`

- [ ] **Step 1: Write failing test for seed data**

In `apps/pajak/tests/test_services.py`, add:
```python
class SeedDataTest(TestCase):
    """These tests run after data migration — relies on test runner applying all migrations."""
    fixtures = []  # no fixtures; seed comes from data migration

    def test_tarif_ppn_umum_exists(self):
        from apps.pajak.models import TarifPajak
        from decimal import Decimal
        t = TarifPajak.objects.get(jenis_pajak='ppn_umum', berlaku_sampai__isnull=True)
        self.assertEqual(t.tarif_persen, Decimal('12.0000'))
        self.assertAlmostEqual(float(t.faktor_dpp), 11/12, places=4)

    def test_tarif_pph_23_jasa_exists(self):
        from apps.pajak.models import TarifPajak
        t = TarifPajak.objects.get(jenis_pajak='pph_23_jasa', berlaku_sampai__isnull=True)
        self.assertEqual(t.tarif_persen, Decimal('2.0000'))
        self.assertEqual(t.faktor_dpp, Decimal('1.000000'))

    def test_bracket_ppn_op_five_layers(self):
        from apps.pajak.models import BracketPPhOP
        self.assertEqual(BracketPPhOP.objects.count(), 5)

    def test_bracket_top_layer_null_atas(self):
        from apps.pajak.models import BracketPPhOP
        top = BracketPPhOP.objects.order_by('-batas_bawah').first()
        self.assertIsNone(top.batas_atas)
        self.assertEqual(top.tarif_persen, Decimal('35.00'))
```

- [ ] **Step 2: Run — expect failure (no seed yet)**

```
python manage.py test apps.pajak.tests.test_services.SeedDataTest --settings=naveda_integra.settings.test
```

Expected: DoesNotExist errors.

- [ ] **Step 3: Write data migration**

`apps/pajak/migrations/0002_seed_tarif.py`:
```python
from decimal import Decimal
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

from datetime import date
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
```

- [ ] **Step 4: Apply migration**

```
python manage.py migrate --settings=naveda_integra.settings.test
```

- [ ] **Step 5: Run seed tests**

```
python manage.py test apps.pajak.tests.test_services.SeedDataTest --settings=naveda_integra.settings.test
```

Expected: 4 tests passed.

- [ ] **Step 6: Commit**

```bash
git add apps/pajak/migrations/0002_seed_tarif.py apps/pajak/tests/test_services.py
git commit -m "feat(pajak): add TarifPajak + BracketPPhOP seed data migration"
```

---

## Task 4: `get_tarif_record` and `compute_pajak` (PPN)

**Files:**
- Create: `apps/pajak/services.py` (start of file through `compute_pajak`)

- [ ] **Step 1: Write failing tests**

In `apps/pajak/tests/test_services.py`, add:
```python
class GetTarifRecordTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa',
            nama='PPh 23 Jasa',
            tarif_persen=Decimal('2.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa',
            nama='PPh 23 Jasa (lama)',
            tarif_persen=Decimal('2.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2020, 1, 1),
            berlaku_sampai=date(2024, 12, 31),
        )

    def test_get_tarif_returns_active_record(self):
        from apps.pajak.services import get_tarif_record
        t = get_tarif_record('pph_23_jasa', date(2026, 1, 1))
        self.assertEqual(t.berlaku_mulai, date(2025, 1, 1))

    def test_get_tarif_raises_if_not_found(self):
        from apps.pajak.services import get_tarif_record
        from apps.pajak.exceptions import TarifPajakTidakDitemukan
        with self.assertRaises(TarifPajakTidakDitemukan):
            get_tarif_record('ppn_bm', date(2019, 1, 1))

    def test_get_tarif_historical_date(self):
        from apps.pajak.services import get_tarif_record
        t = get_tarif_record('pph_23_jasa', date(2023, 6, 1))
        self.assertEqual(t.berlaku_mulai, date(2020, 1, 1))


class ComputePajakPPNTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='ppn_umum',
            nama='PPN Umum',
            tarif_persen=Decimal('12.0000'),
            faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='ppn_ekspor',
            nama='PPN Ekspor',
            tarif_persen=Decimal('0.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )

    def test_ppn_umum_effective_11_percent(self):
        from apps.pajak.services import compute_pajak
        # DPP = 10_000_000 → DPP efektif = 9_166_670 → pajak = 9_166_670 × 12% = 1_100_000.40
        result = compute_pajak('ppn_umum', Decimal('10000000'), date(2026, 1, 1))
        self.assertIn('jumlah_pajak', result)
        self.assertIn('dpp_efektif', result)
        self.assertIn('tarif_persen', result)
        # Effective rate ≈ 11% of original DPP
        self.assertAlmostEqual(float(result['jumlah_pajak']), 10_000_000 * 11 / 12 * 0.12, places=0)

    def test_ppn_ekspor_zero(self):
        from apps.pajak.services import compute_pajak
        result = compute_pajak('ppn_ekspor', Decimal('5000000'), date(2026, 1, 1))
        self.assertEqual(result['jumlah_pajak'], Decimal('0'))
```

- [ ] **Step 2: Run — expect ImportError**

```
python manage.py test apps.pajak.tests.test_services.GetTarifRecordTest apps.pajak.tests.test_services.ComputePajakPPNTest --settings=naveda_integra.settings.test
```

Expected: ImportError (services.py does not exist).

- [ ] **Step 3: Create `apps/pajak/services.py`** with `get_tarif_record` and start of `compute_pajak`

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from .exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError
from .models import TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi


def get_tarif_record(jenis_pajak: str, tanggal: date) -> TarifPajak:
    """Return the active TarifPajak record for jenis_pajak on tanggal."""
    qs = (
        TarifPajak.objects
        .filter(jenis_pajak=jenis_pajak, berlaku_mulai__lte=tanggal)
        .filter(Q(berlaku_sampai__gte=tanggal) | Q(berlaku_sampai__isnull=True))
    )
    try:
        return qs.latest('berlaku_mulai')
    except TarifPajak.DoesNotExist:
        raise TarifPajakTidakDitemukan(
            f'Tidak ada tarif aktif untuk {jenis_pajak} pada {tanggal}.'
        )


def compute_pajak(jenis_pajak: str, dpp: Decimal, tanggal: date) -> dict:
    """
    Compute tax for jenis_pajak on dpp at tanggal.

    Returns dict with keys: dpp_efektif, tarif_persen, jumlah_pajak.
    pph_21_bukan_pegawai uses hitung_progresif; all others use faktor_dpp × tarif_persen.
    """
    if jenis_pajak == 'pph_21_bukan_pegawai':
        pkp = dpp * Decimal('0.50')
        jumlah = hitung_progresif(pkp, tanggal)
        tarif_record = get_tarif_record(jenis_pajak, tanggal)
        return {
            'dpp_efektif': pkp,
            'tarif_persen': tarif_record.tarif_persen,
            'jumlah_pajak': jumlah,
        }

    tarif_record = get_tarif_record(jenis_pajak, tanggal)
    dpp_efektif  = dpp * tarif_record.faktor_dpp
    jumlah       = dpp_efektif * tarif_record.tarif_persen / Decimal('100')

    return {
        'dpp_efektif':  dpp_efektif,
        'tarif_persen': tarif_record.tarif_persen,
        'jumlah_pajak': jumlah,
    }


def hitung_progresif(pkp: Decimal, tanggal: date) -> Decimal:
    """Apply progressive Pasal 17 brackets to pkp. Returns total tax."""
    brackets = BracketPPhOP.objects.filter(berlaku_mulai__lte=tanggal).order_by('berlaku_mulai', 'batas_bawah')
    # Use the most recent set of brackets (latest berlaku_mulai)
    latest_mulai = brackets.values_list('berlaku_mulai', flat=True).order_by('-berlaku_mulai').first()
    if not latest_mulai:
        return Decimal('0')
    brackets = brackets.filter(berlaku_mulai=latest_mulai)

    total = Decimal('0')
    remaining = pkp
    for bracket in brackets:
        if remaining <= 0:
            break
        lower = bracket.batas_bawah
        upper = bracket.batas_atas
        layer_width = (upper - lower + 1) if upper is not None else remaining
        taxable = min(remaining, layer_width)
        total += taxable * bracket.tarif_persen / Decimal('100')
        remaining -= taxable
    return total
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.pajak.tests.test_services.GetTarifRecordTest apps.pajak.tests.test_services.ComputePajakPPNTest --settings=naveda_integra.settings.test
```

Expected: 5 tests passed.

- [ ] **Step 5: Commit**

```bash
git add apps/pajak/services.py apps/pajak/tests/test_services.py
git commit -m "feat(pajak): add get_tarif_record, compute_pajak, hitung_progresif"
```

---

## Task 5: `compute_pajak` PPh + `hitung_progresif` Tests

**Files:**
- Modify: `apps/pajak/tests/test_services.py`

- [ ] **Step 1: Write tests for PPh 23 and PPh 21 progressive**

In `apps/pajak/tests/test_services.py`, add:
```python
class ComputePajakPPhTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak, BracketPPhOP
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa', nama='PPh 23 Jasa',
            tarif_persen=Decimal('2.0000'), faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='pph_21_bukan_pegawai', nama='PPh 21 Bukan Pegawai',
            tarif_persen=Decimal('0.0000'), faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        BracketPPhOP.objects.bulk_create([
            BracketPPhOP(batas_bawah=Decimal('0'),         batas_atas=Decimal('60000000'),   tarif_persen=Decimal('5.00'),  berlaku_mulai=date(2022, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('60000001'),  batas_atas=Decimal('250000000'),  tarif_persen=Decimal('15.00'), berlaku_mulai=date(2022, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('250000001'), batas_atas=Decimal('500000000'),  tarif_persen=Decimal('25.00'), berlaku_mulai=date(2022, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('500000001'), batas_atas=Decimal('5000000000'), tarif_persen=Decimal('30.00'), berlaku_mulai=date(2022, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('5000000001'),batas_atas=None,                  tarif_persen=Decimal('35.00'), berlaku_mulai=date(2022, 1, 1)),
        ])

    def test_pph_23_jasa_flat_rate(self):
        from apps.pajak.services import compute_pajak
        result = compute_pajak('pph_23_jasa', Decimal('5000000'), date(2026, 1, 1))
        # 5_000_000 × 1.0 × 2% = 100_000
        self.assertEqual(result['jumlah_pajak'], Decimal('100000.00'))

    def test_pph_21_bukan_pegawai_single_bracket(self):
        from apps.pajak.services import compute_pajak
        # bruto = 10_000_000 → PKP = 5_000_000 → 5% bracket → tax = 250_000
        result = compute_pajak('pph_21_bukan_pegawai', Decimal('10000000'), date(2026, 1, 1))
        self.assertEqual(result['jumlah_pajak'], Decimal('250000.00'))

    def test_pph_21_bukan_pegawai_two_brackets(self):
        from apps.pajak.services import compute_pajak
        # bruto = 300_000_000 → PKP = 150_000_000
        # Layer 1: 60_000_000 × 5% = 3_000_000
        # Layer 2: 90_000_000 × 15% = 13_500_000
        # Total = 16_500_000
        result = compute_pajak('pph_21_bukan_pegawai', Decimal('300000000'), date(2026, 1, 1))
        self.assertEqual(result['jumlah_pajak'], Decimal('16500000.00'))
```

- [ ] **Step 2: Run tests**

```
python manage.py test apps.pajak.tests.test_services.ComputePajakPPhTest --settings=naveda_integra.settings.test
```

Expected: 3 tests passed.

- [ ] **Step 3: Commit**

```bash
git add apps/pajak/tests/test_services.py
git commit -m "test(pajak): add PPh 23, PPh 21 progressive compute tests"
```

---

## Task 6: `sync_pajak` + MasaPajak Lock Guard

**Files:**
- Modify: `apps/pajak/services.py` (add `sync_pajak`)

- [ ] **Step 1: Write failing tests**

In `apps/pajak/tests/test_services.py`, add:
```python
class SyncPajakTest(TestCase):
    def _make_accounts(self):
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
        return akun_pajak, akun_lawan

    def _make_tarif(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='ppn_umum', nama='PPN Umum',
            tarif_persen=Decimal('12.0000'), faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )

    def test_sync_pajak_creates_draft_record(self):
        from apps.pajak.services import sync_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()

        class FakeKP:
            pk = 42
            tax = None
            entitas_bisnis = None

        pt = sync_pajak(
            source_type='pendapatan_kp',
            source_obj=FakeKP(),
            dpp=Decimal('10000000'),
            tanggal=date(2026, 6, 15),
            jenis_pajak='ppn_umum',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
            sifat_pajak='potong_pungut',
        )
        self.assertEqual(pt.status, 'draft')
        self.assertEqual(pt.source_type, 'pendapatan_kp')
        self.assertEqual(pt.source_id, 42)
        self.assertEqual(pt.masa_pajak, date(2026, 6, 1))
        self.assertFalse(pt.is_overridden)
        self.assertTrue(MasaPajak.objects.filter(tahun=2026, bulan=6).exists())

    def test_sync_pajak_locked_masa_raises(self):
        from apps.pajak.services import sync_pajak
        from apps.pajak.models import MasaPajak
        from apps.pajak.exceptions import MasaPajakTerkunciError
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()
        MasaPajak.objects.create(tahun=2026, bulan=6, status='locked')

        class FakeKP:
            pk = 1
            tax = None
            entitas_bisnis = None

        with self.assertRaises(MasaPajakTerkunciError):
            sync_pajak(
                source_type='pendapatan_kp',
                source_obj=FakeKP(),
                dpp=Decimal('10000000'),
                tanggal=date(2026, 6, 1),
                jenis_pajak='ppn_umum',
                akun_pajak=akun_pajak,
                akun_lawan=akun_lawan,
                sifat_pajak='potong_pungut',
            )

    def test_sync_pajak_manual_tax_sets_overridden(self):
        from apps.pajak.services import sync_pajak
        from apps.pajak.models import TarifPajak
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()

        class FakeKP:
            pk = 7
            tax = Decimal('500000')
            entitas_bisnis = None

        pt = sync_pajak(
            source_type='pendapatan_kp',
            source_obj=FakeKP(),
            dpp=Decimal('5000000'),
            tanggal=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
            sifat_pajak='potong_pungut',
        )
        self.assertTrue(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('500000'))
```

- [ ] **Step 2: Run — expect ImportError for sync_pajak**

```
python manage.py test apps.pajak.tests.test_services.SyncPajakTest --settings=naveda_integra.settings.test
```

Expected: ImportError.

- [ ] **Step 3: Add `sync_pajak` to `apps/pajak/services.py`**

Append to services.py after `hitung_progresif`:
```python
def sync_pajak(
    source_type: str,
    source_obj,
    dpp: Decimal,
    tanggal: date,
    jenis_pajak: str,
    akun_pajak,
    akun_lawan,
    sifat_pajak: str,
) -> PajakTransaksi:
    """
    Create a draft PajakTransaksi for source_obj.

    If source_obj.tax is set (manual override), use that value and mark is_overridden=True.
    Otherwise, compute from TarifPajak.
    Raises MasaPajakTerkunciError if the target period is locked.
    """
    masa_date = tanggal.replace(day=1)
    masa, _ = MasaPajak.objects.get_or_create(
        tahun=masa_date.year, bulan=masa_date.month,
        defaults={'status': 'open'},
    )
    if masa.status == 'locked':
        raise MasaPajakTerkunciError(
            f'Masa pajak {masa_date:%Y-%m} sudah terkunci. '
            'Buka kunci terlebih dahulu sebelum memposting transaksi baru.'
        )

    manual_tax = getattr(source_obj, 'tax', None)
    if manual_tax and manual_tax > 0:
        jumlah_pajak = manual_tax
        tarif_persen = Decimal('0')
        is_overridden = True
    else:
        hasil = compute_pajak(jenis_pajak, dpp, tanggal)
        jumlah_pajak = hasil['jumlah_pajak']
        tarif_persen = hasil['tarif_persen']
        is_overridden = False

    return PajakTransaksi.objects.create(
        source_type=source_type,
        source_id=source_obj.pk,
        masa_pajak=masa_date,
        jenis_pajak=jenis_pajak,
        dpp=dpp,
        tarif_persen=tarif_persen,
        jumlah_pajak=jumlah_pajak,
        sifat_pajak=sifat_pajak,
        status='draft',
        is_overridden=is_overridden,
        akun_pajak=akun_pajak,
        akun_lawan=akun_lawan,
        entitas_bisnis=getattr(source_obj, 'entitas_bisnis', None),
    )
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.pajak.tests.test_services.SyncPajakTest --settings=naveda_integra.settings.test
```

Expected: 3 tests passed.

- [ ] **Step 5: Commit**

```bash
git add apps/pajak/services.py apps/pajak/tests/test_services.py
git commit -m "feat(pajak): add sync_pajak with MasaPajak lock guard"
```

---

## Task 7: `post_jurnal_pajak` + `confirm_pajak`

**Files:**
- Modify: `apps/pajak/services.py`

- [ ] **Step 1: Write failing tests**

In `apps/pajak/tests/test_services.py`, add:
```python
class PostJurnalPajakTest(TestCase):
    def _make_pt(self, sifat_pajak, jumlah=Decimal('1100000')):
        from apps.pajak.models import PajakTransaksi
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
        return PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=jumlah,
            sifat_pajak=sifat_pajak,
            status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )

    def test_post_jurnal_potong_pungut_direction(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        pt = self._make_pt('potong_pungut')
        jh = post_jurnal_pajak(pt)
        details = list(JurnalDetail.objects.filter(jurnal_header=jh))
        self.assertEqual(len(details), 2)
        debit_detail  = next(d for d in details if d.debit  > 0)
        kredit_detail = next(d for d in details if d.kredit > 0)
        self.assertEqual(debit_detail.akun,  pt.akun_lawan)
        self.assertEqual(kredit_detail.akun, pt.akun_pajak)

    def test_post_jurnal_prepaid_direction(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        pt = self._make_pt('prepaid')
        jh = post_jurnal_pajak(pt)
        details = list(JurnalDetail.objects.filter(jurnal_header=jh))
        debit_detail  = next(d for d in details if d.debit  > 0)
        kredit_detail = next(d for d in details if d.kredit > 0)
        self.assertEqual(debit_detail.akun,  pt.akun_pajak)
        self.assertEqual(kredit_detail.akun, pt.akun_lawan)

    def test_post_jurnal_rounding_two_decimal_places(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        # jumlah_pajak has 4 decimal places; journal should round to 2
        pt = self._make_pt('potong_pungut', jumlah=Decimal('1100000.5678'))
        jh = post_jurnal_pajak(pt)
        debit = JurnalDetail.objects.filter(jurnal_header=jh, debit__gt=0).first()
        self.assertEqual(debit.debit, Decimal('1100000.57'))

    def test_post_jurnal_nomor_starts_with_trx_paj(self):
        from apps.pajak.services import post_jurnal_pajak
        pt = self._make_pt('potong_pungut')
        jh = post_jurnal_pajak(pt)
        self.assertTrue(jh.nomor_transaksi.startswith('TRX-PAJ'))

    def test_confirm_pajak_sets_final_and_links_jurnal(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import MasaPajak
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        pt = self._make_pt('potong_pungut')
        jh = confirm_pajak(pt)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'final')
        self.assertEqual(pt.jurnal_header, jh)

    def test_confirm_pajak_locked_masa_raises(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import MasaPajak
        from apps.pajak.exceptions import MasaPajakTerkunciError
        MasaPajak.objects.create(tahun=2026, bulan=6, status='locked')
        pt = self._make_pt('potong_pungut')
        with self.assertRaises(MasaPajakTerkunciError):
            confirm_pajak(pt)
```

- [ ] **Step 2: Run — expect ImportError for post_jurnal_pajak**

```
python manage.py test apps.pajak.tests.test_services.PostJurnalPajakTest --settings=naveda_integra.settings.test
```

Expected: ImportError.

- [ ] **Step 3: Add `post_jurnal_pajak` and `confirm_pajak` to services.py**

First, add the import at the top of services.py (after existing imports):
```python
from apps.jurnal.models import JurnalHeader, JurnalDetail
```

Then append the functions:
```python
def _next_pajak_journal_number() -> str:
    """Generate next sequential TRX-PAJ-XXXXXXXX number."""
    prefix = 'TRX-PAJ'
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith=prefix)
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}-{seq:08d}'


def post_jurnal_pajak(pajak_trx: PajakTransaksi) -> JurnalHeader:
    """Create JurnalHeader + 2 JurnalDetail for pajak_trx. Rounding: ROUND_HALF_UP to 2 dp."""
    jumlah = pajak_trx.jumlah_pajak.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    if pajak_trx.sifat_pajak == 'potong_pungut':
        akun_debit  = pajak_trx.akun_lawan
        akun_kredit = pajak_trx.akun_pajak
    else:  # prepaid
        akun_debit  = pajak_trx.akun_pajak
        akun_kredit = pajak_trx.akun_lawan

    nomor = _next_pajak_journal_number()
    jh = JurnalHeader.objects.create(
        tanggal=pajak_trx.masa_pajak,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Jurnal Pajak — {pajak_trx.get_jenis_pajak_display()} '
            f'— {pajak_trx.source_type}:{pajak_trx.source_id}'
        ),
        entitas_bisnis=pajak_trx.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=jh, akun=akun_debit,  debit=jumlah,            kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=akun_kredit, debit=Decimal('0'),       kredit=jumlah),
    ])
    return jh


def confirm_pajak(pajak_trx: PajakTransaksi) -> JurnalHeader:
    """Validate draft status + unlocked period, set final, post journal."""
    if pajak_trx.status != 'draft':
        raise PajakStatusError(
            f'PajakTransaksi {pajak_trx.pk} berstatus "{pajak_trx.status}", bukan "draft".'
        )
    masa_date = pajak_trx.masa_pajak
    try:
        masa = MasaPajak.objects.get(tahun=masa_date.year, bulan=masa_date.month)
        if masa.status == 'locked':
            raise MasaPajakTerkunciError(
                f'Masa pajak {masa_date:%Y-%m} sudah terkunci.'
            )
    except MasaPajak.DoesNotExist:
        pass  # masa not created yet means open

    jh = post_jurnal_pajak(pajak_trx)
    pajak_trx.jurnal_header = jh
    pajak_trx.status = 'final'
    pajak_trx.save(update_fields=['jurnal_header', 'status'])
    return jh
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.pajak.tests.test_services.PostJurnalPajakTest --settings=naveda_integra.settings.test
```

Expected: 6 tests passed.

- [ ] **Step 5: Commit**

```bash
git add apps/pajak/services.py apps/pajak/tests/test_services.py
git commit -m "feat(pajak): add post_jurnal_pajak and confirm_pajak"
```

---

## Task 8: `batal_pajak` + `override_pajak`

**Files:**
- Modify: `apps/pajak/services.py`

- [ ] **Step 1: Write failing tests**

In `apps/pajak/tests/test_services.py`, add:
```python
class BatalPajakTest(TestCase):
    def _make_confirmed_pt(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        from apps.master_data.models import Akun
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1), jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000'),
            sifat_pajak='potong_pungut', status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )
        confirm_pajak(pt)
        pt.refresh_from_db()
        return pt

    def test_batal_pajak_sets_dibatalkan(self):
        from apps.pajak.services import batal_pajak
        pt = self._make_confirmed_pt()
        batal_pajak(pt)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')

    def test_batal_pajak_creates_reversal_journal(self):
        from apps.pajak.services import batal_pajak
        from apps.jurnal.models import JurnalHeader, JurnalDetail
        pt = self._make_confirmed_pt()
        original_jh = pt.jurnal_header
        original_debit = JurnalDetail.objects.filter(jurnal_header=original_jh, debit__gt=0).first()
        batal_pajak(pt)
        # A new journal should have been created with swapped debit/kredit
        reversal_jh = JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-PAJ').exclude(pk=original_jh.pk).first()
        self.assertIsNotNone(reversal_jh)
        reversal_kredit = JurnalDetail.objects.filter(jurnal_header=reversal_jh, kredit__gt=0, akun=original_debit.akun).first()
        self.assertIsNotNone(reversal_kredit)
        self.assertEqual(reversal_kredit.kredit, original_debit.debit)


class OverridePajakTest(TestCase):
    def _make_confirmed_pt(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        from apps.master_data.models import Akun
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1), jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000'),
            sifat_pajak='potong_pungut', status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )
        confirm_pajak(pt)
        pt.refresh_from_db()
        return pt

    def test_override_updates_amount_and_posts_new_journal(self):
        from apps.pajak.services import override_pajak
        from apps.jurnal.models import JurnalHeader
        pt = self._make_confirmed_pt()
        original_jh_pk = pt.jurnal_header.pk
        pt2 = override_pajak(pt, Decimal('900000'), modified_by=None)
        pt2.refresh_from_db()
        self.assertEqual(pt2.jumlah_pajak, Decimal('900000'))
        self.assertTrue(pt2.is_overridden)
        self.assertEqual(pt2.status, 'final')
        self.assertNotEqual(pt2.jurnal_header.pk, original_jh_pk)
```

- [ ] **Step 2: Run — expect ImportError for batal_pajak**

```
python manage.py test apps.pajak.tests.test_services.BatalPajakTest apps.pajak.tests.test_services.OverridePajakTest --settings=naveda_integra.settings.test
```

Expected: ImportError.

- [ ] **Step 3: Add `batal_pajak` and `override_pajak` to services.py**

Append to services.py:
```python
def batal_pajak(pajak_trx: PajakTransaksi) -> None:
    """Cancel pajak_trx and post a reversal journal if one exists."""
    if pajak_trx.jurnal_header_id:
        original_jh = pajak_trx.jurnal_header
        nomor = _next_pajak_journal_number()
        rev_jh = JurnalHeader.objects.create(
            tanggal=original_jh.tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reversal Pajak — {original_jh.nomor_transaksi}',
            entitas_bisnis=original_jh.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=rev_jh,
                akun=d.akun,
                debit=d.kredit,
                kredit=d.debit,
            )
            for d in original_jh.details.all()
        ])
    pajak_trx.status = 'dibatalkan'
    pajak_trx.save(update_fields=['status'])


def override_pajak(pajak_trx: PajakTransaksi, jumlah_baru: Decimal, modified_by=None) -> PajakTransaksi:
    """
    Manual override: reverse existing journal, set new amount, post new journal.
    Works on both draft and final records.
    """
    from django.utils import timezone
    batal_pajak(pajak_trx)
    pajak_trx.jumlah_pajak = jumlah_baru
    pajak_trx.is_overridden = True
    pajak_trx.modified_by = modified_by
    pajak_trx.modified_at = timezone.now()
    pajak_trx.status = 'draft'
    pajak_trx.jurnal_header = None
    pajak_trx.save(update_fields=['jumlah_pajak', 'is_overridden', 'modified_by', 'modified_at', 'status', 'jurnal_header'])
    jh = post_jurnal_pajak(pajak_trx)
    pajak_trx.jurnal_header = jh
    pajak_trx.status = 'final'
    pajak_trx.save(update_fields=['jurnal_header', 'status'])
    return pajak_trx
```

- [ ] **Step 4: Run tests**

```
python manage.py test apps.pajak.tests.test_services.BatalPajakTest apps.pajak.tests.test_services.OverridePajakTest --settings=naveda_integra.settings.test
```

Expected: 4 tests passed.

- [ ] **Step 5: Run full pajak test suite**

```
python manage.py test apps.pajak --settings=naveda_integra.settings.test
```

Expected: all tests passed.

- [ ] **Step 6: Commit**

```bash
git add apps/pajak/services.py apps/pajak/tests/test_services.py
git commit -m "feat(pajak): add batal_pajak, override_pajak"
```

---

## Task 9: Admin

**Files:**
- Create: `apps/pajak/admin.py`

- [ ] **Step 1: Write admin**

`apps/pajak/admin.py`:
```python
from django.contrib import admin
from .models import TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi


@admin.register(TarifPajak)
class TarifPajakAdmin(admin.ModelAdmin):
    list_display  = ('jenis_pajak', 'tarif_persen', 'faktor_dpp', 'berlaku_mulai', 'berlaku_sampai')
    list_filter   = ('jenis_pajak',)
    ordering      = ('jenis_pajak', '-berlaku_mulai')


@admin.register(BracketPPhOP)
class BracketPPhOPAdmin(admin.ModelAdmin):
    list_display = ('batas_bawah', 'batas_atas', 'tarif_persen', 'berlaku_mulai')
    ordering     = ('berlaku_mulai', 'batas_bawah')


@admin.register(MasaPajak)
class MasaPajakAdmin(admin.ModelAdmin):
    list_display = ('tahun', 'bulan', 'status')
    list_filter  = ('status',)
    ordering     = ('-tahun', '-bulan')


@admin.register(PajakTransaksi)
class PajakTransaksiAdmin(admin.ModelAdmin):
    list_display  = ('source_type', 'source_id', 'jenis_pajak', 'masa_pajak', 'jumlah_pajak', 'sifat_pajak', 'status', 'is_overridden')
    list_filter   = ('status', 'jenis_pajak', 'sifat_pajak', 'source_type')
    search_fields = ('source_id',)
    readonly_fields = ('created_at', 'modified_at', 'modified_by')
```

- [ ] **Step 2: Verify admin loads (smoke check)**

```
python manage.py check --settings=naveda_integra.settings.test
```

Expected: System check identified no issues.

- [ ] **Step 3: Commit**

```bash
git add apps/pajak/admin.py
git commit -m "feat(pajak): add admin registrations for all pajak models"
```

---

## Task 10: Refactor `_create_kp_journal` — Remove `include_tax`

**Files:**
- Modify: `apps/pendapatan/services.py`

- [ ] **Step 1: Write failing test for DPP-only journal**

Create `apps/pajak/tests/test_pendapatan_integration.py`:
```python
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType
from apps.pendapatan.services import create_pendapatan_header
from apps.jurnal.models import JurnalDetail


def make_base_fixtures():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Jasa', kode_akun='4.1.1')
    coa_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
    stt = SubTransactionType.objects.create(
        nama='Jasa', module='pendapatan', direction='inflow',
        default_offset_account=coa_revenue,
    )
    return {
        'eb': eb, 'coa_kas': coa_kas, 'coa_piutang': coa_piutang,
        'coa_revenue': coa_revenue, 'coa_ppn': coa_ppn, 'stt': stt,
    }


class CreateKPJournalDPPOnlyTest(TestCase):
    """After refactor, _create_kp_journal must post DPP only — no tax in main journal."""

    def setUp(self):
        self.f = make_base_fixtures()

    def test_main_journal_has_no_tax_line(self):
        from apps.pendapatan.services import confirm_pendapatan
        from apps.pajak.models import TarifPajak

        TarifPajak.objects.create(
            jenis_pajak='ppn_umum', nama='PPN',
            tarif_persen=Decimal('12.0000'), faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )

        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa Konsultasi',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi A',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('10000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_type': 'ppn_keluaran',
                'tax_account': self.f['coa_ppn'],
            }],
        )
        confirm_pendapatan(header)

        # Main journal (TRX-PND-J) should debit only the DPP amount (10_000_000), no tax line
        from apps.jurnal.models import JurnalHeader
        main_jh = JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-PND-J').first()
        self.assertIsNotNone(main_jh)
        main_details = list(JurnalDetail.objects.filter(jurnal_header=main_jh))
        # Only 2 details: Dr Kas (DPP) | Cr Revenue (DPP)
        self.assertEqual(len(main_details), 2)
        total_debit = sum(d.debit for d in main_details)
        self.assertEqual(total_debit, Decimal('10000000'))  # DPP only

    def test_pajak_journal_created_separately(self):
        from apps.pendapatan.services import confirm_pendapatan
        from apps.pajak.models import TarifPajak, PajakTransaksi
        from apps.jurnal.models import JurnalHeader

        TarifPajak.objects.create(
            jenis_pajak='ppn_umum', nama='PPN',
            tarif_persen=Decimal('12.0000'), faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )

        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa Konsultasi 2',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi B',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('10000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_type': 'ppn_keluaran',
                'tax_account': self.f['coa_ppn'],
            }],
        )
        confirm_pendapatan(header)

        # PajakTransaksi must exist with source_type='pendapatan_kp'
        pt = PajakTransaksi.objects.filter(source_type='pendapatan_kp').first()
        self.assertIsNotNone(pt)
        self.assertEqual(pt.status, 'final')
        self.assertIsNotNone(pt.jurnal_header)
        # Pajak journal has TRX-PAJ prefix
        self.assertTrue(pt.jurnal_header.nomor_transaksi.startswith('TRX-PAJ'))
```

- [ ] **Step 2: Run — expect failure (test references fields that may not be in create_pendapatan_header)**

```
python manage.py test apps.pajak.tests.test_pendapatan_integration.CreateKPJournalDPPOnlyTest --settings=naveda_integra.settings.test
```

Note: this will likely fail because `tax_type`/`tax_account` handling in `create_pendapatan_header` and the refactor haven't been applied yet. Record the failure message before proceeding.

- [ ] **Step 3: Refactor `_create_kp_journal` in `apps/pendapatan/services.py`**

Find `_create_kp_journal` (line 338). Replace the entire function:

```python
def _create_kp_journal(header, eb_group, kp, debit_acct, credit_acct, amount, user=None):
    """
    Create main journal for one KP recognition event. Books DPP only.
    Tax is handled separately by apps.pajak.services.
    """
    if debit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun debit untuk pembuatan jurnal.'
        )
    if credit_acct is None:
        raise ValueError(
            f'KP "{kp.deskripsi_item}" tidak memiliki akun kredit untuk pembuatan jurnal.'
        )

    nomor = _next_journal_number('TRX-PND-J')
    jh = JurnalHeader.objects.create(
        tanggal=header.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama} — KP {kp.pk}'
        ),
        entitas_bisnis=eb_group.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=jh, akun=debit_acct,  debit=amount,           kredit=Decimal('0')),
        JurnalDetail(jurnal_header=jh, akun=credit_acct, debit=Decimal('0'),      kredit=amount),
    ])
    _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
    return jh
```

Also remove `include_tax=True` from all three call sites in `confirm_pendapatan` (lines ~263, ~284, ~308 approximately). Each call looks like:
```python
_create_kp_journal(
    header, eb_group, kp,
    debit_acct=pay_acct,
    credit_acct=kp.revenue_account,
    amount=harga_j,
    user=user,
    include_tax=True,   # ← REMOVE this line
)
```

After removal each call should be:
```python
_create_kp_journal(
    header, eb_group, kp,
    debit_acct=pay_acct,
    credit_acct=kp.revenue_account,
    amount=harga_j,
    user=user,
)
```

- [ ] **Step 4: Run existing pendapatan tests to verify no regression**

```
python manage.py test apps.pendapatan --settings=naveda_integra.settings.test
```

Expected: all existing tests pass (the include_tax removal shouldn't break existing tests since the old tests don't pass `tax_type`).

- [ ] **Step 5: Commit**

```bash
git add apps/pendapatan/services.py apps/pajak/tests/test_pendapatan_integration.py
git commit -m "refactor(pendapatan): remove include_tax from _create_kp_journal; main journal books DPP only"
```

---

## Task 11: Pendapatan `confirm_pendapatan` — Integration with `sync_pajak` + `confirm_pajak`

**Files:**
- Modify: `apps/pendapatan/services.py`

- [ ] **Step 1: Add `sync_pajak + confirm_pajak` calls in `confirm_pendapatan`**

At the top of `apps/pendapatan/services.py`, add the import (after existing imports):
```python
TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}
```

Inside `confirm_pendapatan`, after each call to `_create_kp_journal`, add the pajak integration block. For `POINT_IN_TIME` case (Case 1 & 2), the block after the `_create_kp_journal(...)` call should become:

```python
_create_kp_journal(
    header, eb_group, kp,
    debit_acct=pay_acct,
    credit_acct=kp.revenue_account,
    amount=harga_j,
    user=user,
)
_maybe_sync_confirm_pajak(kp, header, pay_acct)
```

For `advance_payment_cash` (Case 3) after its `_create_kp_journal`:
```python
_create_kp_journal(
    header, eb_group, kp,
    debit_acct=pay_acct,
    credit_acct=kp.ot_liabilitas_kontrak_acct,
    amount=harga_j,
    user=user,
)
_maybe_sync_confirm_pajak(kp, header, pay_acct)
```

Add the helper function to `apps/pendapatan/services.py` (just before `_create_kp_journal`):
```python
def _maybe_sync_confirm_pajak(kp, header, pay_acct):
    """If kp has a tax_type and tax_account, create and confirm a PajakTransaksi."""
    from apps.pajak.services import sync_pajak, confirm_pajak
    if not (kp.tax_type and kp.tax_account_id):
        return
    jenis = TAX_TYPE_MAP.get(kp.tax_type)
    if not jenis:
        return
    sifat = 'potong_pungut' if kp.tax_type == 'ppn_keluaran' else 'prepaid'
    pt = sync_pajak(
        source_type='pendapatan_kp',
        source_obj=kp,
        dpp=kp.harga_j,
        tanggal=header.tanggal,
        jenis_pajak=jenis,
        akun_pajak=kp.tax_account,
        akun_lawan=pay_acct,
        sifat_pajak=sifat,
    )
    confirm_pajak(pt)
```

- [ ] **Step 2: Run integration tests**

```
python manage.py test apps.pajak.tests.test_pendapatan_integration --settings=naveda_integra.settings.test
```

Expected: 2 tests passed.

- [ ] **Step 3: Run full pendapatan + pajak suite**

```
python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
```

Expected: all tests passed.

- [ ] **Step 4: Commit**

```bash
git add apps/pendapatan/services.py
git commit -m "feat(pendapatan): integrate sync_pajak+confirm_pajak in confirm_pendapatan"
```

---

## Task 12: Pendapatan `void_pendapatan` — Integration with `batal_pajak`

**Files:**
- Modify: `apps/pendapatan/services.py`

- [ ] **Step 1: Write failing test for void + pajak reversal**

In `apps/pajak/tests/test_pendapatan_integration.py`, add:
```python
class VoidPendapatanBatalPajakTest(TestCase):
    def setUp(self):
        self.f = make_base_fixtures()
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='ppn_umum', nama='PPN',
            tarif_persen=Decimal('12.0000'), faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )

    def _create_confirmed_header(self):
        from apps.pendapatan.services import create_pendapatan_header, confirm_pendapatan
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa void test',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi Void',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('10000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_type': 'ppn_keluaran',
                'tax_account': self.f['coa_ppn'],
            }],
        )
        confirm_pendapatan(header)
        return header

    def test_void_cancels_pajak_transaksi(self):
        from apps.pendapatan.services import void_pendapatan
        from apps.pajak.models import PajakTransaksi
        header = self._create_confirmed_header()
        void_pendapatan(header)
        pt = PajakTransaksi.objects.filter(source_type='pendapatan_kp').first()
        self.assertEqual(pt.status, 'dibatalkan')

    def test_void_creates_reversal_pajak_journal(self):
        from apps.pendapatan.services import void_pendapatan
        from apps.jurnal.models import JurnalHeader
        header = self._create_confirmed_header()
        paj_count_before = JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-PAJ').count()
        void_pendapatan(header)
        paj_count_after = JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-PAJ').count()
        # A reversal journal should have been created
        self.assertGreater(paj_count_after, paj_count_before)
```

- [ ] **Step 2: Run — expect failure (void doesn't call batal_pajak yet)**

```
python manage.py test apps.pajak.tests.test_pendapatan_integration.VoidPendapatanBatalPajakTest --settings=naveda_integra.settings.test
```

Expected: AssertionError (status is 'final', not 'dibatalkan').

- [ ] **Step 3: Add `batal_pajak` calls to `void_pendapatan`**

In `apps/pendapatan/services.py`, inside `void_pendapatan` at the top of the `with transaction.atomic():` block, add this before the existing journal reversal loop:

```python
        # Cancel all linked pajak transaksi (and their journals)
        from apps.pajak.services import batal_pajak
        from apps.pajak.models import PajakTransaksi
        kp_ids = list(
            KewajibabPelaksanaan.objects.filter(
                pendapatan_eb__pendapatan_header=header
            ).values_list('id', flat=True)
        )
        for pt in PajakTransaksi.objects.filter(
            source_type='pendapatan_kp', source_id__in=kp_ids
        ):
            batal_pajak(pt)
```

- [ ] **Step 4: Run void tests**

```
python manage.py test apps.pajak.tests.test_pendapatan_integration.VoidPendapatanBatalPajakTest --settings=naveda_integra.settings.test
```

Expected: 2 tests passed.

- [ ] **Step 5: Run full suite**

```
python manage.py test apps.pendapatan apps.pajak --settings=naveda_integra.settings.test
```

Expected: all tests passed.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/services.py apps/pajak/tests/test_pendapatan_integration.py
git commit -m "feat(pendapatan): call batal_pajak in void_pendapatan for all linked PajakTransaksi"
```

---

## Task 13: URL Routing

**Files:**
- Create: `apps/pajak/urls.py`
- Modify: `naveda_integra/urls.py`

- [ ] **Step 1: Create URL file**

`apps/pajak/urls.py`:
```python
from django.urls import path
from . import views

app_name = 'pajak'

urlpatterns = [
    path('transaksi/',                      views.PajakTransaksiListView.as_view(),   name='transaksi_list'),
    path('transaksi/<int:pk>/edit/',        views.PajakTransaksiEditView.as_view(),   name='transaksi_edit'),
    path('masa/',                           views.MasaPajakListView.as_view(),        name='masa_list'),
    path('masa/<int:tahun>/<int:bulan>/',   views.MasaPajakDetailView.as_view(),     name='masa_detail'),
    path('tarif/',                          views.TarifPajakListView.as_view(),       name='tarif_list'),
    path('tarif/tambah/',                   views.TarifPajakCreateView.as_view(),     name='tarif_create'),
]
```

- [ ] **Step 2: Register in main urls.py**

In `naveda_integra/urls.py`, add after the `pendapatan` line:
```python
    path('pajak/', include('apps.pajak.urls', namespace='pajak')),
```

- [ ] **Step 3: Create stub views to prevent ImportError**

`apps/pajak/views.py`:
```python
from django.views.generic import ListView, UpdateView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy

from .models import PajakTransaksi, MasaPajak, TarifPajak
from .forms import OverridePajakForm, TarifPajakForm


class PajakTransaksiListView(LoginRequiredMixin, ListView):
    model = PajakTransaksi
    template_name = 'pajak/transaksi_list.html'
    context_object_name = 'transaksi_list'
    paginate_by = 50

    def get_queryset(self):
        qs = PajakTransaksi.objects.select_related('akun_pajak', 'akun_lawan', 'entitas_bisnis').order_by('-masa_pajak', '-created_at')
        masa = self.request.GET.get('masa')
        jenis = self.request.GET.get('jenis')
        status = self.request.GET.get('status')
        if masa:
            qs = qs.filter(masa_pajak__startswith=masa)
        if jenis:
            qs = qs.filter(jenis_pajak=jenis)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .models import JENIS_PAJAK_CHOICES, STATUS_CHOICES
        ctx['jenis_choices'] = JENIS_PAJAK_CHOICES
        ctx['status_choices'] = STATUS_CHOICES
        return ctx


class PajakTransaksiEditView(LoginRequiredMixin, UpdateView):
    model = PajakTransaksi
    form_class = OverridePajakForm
    template_name = 'pajak/transaksi_edit.html'
    success_url = reverse_lazy('pajak:transaksi_list')

    def form_valid(self, form):
        from .services import override_pajak
        pt = self.get_object()
        jumlah_baru = form.cleaned_data['jumlah_pajak']
        override_pajak(pt, jumlah_baru, modified_by=self.request.user)
        return super(UpdateView, self).form_valid(form)


class MasaPajakListView(LoginRequiredMixin, ListView):
    model = MasaPajak
    template_name = 'pajak/masa_list.html'
    context_object_name = 'masa_list'


class MasaPajakDetailView(LoginRequiredMixin, DetailView):
    model = MasaPajak
    template_name = 'pajak/masa_detail.html'
    context_object_name = 'masa'

    def get_object(self):
        return MasaPajak.objects.get(
            tahun=self.kwargs['tahun'],
            bulan=self.kwargs['bulan'],
        )

    def post(self, request, *args, **kwargs):
        from django.shortcuts import redirect
        masa = self.get_object()
        action = request.POST.get('action')
        if action == 'lock':
            masa.status = 'locked'
        elif action == 'unlock':
            masa.status = 'open'
        masa.save(update_fields=['status'])
        return redirect('pajak:masa_detail', tahun=masa.tahun, bulan=masa.bulan)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        masa = self.get_object()
        ctx['transaksi_list'] = PajakTransaksi.objects.filter(masa_pajak=masa.masa_date_field).select_related('akun_pajak', 'akun_lawan')
        return ctx

    @property
    def masa_date_field(self):
        pass  # resolved in template — MasaPajak str() already shows the period


class TarifPajakListView(LoginRequiredMixin, ListView):
    model = TarifPajak
    template_name = 'pajak/tarif_list.html'
    context_object_name = 'tarif_list'
    queryset = TarifPajak.objects.order_by('jenis_pajak', '-berlaku_mulai')


class TarifPajakCreateView(LoginRequiredMixin, CreateView):
    model = TarifPajak
    form_class = TarifPajakForm
    template_name = 'pajak/tarif_form.html'
    success_url = reverse_lazy('pajak:tarif_list')
```

`apps/pajak/forms.py`:
```python
from django import forms
from .models import PajakTransaksi, TarifPajak


class OverridePajakForm(forms.Form):
    jumlah_pajak = forms.DecimalField(
        max_digits=19, decimal_places=4, label='Jumlah Pajak (override)',
        min_value=0,
    )


class TarifPajakForm(forms.ModelForm):
    class Meta:
        model = TarifPajak
        fields = ['jenis_pajak', 'nama', 'tarif_persen', 'faktor_dpp', 'berlaku_mulai', 'berlaku_sampai', 'keterangan']
        widgets = {
            'berlaku_mulai':  forms.DateInput(attrs={'type': 'date'}),
            'berlaku_sampai': forms.DateInput(attrs={'type': 'date'}),
        }
```

- [ ] **Step 4: Fix `MasaPajakDetailView.get_context_data` — the `masa_date_field` logic is broken. Fix it:**

Replace the `get_context_data` and the broken property with:
```python
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        masa = self.get_object()
        from datetime import date
        masa_date = date(masa.tahun, masa.bulan, 1)
        ctx['transaksi_list'] = PajakTransaksi.objects.filter(
            masa_pajak=masa_date
        ).select_related('akun_pajak', 'akun_lawan')
        return ctx
```

(Remove the broken `masa_date_field` property entirely.)

- [ ] **Step 5: Run system check**

```
python manage.py check --settings=naveda_integra.settings.test
```

Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add apps/pajak/urls.py apps/pajak/views.py apps/pajak/forms.py naveda_integra/urls.py
git commit -m "feat(pajak): add URL routing, views, forms"
```

---

## Task 14: Templates

**Files:**
- Create: `templates/pajak/transaksi_list.html`
- Create: `templates/pajak/transaksi_edit.html`
- Create: `templates/pajak/masa_list.html`
- Create: `templates/pajak/masa_detail.html`
- Create: `templates/pajak/tarif_list.html`
- Create: `templates/pajak/tarif_form.html`

- [ ] **Step 1: Create `templates/pajak/transaksi_list.html`**

```html
{% extends "base.html" %}
{% block title %}Daftar Pajak Transaksi{% endblock %}
{% block content %}
<div class="container-fluid px-4">
  <h2 class="mt-4">Pajak Transaksi</h2>

  <form method="get" class="row g-2 mb-3">
    <div class="col-auto">
      <input type="month" name="masa" class="form-control" value="{{ request.GET.masa }}" placeholder="Masa (YYYY-MM)">
    </div>
    <div class="col-auto">
      <select name="jenis" class="form-select">
        <option value="">Semua Jenis</option>
        {% for val, label in jenis_choices %}
          <option value="{{ val }}" {% if request.GET.jenis == val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-auto">
      <select name="status" class="form-select">
        <option value="">Semua Status</option>
        {% for val, label in status_choices %}
          <option value="{{ val }}" {% if request.GET.status == val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-auto">
      <button type="submit" class="btn btn-primary">Filter</button>
    </div>
  </form>

  <table class="table table-sm table-hover">
    <thead>
      <tr>
        <th>Masa</th><th>Sumber</th><th>Jenis</th><th>Sifat</th>
        <th class="text-end">DPP</th><th class="text-end">Pajak</th>
        <th>Status</th><th>Override?</th><th></th>
      </tr>
    </thead>
    <tbody>
      {% for pt in transaksi_list %}
      <tr>
        <td>{{ pt.masa_pajak|date:"Y-m" }}</td>
        <td>{{ pt.source_type }}:{{ pt.source_id }}</td>
        <td>{{ pt.get_jenis_pajak_display }}</td>
        <td>{{ pt.get_sifat_pajak_display }}</td>
        <td class="text-end">{{ pt.dpp|floatformat:0 }}</td>
        <td class="text-end">{{ pt.jumlah_pajak|floatformat:2 }}</td>
        <td><span class="badge bg-secondary">{{ pt.status }}</span></td>
        <td>{% if pt.is_overridden %}<span class="badge bg-warning text-dark">Ya</span>{% endif %}</td>
        <td>
          {% if pt.status == 'final' %}
          <a href="{% url 'pajak:transaksi_edit' pt.pk %}" class="btn btn-xs btn-outline-secondary">Override</a>
          {% endif %}
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="9" class="text-center text-muted">Tidak ada data</td></tr>
      {% endfor %}
    </tbody>
  </table>

  {% include "partials/pagination.html" with page_obj=page_obj %}
</div>
{% endblock %}
```

- [ ] **Step 2: Create `templates/pajak/transaksi_edit.html`**

```html
{% extends "base.html" %}
{% block title %}Override Pajak Transaksi{% endblock %}
{% block content %}
<div class="container px-4 mt-4">
  <h2>Override Pajak Transaksi #{{ object.pk }}</h2>
  <dl class="row mb-4">
    <dt class="col-sm-3">Jenis Pajak</dt><dd class="col-sm-9">{{ object.get_jenis_pajak_display }}</dd>
    <dt class="col-sm-3">Masa</dt><dd class="col-sm-9">{{ object.masa_pajak|date:"Y-m" }}</dd>
    <dt class="col-sm-3">DPP</dt><dd class="col-sm-9">{{ object.dpp|floatformat:0 }}</dd>
    <dt class="col-sm-3">Jumlah Pajak Saat Ini</dt><dd class="col-sm-9">{{ object.jumlah_pajak|floatformat:2 }}</dd>
    <dt class="col-sm-3">Status</dt><dd class="col-sm-9">{{ object.status }}</dd>
  </dl>
  <form method="post">
    {% csrf_token %}
    <div class="mb-3">
      <label class="form-label">Jumlah Pajak Baru</label>
      {{ form.jumlah_pajak }}
    </div>
    <button type="submit" class="btn btn-warning">Simpan Override</button>
    <a href="{% url 'pajak:transaksi_list' %}" class="btn btn-secondary ms-2">Batal</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `templates/pajak/masa_list.html`**

```html
{% extends "base.html" %}
{% block title %}Masa Pajak{% endblock %}
{% block content %}
<div class="container-fluid px-4">
  <h2 class="mt-4">Daftar Masa Pajak</h2>
  <table class="table table-sm table-hover">
    <thead>
      <tr><th>Tahun</th><th>Bulan</th><th>Status</th><th></th></tr>
    </thead>
    <tbody>
      {% for mp in masa_list %}
      <tr>
        <td>{{ mp.tahun }}</td>
        <td>{{ mp.bulan }}</td>
        <td>
          {% if mp.status == 'locked' %}
          <span class="badge bg-danger">Terkunci</span>
          {% else %}
          <span class="badge bg-success">Open</span>
          {% endif %}
        </td>
        <td><a href="{% url 'pajak:masa_detail' mp.tahun mp.bulan %}" class="btn btn-xs btn-outline-primary">Detail</a></td>
      </tr>
      {% empty %}
      <tr><td colspan="4" class="text-center text-muted">Belum ada masa pajak</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Create `templates/pajak/masa_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Masa Pajak {{ masa.tahun }}-{{ masa.bulan|stringformat:"02d" }}{% endblock %}
{% block content %}
<div class="container-fluid px-4">
  <h2 class="mt-4">Masa Pajak {{ masa.tahun }}-{{ masa.bulan|stringformat:"02d" }}</h2>
  <p>Status: <strong>{{ masa.get_status_display }}</strong></p>
  <form method="post" class="mb-4">
    {% csrf_token %}
    {% if masa.status == 'open' %}
    <button type="submit" name="action" value="lock" class="btn btn-danger"
            onclick="return confirm('Kunci masa pajak ini? Tidak dapat menambah transaksi baru setelah dikunci.')">
      Kunci Masa Pajak
    </button>
    {% else %}
    <button type="submit" name="action" value="unlock" class="btn btn-warning">Buka Kunci</button>
    {% endif %}
  </form>

  <h5>Transaksi Pajak</h5>
  <table class="table table-sm">
    <thead>
      <tr><th>Sumber</th><th>Jenis</th><th>Sifat</th><th class="text-end">Pajak</th><th>Status</th></tr>
    </thead>
    <tbody>
      {% for pt in transaksi_list %}
      <tr>
        <td>{{ pt.source_type }}:{{ pt.source_id }}</td>
        <td>{{ pt.get_jenis_pajak_display }}</td>
        <td>{{ pt.get_sifat_pajak_display }}</td>
        <td class="text-end">{{ pt.jumlah_pajak|floatformat:2 }}</td>
        <td>{{ pt.status }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="5" class="text-center text-muted">Tidak ada transaksi</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 5: Create `templates/pajak/tarif_list.html`**

```html
{% extends "base.html" %}
{% block title %}Tarif Pajak{% endblock %}
{% block content %}
<div class="container-fluid px-4">
  <div class="d-flex justify-content-between align-items-center mt-4 mb-3">
    <h2>Tarif Pajak</h2>
    <a href="{% url 'pajak:tarif_create' %}" class="btn btn-primary">+ Tambah Tarif</a>
  </div>
  <table class="table table-sm table-hover">
    <thead>
      <tr><th>Jenis</th><th>Nama</th><th class="text-end">Tarif %</th><th class="text-end">Faktor DPP</th><th>Berlaku Mulai</th><th>Berlaku Sampai</th></tr>
    </thead>
    <tbody>
      {% for t in tarif_list %}
      <tr>
        <td>{{ t.get_jenis_pajak_display }}</td>
        <td>{{ t.nama }}</td>
        <td class="text-end">{{ t.tarif_persen }}</td>
        <td class="text-end">{{ t.faktor_dpp }}</td>
        <td>{{ t.berlaku_mulai }}</td>
        <td>{{ t.berlaku_sampai|default:"—" }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="6" class="text-center text-muted">Tidak ada tarif</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 6: Create `templates/pajak/tarif_form.html`**

```html
{% extends "base.html" %}
{% block title %}Tambah Tarif Pajak{% endblock %}
{% block content %}
<div class="container px-4 mt-4">
  <h2>Tambah Tarif Pajak</h2>
  <form method="post" class="mt-3">
    {% csrf_token %}
    {% for field in form %}
    <div class="mb-3">
      <label class="form-label">{{ field.label }}</label>
      {{ field }}
      {% if field.errors %}<div class="text-danger">{{ field.errors }}</div>{% endif %}
    </div>
    {% endfor %}
    <button type="submit" class="btn btn-primary">Simpan</button>
    <a href="{% url 'pajak:tarif_list' %}" class="btn btn-secondary ms-2">Batal</a>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 7: Run system check and smoke test**

```
python manage.py check --settings=naveda_integra.settings.test
python manage.py test apps.pajak apps.pendapatan --settings=naveda_integra.settings.test
```

Expected: system check passes, all tests pass.

- [ ] **Step 8: Commit**

```bash
git add templates/pajak/
git commit -m "feat(pajak): add templates for transaksi, masa, tarif views"
```

---

## Self-Review

**Spec coverage:**
- ✅ TarifPajak with faktor_dpp (Task 2, 3)
- ✅ BracketPPhOP progressive brackets (Task 2, 3)
- ✅ MasaPajak lock guard in sync_pajak + confirm_pajak (Task 6, 7)
- ✅ compute_pajak: ppn_umum faktor 11/12, ppn_ekspor zero (Task 4, 5)
- ✅ compute_pajak: pph_21 progressive 50% × bruto (Task 5)
- ✅ ROUND_HALF_UP 2 dp in post_jurnal_pajak (Task 7)
- ✅ sifat_pajak → journal direction potong_pungut / prepaid (Task 7)
- ✅ batal_pajak reverse journal (Task 8)
- ✅ override_pajak reverse + repost (Task 8)
- ✅ sync_pajak source_type + source_id (Task 6)
- ✅ pendapatan _create_kp_journal DPP only (Task 10)
- ✅ confirm_pendapatan calls sync_pajak + confirm_pajak (Task 11)
- ✅ void_pendapatan calls batal_pajak (Task 12)
- ✅ TRX-PAJ prefix for pajak journals (Task 7)
- ✅ Admin (Task 9)
- ✅ Views + URLs (Tasks 13, 14)
- ✅ Seed data migration (Task 3)
- ✅ INSTALLED_APPS + url routing (Task 1, 13)

**Type consistency:** All service functions defined in Task 4–8 use `PajakTransaksi`, `TarifPajak`, `MasaPajak`, `BracketPPhOP` from Task 2. `JurnalHeader`/`JurnalDetail` import in services.py added in Task 7. `_next_pajak_journal_number()` defined in Task 7 and used only there. `override_pajak` calls `batal_pajak` + `post_jurnal_pajak` — both defined in Task 7/8. Consistent.

**Placeholder scan:** None found. All code blocks are complete.
