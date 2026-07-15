# UOM Master & Konversi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun app `apps/uom` berisi master satuan standar + mesin konversi hybrid (fisik universal + kemasan per-item), sebagai fondasi lintas modul, tanpa mengubah costing/stock ledger.

**Architecture:** App Django baru `apps/uom` dengan model `UnitOfMeasure` (registry global) dan `ItemUOM` (konversi kemasan per-item). Item master (`purchase.ItemMasterPurchase`) memperoleh 3 FK satuan (`stock_uom`, `purchase_uom`, `sales_uom`). Konversi dilakukan fungsi murni `convert(qty, from_uom, to_uom, item=None)` di `apps/uom/conversion.py`.

**Tech Stack:** Django 6.0, PostgreSQL (psycopg2), Decimal untuk semua kuantitas/faktor, `django.test.TestCase` dijalankan via pytest/manage.py.

## Global Constraints

- Django >= 6.0, < 7.0. Python target sesuai proyek.
- Semua field kuantitas/faktor memakai `DecimalField` (jangan float).
- Test dijalankan dengan: `python manage.py test <path> --settings=naveda_integra.settings.test -v 2`.
- App di-registrasi di `naveda_integra/settings/base.py` INSTALLED_APPS.
- `apps.py` wajib punya `name = 'apps.uom'` dan `label = 'uom'` (pola proyek).
- Migrasi skema dibuat via `makemigrations`; migrasi data (seed/backfill) ditulis manual dengan `migrations.RunPython` (contoh: `apps/pajak/migrations/0002_seed_tarif.py`).
- FASE 1 TIDAK menyambung konversi ke transaksi Purchase/Sales/POS. FK UOM baru tetap `null=True, blank=True`.
- Fungsi `convert` gagal keras (`ConversionError`), tidak boleh diam-diam mengembalikan nilai salah.

---

### Task 1: Scaffold app `apps/uom` + model `UnitOfMeasure`

**Files:**
- Create: `apps/uom/__init__.py` (kosong)
- Create: `apps/uom/apps.py`
- Create: `apps/uom/models.py`
- Create: `apps/uom/migrations/__init__.py` (kosong)
- Create: `apps/uom/tests.py`
- Modify: `naveda_integra/settings/base.py` (tambah `'apps.uom'` ke INSTALLED_APPS setelah `'apps.master_data'`)

**Interfaces:**
- Produces: `apps.uom.models.UnitOfMeasure` dengan field `kode, nama, dimension, factor_to_base, is_base, is_system, is_active`; konstanta `DIMENSION_CHOICES` dengan nilai `count, weight, volume, length, area`.

- [ ] **Step 1: Register app in settings**

Modify `naveda_integra/settings/base.py`, tambahkan satu baris pada list INSTALLED_APPS tepat setelah `'apps.master_data',`:

```python
    'apps.master_data',
    'apps.uom',
```

- [ ] **Step 2: Create app scaffold files**

Create `apps/uom/__init__.py`:

```python
```

Create `apps/uom/migrations/__init__.py`:

```python
```

Create `apps/uom/apps.py`:

```python
from django.apps import AppConfig


class UomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.uom'
    label = 'uom'
```

- [ ] **Step 3: Write the failing test**

Create `apps/uom/tests.py`:

```python
"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase

from .models import UnitOfMeasure


class UnitOfMeasureModelTests(TestCase):
    def test_create_physical_unit(self):
        kg = UnitOfMeasure.objects.create(
            kode='kg', nama='Kilogram', dimension='weight',
            factor_to_base=Decimal('1000'), is_base=False, is_system=True,
        )
        self.assertEqual(str(kg), 'kg - Kilogram')
        self.assertEqual(kg.factor_to_base, Decimal('1000'))

    def test_packaging_unit_allows_null_factor(self):
        carton = UnitOfMeasure.objects.create(
            kode='carton', nama='Karton', dimension='count',
            factor_to_base=None, is_base=False, is_system=True,
        )
        self.assertIsNone(carton.factor_to_base)

    def test_kode_unique(self):
        UnitOfMeasure.objects.create(kode='pcs', nama='Pieces', dimension='count',
                                     factor_to_base=Decimal('1'), is_base=True)
        with self.assertRaises(Exception):
            UnitOfMeasure.objects.create(kode='pcs', nama='Dup', dimension='count',
                                         factor_to_base=Decimal('1'))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python manage.py test apps.uom --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `ImportError`/`cannot import name 'UnitOfMeasure'` (model belum ada).

- [ ] **Step 5: Write minimal implementation**

Create `apps/uom/models.py`:

```python
"""Unit of Measure master + per-item packaging conversion."""
from django.db import models


DIMENSION_CHOICES = [
    ('count', 'Count / Jumlah'),
    ('weight', 'Berat'),
    ('volume', 'Volume'),
    ('length', 'Panjang'),
    ('area', 'Luas'),
]


class UnitOfMeasure(models.Model):
    kode = models.CharField(max_length=20, unique=True, verbose_name='Kode')
    nama = models.CharField(max_length=100, verbose_name='Nama')
    dimension = models.CharField(
        max_length=10, choices=DIMENSION_CHOICES, db_index=True, verbose_name='Dimensi',
    )
    factor_to_base = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True,
        verbose_name='Faktor ke Base',
        help_text='Faktor universal ke satuan dasar dimensi. Kosongkan untuk '
                  'satuan kemasan yang berbeda tiap produk (carton, box, dus, dll).',
    )
    is_base = models.BooleanField(default=False, verbose_name='Satuan Dasar')
    is_system = models.BooleanField(default=False, verbose_name='Bawaan Sistem')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')

    class Meta:
        verbose_name = 'Unit of Measure'
        verbose_name_plural = 'Units of Measure'
        ordering = ['dimension', 'kode']

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'
```

- [ ] **Step 6: Make migration**

Run: `python manage.py makemigrations uom --settings=naveda_integra.settings.test`
Expected: `apps/uom/migrations/0001_initial.py` dibuat.

- [ ] **Step 7: Run test to verify it passes**

Run: `python manage.py test apps.uom --settings=naveda_integra.settings.test -v 2`
Expected: PASS (3 test).

- [ ] **Step 8: Commit**

```bash
git add apps/uom naveda_integra/settings/base.py
git commit -m "feat(uom): scaffold uom app with UnitOfMeasure model"
```

---

### Task 2: Model `ItemUOM` (konversi kemasan per-item)

**Files:**
- Modify: `apps/uom/models.py` (tambah class `ItemUOM`)
- Modify: `apps/uom/tests.py` (tambah test class)

**Interfaces:**
- Consumes: `UnitOfMeasure` (Task 1), `purchase.ItemMasterPurchase`.
- Produces: `apps.uom.models.ItemUOM` dengan field `item (FK ItemMasterPurchase), uom (FK UnitOfMeasure), qty_in_stock_uom (Decimal)`, unique `(item, uom)`.

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
from apps.purchase.models import ItemMasterPurchase
from .models import ItemUOM


class ItemUOMModelTests(TestCase):
    def setUp(self):
        self.item = ItemMasterPurchase.objects.create(nama='Kopi Sachet', tipe_item='RM')
        self.carton = UnitOfMeasure.objects.create(
            kode='carton', nama='Karton', dimension='count', factor_to_base=None,
        )

    def test_create_item_uom(self):
        iu = ItemUOM.objects.create(
            item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'),
        )
        self.assertEqual(iu.qty_in_stock_uom, Decimal('24'))
        self.assertIn('carton', str(iu))

    def test_unique_item_uom(self):
        ItemUOM.objects.create(item=self.item, uom=self.carton,
                               qty_in_stock_uom=Decimal('24'))
        with self.assertRaises(Exception):
            ItemUOM.objects.create(item=self.item, uom=self.carton,
                                   qty_in_stock_uom=Decimal('12'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.ItemUOMModelTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `cannot import name 'ItemUOM'`.

- [ ] **Step 3: Write minimal implementation**

Tambahkan ke akhir `apps/uom/models.py`:

```python
class ItemUOM(models.Model):
    """Per-item packaging conversion: 1 <uom> = qty_in_stock_uom <item.stock_uom>."""
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.CASCADE,
        related_name='item_uoms',
        verbose_name='Item',
    )
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='item_uoms',
        verbose_name='Satuan',
    )
    qty_in_stock_uom = models.DecimalField(
        max_digits=24, decimal_places=8,
        verbose_name='Jumlah dalam Stock UOM',
        help_text='Berapa banyak satuan stok dalam 1 satuan ini. Contoh: 1 carton = 24 pcs → 24.',
    )

    class Meta:
        verbose_name = 'Item UOM'
        verbose_name_plural = 'Item UOMs'
        unique_together = [('item', 'uom')]
        indexes = [
            models.Index(fields=['item', 'uom'], name='idx_itemuom_item_uom'),
        ]

    def __str__(self) -> str:
        return f'{self.item.nama}: 1 {self.uom.kode} = {self.qty_in_stock_uom}'
```

- [ ] **Step 4: Make migration**

Run: `python manage.py makemigrations uom --settings=naveda_integra.settings.test`
Expected: migrasi `0002_itemuom.py` dibuat.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.ItemUOMModelTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test).

- [ ] **Step 6: Commit**

```bash
git add apps/uom
git commit -m "feat(uom): add ItemUOM per-item packaging conversion model"
```

---

### Task 3: Tambah FK `stock_uom` / `purchase_uom` / `sales_uom` ke item master

**Files:**
- Modify: `apps/purchase/models.py` (class `ItemMasterPurchase`, tambah 3 FK setelah field `unit_price`)
- Modify: `apps/uom/tests.py` (test relasi)

**Interfaces:**
- Consumes: `UnitOfMeasure` (Task 1).
- Produces: `ItemMasterPurchase.stock_uom`, `.purchase_uom`, `.sales_uom` (semua FK ke `uom.UnitOfMeasure`, `null=True`).

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
class ItemMasterUOMFieldsTests(TestCase):
    def test_item_has_uom_fields(self):
        pcs = UnitOfMeasure.objects.create(
            kode='pcs', nama='Pieces', dimension='count',
            factor_to_base=Decimal('1'), is_base=True,
        )
        item = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')
        item.stock_uom = pcs
        item.purchase_uom = pcs
        item.sales_uom = pcs
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.stock_uom, pcs)
        self.assertEqual(item.purchase_uom, pcs)
        self.assertEqual(item.sales_uom, pcs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.ItemMasterUOMFieldsTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `ItemMasterPurchase has no field 'stock_uom'`.

- [ ] **Step 3: Write minimal implementation**

Di `apps/purchase/models.py`, dalam class `ItemMasterPurchase`, tambahkan tepat setelah field `unit_price` (baris ~163-168) dan sebelum field `entitas_bisnis`:

```python
    stock_uom = models.ForeignKey(
        'uom.UnitOfMeasure',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='items_stock',
        verbose_name='Satuan Stok',
        help_text='Satuan penyimpanan/penilaian (kanonik item).',
    )
    purchase_uom = models.ForeignKey(
        'uom.UnitOfMeasure',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='items_purchase',
        verbose_name='Satuan Pembelian',
    )
    sales_uom = models.ForeignKey(
        'uom.UnitOfMeasure',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='items_sales',
        verbose_name='Satuan Penjualan',
    )
```

- [ ] **Step 4: Make migration**

Run: `python manage.py makemigrations purchase --settings=naveda_integra.settings.test`
Expected: migrasi baru di `apps/purchase/migrations/` menambah 3 FK.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.ItemMasterUOMFieldsTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Run full purchase tests to check no regression**

Run: `python manage.py test apps.purchase --settings=naveda_integra.settings.test -v 2`
Expected: PASS (semua test purchase lama tetap hijau).

- [ ] **Step 7: Commit**

```bash
git add apps/purchase apps/uom/tests.py
git commit -m "feat(purchase): add stock/purchase/sales UOM FKs to item master"
```

---

### Task 4: Seed data migration satuan bawaan

**Files:**
- Create: `apps/uom/migrations/0003_seed_units.py`
- Modify: `apps/uom/tests.py` (test seed dijalankan)

**Interfaces:**
- Consumes: `UnitOfMeasure` (Task 1).
- Produces: baris `UnitOfMeasure` bawaan (`is_system=True`) untuk 5 dimensi; tepat 1 `is_base=True` per dimensi.

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
class SeedUnitsTests(TestCase):
    """Seed runs via migration; data must be present in the test DB."""

    def test_base_unit_per_dimension(self):
        for dim in ('count', 'weight', 'volume', 'length', 'area'):
            bases = UnitOfMeasure.objects.filter(dimension=dim, is_base=True)
            self.assertEqual(bases.count(), 1, f'dimension {dim} must have exactly one base')

    def test_known_units_seeded(self):
        for kode in ('pcs', 'kg', 'g', 'ton', 'mL', 'L', 'mm', 'cm', 'm',
                     'carton', 'box', 'lusin'):
            self.assertTrue(
                UnitOfMeasure.objects.filter(kode=kode, is_system=True).exists(),
                f'{kode} not seeded',
            )

    def test_packaging_units_have_null_factor(self):
        for kode in ('carton', 'box', 'pack', 'dus', 'roll', 'botol'):
            u = UnitOfMeasure.objects.get(kode=kode)
            self.assertIsNone(u.factor_to_base, f'{kode} should have null factor')

    def test_lusin_factor(self):
        self.assertEqual(UnitOfMeasure.objects.get(kode='lusin').factor_to_base,
                         Decimal('12'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.SeedUnitsTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — belum ada base unit / kode tidak ditemukan.

- [ ] **Step 3: Write the seed migration**

Create `apps/uom/migrations/0003_seed_units.py`:

```python
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
```

Note: `m³`/`cm²` disimpan sebagai kode ASCII (`m3`, `cm2`) untuk keamanan; label boleh mengandung simbol.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.SeedUnitsTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add apps/uom
git commit -m "feat(uom): seed standard units of measure"
```

---

### Task 5: Backfill migration — item lama → `pcs`

**Files:**
- Create: `apps/purchase/migrations/00NN_backfill_item_uom.py` (nomor mengikuti migrasi Task 3)
- Modify: `apps/uom/tests.py` (test backfill logic sebagai fungsi murni)

**Interfaces:**
- Consumes: `UnitOfMeasure` seed (Task 4), FK item master (Task 3).
- Produces: semua `ItemMasterPurchase` dengan `stock_uom/purchase_uom/sales_uom` NULL diisi `pcs`.

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
class BackfillItemUOMTests(TestCase):
    def test_backfill_sets_pcs_for_null_items(self):
        from apps.uom.backfill import backfill_default_uom
        item = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        self.assertIsNone(item.stock_uom)

        backfill_default_uom(ItemMasterPurchase, UnitOfMeasure)

        item.refresh_from_db()
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.assertEqual(item.stock_uom, pcs)
        self.assertEqual(item.purchase_uom, pcs)
        self.assertEqual(item.sales_uom, pcs)

    def test_backfill_does_not_override_existing(self):
        from apps.uom.backfill import backfill_default_uom
        kg = UnitOfMeasure.objects.get(kode='kg')
        item = ItemMasterPurchase.objects.create(nama='Tepung', tipe_item='RM',
                                                 stock_uom=kg)
        backfill_default_uom(ItemMasterPurchase, UnitOfMeasure)
        item.refresh_from_db()
        self.assertEqual(item.stock_uom, kg)  # unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.BackfillItemUOMTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `No module named 'apps.uom.backfill'`.

- [ ] **Step 3: Write the backfill helper**

Create `apps/uom/backfill.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.BackfillItemUOMTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test).

- [ ] **Step 5: Create the backfill migration**

Cari nomor migrasi terakhir purchase: `ls apps/purchase/migrations/`. Buat file berikutnya, mis. `apps/purchase/migrations/00NN_backfill_item_uom.py` (ganti `00NN` dan `PREV` sesuai urutan; `PREV` = migrasi Task 3 yang menambah FK UOM):

```python
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
        ('purchase', 'PREV'),      # migrasi Task 3 (FK UOM)
        ('uom', '0003_seed_units'),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

Catatan: `backfill_default_uom` menerima model apa pun (termasuk historical model dari `apps.get_model`) karena hanya memakai field & manager standar.

- [ ] **Step 6: Verify migrations apply cleanly**

Run: `python manage.py migrate --settings=naveda_integra.settings.test`
Expected: semua migrasi (uom + purchase) apply tanpa error.

- [ ] **Step 7: Commit**

```bash
git add apps/uom apps/purchase/migrations
git commit -m "feat(purchase): backfill default pcs UOM for existing items"
```

---

### Task 6: Mesin konversi `convert()` + `ConversionError`

**Files:**
- Create: `apps/uom/conversion.py`
- Modify: `apps/uom/tests.py` (test konversi)

**Interfaces:**
- Consumes: `UnitOfMeasure`, `ItemUOM` (Task 1-2), `ItemMasterPurchase.stock_uom` (Task 3).
- Produces:
  - `apps.uom.conversion.ConversionError` (Exception)
  - `convert(qty: Decimal, from_uom, to_uom, item=None) -> Decimal`
  - `to_stock_uom(qty: Decimal, from_uom, item) -> Decimal`
  - `from_stock_uom(qty: Decimal, to_uom, item) -> Decimal`

- [ ] **Step 1: Write the failing tests**

Tambahkan ke `apps/uom/tests.py`:

```python
class ConvertTests(TestCase):
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.kg = UnitOfMeasure.objects.get(kode='kg')
        self.g = UnitOfMeasure.objects.get(kode='g')
        self.L = UnitOfMeasure.objects.get(kode='L')
        self.mL = UnitOfMeasure.objects.get(kode='mL')
        self.carton = UnitOfMeasure.objects.get(kode='carton')
        self.item_a = ItemMasterPurchase.objects.create(
            nama='Kopi A', tipe_item='RM', stock_uom=self.pcs)
        self.item_b = ItemMasterPurchase.objects.create(
            nama='Kopi B', tipe_item='RM', stock_uom=self.pcs)
        ItemUOM.objects.create(item=self.item_a, uom=self.carton,
                               qty_in_stock_uom=Decimal('24'))
        ItemUOM.objects.create(item=self.item_b, uom=self.carton,
                               qty_in_stock_uom=Decimal('12'))

    def test_identity(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('5'), self.pcs, self.pcs), Decimal('5'))

    def test_physical_universal_kg_to_g(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('2'), self.kg, self.g), Decimal('2000'))

    def test_physical_universal_L_to_mL(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('1.5'), self.L, self.mL), Decimal('1500'))

    def test_packaging_carton_to_pcs_per_item(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('1'), self.carton, self.pcs, item=self.item_a),
                         Decimal('24'))
        self.assertEqual(convert(Decimal('1'), self.carton, self.pcs, item=self.item_b),
                         Decimal('12'))

    def test_packaging_pcs_to_carton(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('48'), self.pcs, self.carton, item=self.item_a),
                         Decimal('2'))

    def test_packaging_without_item_raises(self):
        from apps.uom.conversion import convert, ConversionError
        with self.assertRaises(ConversionError):
            convert(Decimal('1'), self.carton, self.pcs)

    def test_incompatible_raises(self):
        from apps.uom.conversion import convert, ConversionError
        with self.assertRaises(ConversionError):
            convert(Decimal('1'), self.kg, self.pcs, item=self.item_a)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.uom.tests.ConvertTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `No module named 'apps.uom.conversion'`.

- [ ] **Step 3: Write the conversion engine**

Create `apps/uom/conversion.py`:

```python
"""Hybrid UOM conversion engine.

- Physical universal conversions (kg<->g, L<->mL) use UnitOfMeasure.factor_to_base
  within one dimension; no item context needed.
- Packaging conversions (carton->pcs) differ per product and use ItemUOM keyed
  to the item's stock_uom.
"""
from decimal import Decimal

from .models import ItemUOM


class ConversionError(Exception):
    """Raised when a conversion cannot be resolved."""


def _universal(qty, from_uom, to_uom):
    """qty in from_uom -> to_uom via global factors (same dimension). None if N/A."""
    if (from_uom.dimension == to_uom.dimension
            and from_uom.factor_to_base is not None
            and to_uom.factor_to_base is not None):
        return qty * from_uom.factor_to_base / to_uom.factor_to_base
    return None


def to_stock_uom(qty: Decimal, from_uom, item) -> Decimal:
    """Convert qty expressed in from_uom into the item's stock_uom."""
    stock = item.stock_uom if item is not None else None
    if stock is None:
        raise ConversionError('Item tidak memiliki stock_uom.')
    if from_uom.pk == stock.pk:
        return qty
    iu = ItemUOM.objects.filter(item=item, uom=from_uom).first()
    if iu is not None:
        return qty * iu.qty_in_stock_uom
    universal = _universal(qty, from_uom, stock)
    if universal is not None:
        return universal
    raise ConversionError(
        f'Tidak dapat mengonversi {from_uom.kode} ke stock_uom {stock.kode} '
        f'untuk item {item.nama}.'
    )


def from_stock_uom(qty: Decimal, to_uom, item) -> Decimal:
    """Convert qty expressed in the item's stock_uom into to_uom."""
    stock = item.stock_uom if item is not None else None
    if stock is None:
        raise ConversionError('Item tidak memiliki stock_uom.')
    if to_uom.pk == stock.pk:
        return qty
    iu = ItemUOM.objects.filter(item=item, uom=to_uom).first()
    if iu is not None:
        if iu.qty_in_stock_uom == 0:
            raise ConversionError('qty_in_stock_uom tidak boleh 0.')
        return qty / iu.qty_in_stock_uom
    universal = _universal(qty, stock, to_uom)
    if universal is not None:
        return universal
    raise ConversionError(
        f'Tidak dapat mengonversi stock_uom {stock.kode} ke {to_uom.kode} '
        f'untuk item {item.nama}.'
    )


def convert(qty: Decimal, from_uom, to_uom, item=None) -> Decimal:
    """Convert qty from one UOM to another.

    Universal (physical, same dimension) conversions ignore ``item``.
    Packaging conversions require ``item``. Raises ConversionError if unresolved.
    """
    if from_uom.pk == to_uom.pk:
        return qty
    universal = _universal(qty, from_uom, to_uom)
    if universal is not None:
        return universal
    if item is None:
        raise ConversionError(
            f'Konversi {from_uom.kode} -> {to_uom.kode} membutuhkan konteks item '
            f'(satuan kemasan).'
        )
    base_qty = to_stock_uom(qty, from_uom, item)
    return from_stock_uom(base_qty, to_uom, item)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.uom.tests.ConvertTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (7 test).

- [ ] **Step 5: Commit**

```bash
git add apps/uom
git commit -m "feat(uom): add hybrid convert() engine with ConversionError"
```

---

### Task 7: Django admin + guard `is_system` dari penghapusan

**Files:**
- Create: `apps/uom/admin.py`
- Modify: `apps/uom/tests.py` (test guard delete)

**Interfaces:**
- Consumes: `UnitOfMeasure`, `ItemUOM`.
- Produces: registrasi admin; `UnitOfMeasureAdmin.has_delete_permission` menolak hapus baris `is_system=True`.

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
from django.contrib.admin.sites import AdminSite


class AdminGuardTests(TestCase):
    def test_system_unit_delete_blocked(self):
        from apps.uom.admin import UnitOfMeasureAdmin
        admin = UnitOfMeasureAdmin(UnitOfMeasure, AdminSite())
        pcs = UnitOfMeasure.objects.get(kode='pcs')

        class Req:  # minimal request stub
            pass
        self.assertFalse(admin.has_delete_permission(Req(), obj=pcs))

    def test_custom_unit_delete_allowed(self):
        from apps.uom.admin import UnitOfMeasureAdmin
        admin = UnitOfMeasureAdmin(UnitOfMeasure, AdminSite())
        custom = UnitOfMeasure.objects.create(
            kode='sak', nama='Sak', dimension='count', factor_to_base=None,
            is_system=False)

        class Req:
            pass
        self.assertTrue(admin.has_delete_permission(Req(), obj=custom))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.AdminGuardTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `No module named 'apps.uom.admin'`.

- [ ] **Step 3: Write the admin**

Create `apps/uom/admin.py`:

```python
from django.contrib import admin

from .models import UnitOfMeasure, ItemUOM


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'dimension', 'factor_to_base',
                    'is_base', 'is_system', 'is_active')
    list_filter = ('dimension', 'is_base', 'is_system', 'is_active')
    search_fields = ('kode', 'nama')

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ItemUOM)
class ItemUOMAdmin(admin.ModelAdmin):
    list_display = ('item', 'uom', 'qty_in_stock_uom')
    search_fields = ('item__nama', 'uom__kode')
    autocomplete_fields = ('item', 'uom')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.AdminGuardTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add apps/uom
git commit -m "feat(uom): admin registration with is_system delete guard"
```

---

### Task 8: UI kelola satuan (list + create/edit)

**Files:**
- Create: `apps/uom/forms.py`
- Create: `apps/uom/views.py`
- Create: `apps/uom/urls.py`
- Create: `templates/uom/unit_list.html`
- Create: `templates/uom/unit_form.html`
- Modify: `naveda_integra/urls.py` (include `apps.uom.urls`)
- Modify: `apps/uom/tests.py` (test view)

**Interfaces:**
- Consumes: `UnitOfMeasure`.
- Produces: URL names `uom:list`, `uom:create`, `uom:update` di bawah prefix `/uom/`.

- [ ] **Step 1: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UnitViewTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username='u1', password='pw123456')
        self.client.force_login(self.client_user)

    def test_list_renders(self):
        resp = self.client.get(reverse('uom:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'pcs')  # seeded unit visible

    def test_create_custom_unit(self):
        resp = self.client.post(reverse('uom:create'), {
            'kode': 'sak', 'nama': 'Sak', 'dimension': 'count',
            'factor_to_base': '', 'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(UnitOfMeasure.objects.filter(kode='sak').exists())
```

Note: bila proyek memakai login berbasis `login_required`, `force_login` sudah menutupinya. Sesuaikan `create_user` bila model User custom butuh field tambahan (cek `apps/accounts/models.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.UnitViewTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `Reverse for 'list' not found` / no url conf.

- [ ] **Step 3: Write form**

Create `apps/uom/forms.py`:

```python
from django import forms

from .models import UnitOfMeasure


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['kode', 'nama', 'dimension', 'factor_to_base', 'is_base', 'is_active']

    def clean(self):
        cleaned = super().clean()
        # Guard: cannot edit kode of a system unit
        if self.instance.pk and self.instance.is_system:
            cleaned['kode'] = self.instance.kode
        return cleaned
```

- [ ] **Step 4: Write views**

Create `apps/uom/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UnitOfMeasureForm
from .models import UnitOfMeasure


@login_required
def unit_list(request):
    units = UnitOfMeasure.objects.all().order_by('dimension', 'kode')
    return render(request, 'uom/unit_list.html', {'units': units})


@login_required
def unit_create(request):
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('uom:list')
    else:
        form = UnitOfMeasureForm()
    return render(request, 'uom/unit_form.html', {'form': form, 'is_edit': False})


@login_required
def unit_update(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            return redirect('uom:list')
    else:
        form = UnitOfMeasureForm(instance=unit)
    return render(request, 'uom/unit_form.html',
                  {'form': form, 'is_edit': True, 'unit': unit})
```

- [ ] **Step 5: Write urls**

Create `apps/uom/urls.py`:

```python
from django.urls import path

from . import views

app_name = 'uom'

urlpatterns = [
    path('', views.unit_list, name='list'),
    path('create/', views.unit_create, name='create'),
    path('<int:pk>/edit/', views.unit_update, name='update'),
]
```

Modify `naveda_integra/urls.py`, tambahkan di dalam `urlpatterns` setelah baris `master-data/`:

```python
    path('uom/', include('apps.uom.urls')),
```

- [ ] **Step 6: Write templates**

Cek base template yang dipakai app lain (mis. `apps/inventory` templates) untuk `{% extends %}` yang benar. Create `templates/uom/unit_list.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="container">
  <h1>Master Satuan</h1>
  <a href="{% url 'uom:create' %}">+ Satuan Baru</a>
  <table>
    <thead>
      <tr><th>Kode</th><th>Nama</th><th>Dimensi</th><th>Faktor</th>
          <th>Base</th><th>Sistem</th><th>Aktif</th><th></th></tr>
    </thead>
    <tbody>
      {% for u in units %}
      <tr>
        <td>{{ u.kode }}</td><td>{{ u.nama }}</td><td>{{ u.get_dimension_display }}</td>
        <td>{{ u.factor_to_base|default:'-' }}</td>
        <td>{{ u.is_base|yesno:'Ya,-' }}</td>
        <td>{{ u.is_system|yesno:'Ya,-' }}</td>
        <td>{{ u.is_active|yesno:'Ya,-' }}</td>
        <td><a href="{% url 'uom:update' u.pk %}">Edit</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

Create `templates/uom/unit_form.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="container">
  <h1>{% if is_edit %}Edit Satuan{% else %}Satuan Baru{% endif %}</h1>
  {% if is_edit and unit.is_system %}
    <p><em>Satuan bawaan sistem — kode tidak dapat diubah.</em></p>
  {% endif %}
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Simpan</button>
    <a href="{% url 'uom:list' %}">Batal</a>
  </form>
</div>
{% endblock %}
```

Note: ganti `'base.html'` bila proyek memakai nama base template berbeda (verifikasi dengan `grep -rl "{% block content %}" templates/ | head`).

- [ ] **Step 7: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.UnitViewTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test). Bila gagal karena base template, sesuaikan nama `{% extends %}` lalu ulangi.

- [ ] **Step 8: Commit**

```bash
git add apps/uom naveda_integra/urls.py templates/uom
git commit -m "feat(uom): unit management UI (list/create/edit)"
```

---

### Task 9: `ItemUOM` inline pada form item master + pilihan UOM

**Files:**
- Modify: `apps/purchase/admin.py` (tambah `ItemUOMInline` pada `ItemMasterPurchaseAdmin`; tambah field UOM di fieldsets/list bila ada)
- Modify: `apps/purchase/forms.py` (jika ada form item master, tambah `stock_uom/purchase_uom/sales_uom`)
- Modify: `apps/uom/tests.py` (test inline terpasang)

**Interfaces:**
- Consumes: `ItemUOM` (Task 2), FK UOM (Task 3).
- Produces: admin item master menampilkan pilihan UOM + inline ItemUOM.

- [ ] **Step 1: Inspect current item master admin/form**

Run: `grep -nE "ItemMasterPurchase|class .*Admin|fields|fieldsets|inlines" apps/purchase/admin.py`
Run: `grep -nE "ItemMaster|class .*Form|fields" apps/purchase/forms.py`
Catat nama class admin item master dan apakah ada ModelForm untuk item master.

- [ ] **Step 2: Write the failing test**

Tambahkan ke `apps/uom/tests.py`:

```python
class ItemMasterAdminInlineTests(TestCase):
    def test_itemuom_inline_registered(self):
        from django.contrib import admin as dj_admin
        from apps.purchase.models import ItemMasterPurchase
        from apps.uom.models import ItemUOM
        model_admin = dj_admin.site._registry[ItemMasterPurchase]
        inline_models = [inline.model for inline in model_admin.inlines]
        self.assertIn(ItemUOM, inline_models)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python manage.py test apps.uom.tests.ItemMasterAdminInlineTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `ItemUOM not in inlines` (atau KeyError bila item master belum terdaftar; jika belum terdaftar, catat & daftarkan minimal).

- [ ] **Step 4: Add the inline**

Di `apps/purchase/admin.py`, tambahkan import dan inline, lalu pasang ke admin item master (gunakan nama class hasil Step 1). Contoh:

```python
from apps.uom.models import ItemUOM


class ItemUOMInline(admin.TabularInline):
    model = ItemUOM
    extra = 1
    autocomplete_fields = ('uom',)
```

Lalu pada class admin `ItemMasterPurchase` (mis. `ItemMasterPurchaseAdmin`), tambahkan:

```python
    inlines = [ItemUOMInline]
```

Jika class admin item master belum ada `search_fields`, tambahkan `search_fields = ('nama', 'item_id')` agar `autocomplete_fields` di Task 7/9 berfungsi.

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test apps.uom.tests.ItemMasterAdminInlineTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Run full suite for touched apps**

Run: `python manage.py test apps.uom apps.purchase --settings=naveda_integra.settings.test -v 2`
Expected: PASS semua.

- [ ] **Step 7: Commit**

```bash
git add apps/purchase/admin.py apps/uom/tests.py
git commit -m "feat(purchase): ItemUOM inline on item master admin"
```

---

### Task 10: Regression sweep + dokumentasi ringkas

**Files:**
- Modify: `docs/DATABASE.md` (tambah entri tabel `uom_unitofmeasure`, `uom_itemuom`, dan 3 kolom baru item master) — jika file mendokumentasikan skema.

- [x] **Step 1: Run the full test suite**

Run: `python manage.py test --settings=naveda_integra.settings.test -v 1`
Result: 756 tests ran. 82 failures/errors, all pre-existing `django-axes`
`AxesBackendRequestParameterRequired` issues triggered by `self.client.login()`
in unrelated apps (manufacturing, purchase, entitas_bisnis, customers, inventory,
etc.) — none touch `apps.uom` or UOM fields. Confirmed by name-matching the
failing tests: zero mention `uom`.

Blocker found & fixed en route: `apps/pos_config/migrations/0005_drop_orphaned_pos_apps.py`
(unrelated commit `7504296`) used Postgres-only `DROP TABLE ... CASCADE`, which
SQLite (test settings) rejects with `OperationalError: near "CASCADE": syntax error`,
breaking test-DB setup for the entire suite. Removed `CASCADE` (verified no other
app has a FK into the dropped `pos_orders`/`pos_crm`/`pos_promotions`/`pos_reports`
tables, so dropping without `CASCADE` is safe on Postgres too).

- [x] **Step 2: Verify migrations are complete & consistent**

Run: `python manage.py makemigrations --check --dry-run --settings=naveda_integra.settings.test`
Result: one pending migration reported — `apps/pajak/migrations/0003_alter_pajaktransaksi_options.py`
(Meta options change). Pre-existing, unrelated to `uom`/`purchase` models touched
by this plan; left untouched (out of scope).

- [x] **Step 3: Update schema doc (jika ada)**

Checked `docs/DATABASE.md` — it is a PostgreSQL install/setup guide, not a
per-table schema reference (no table-level documentation exists for any app).
Per the plan's own conditional, skipped.

- [x] **Step 4: Commit**

Skipped (Step 3 was a no-op; nothing to commit for docs). The migration fix
from Step 1 was committed separately as `fix(pos_config): use sqlite-compatible
DROP TABLE in orphaned pos apps cleanup migration`.

---

## Self-Review

**Spec coverage:**
- Master satuan standar bawaan → Task 4 (seed). ✅
- Konversi otomatis + faktor dapat dikonfigurasi → Task 6 (`convert`) + `factor_to_base`/`ItemUOM`. ✅
- Satuan kustom + aturan konversi → Task 8 (UI create) + `ItemUOM`. ✅
- Master satuan sama lintas modul → app `uom` netral (Task 1), item master pakai FK (Task 3). ✅
- Satuan berbeda per proses bisnis (beli/simpan/produksi/jual) → `stock/purchase/sales_uom` (Task 3) + convert (Task 6). ✅
- Generic/reusable/scalable untuk BOM → app terpisah + `to_stock_uom`/`from_stock_uom` helper (Task 6). ✅
- CRUD + UI → Task 7 (admin) + Task 8 (UI). ✅
- Guard is_system → Task 7 + Task 8 form clean. ✅
- Migrasi bertahap (nullable + backfill) → Task 3 + Task 5. ✅
- Testing convert (fisik/kemasan/error) → Task 6. ✅
- Non-goals (tanpa wiring transaksi, tanpa berjenjang, tanpa non-null) → dihormati; tidak ada task yang menyentuhnya. ✅

**Placeholder scan:** `00NN`/`PREV` di Task 5 adalah nomor migrasi yang harus diisi dari `ls` — instruksi eksplisit disertakan, bukan placeholder logika. Tidak ada TODO/TBD lain.

**Type consistency:** `convert/to_stock_uom/from_stock_uom` konsisten dipakai di Task 6; `backfill_default_uom(ItemModel, UnitModel)` konsisten antara Task 5 helper & migrasi; field names (`stock_uom`, `purchase_uom`, `sales_uom`, `qty_in_stock_uom`, `factor_to_base`, `is_system`) konsisten lintas task.
