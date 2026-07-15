# Stock Ledger Tunggal + Isolasi Entitas Bisnis Implementation Plan (Fase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Membangun `StockMovement` sebagai ledger stok tunggal yang otoritatif dengan isolasi Entitas Bisnis hierarkis, memperbaiki kebocoran stok antar cabang, tanpa mengubah costing (FIFO) dan tanpa memutus pembaca `FIFOBatch`/`InventoryRecord` (dijaga sebagai mirror).

**Architecture:** Engine stok murni di `apps/inventory/ledger.py` (fungsi `record_inflow`, `consume_stock`, `reverse_movements`, `get_available_stock`) yang menulis `StockMovement` (layer inflow append-only + baris outflow) dan `StockConsumption` (alokasi outflow→inflow). Isolasi hierarkis: konsumsi mencocokkan node EB terdalam lalu naik ke induk (lv3→lv2→lv1), tak menyeberang cabang sibling. Purchase/Sales/Manufacturing dual-write: tetap tulis `FIFOBatch`+`InventoryRecord`, tautkan ke layer `StockMovement` lewat FK, dan konsumsi memirror pengurangannya ke ledger lama. Backfill dari `FIFOBatch` + rekonsiliasi.

**Tech Stack:** Django 6.0, PostgreSQL (prod) / SQLite in-memory (test), `django.contrib.contenttypes` GenericForeignKey, Decimal untuk semua kuantitas/biaya.

---

## Global Constraints

- Django >= 6.0. Semua kuantitas/biaya `DecimalField` (jangan float).
- Test dijalankan: `python manage.py test <path> --settings=naveda_integra.settings.test -v 2`.
- App `apps.inventory` sudah ada; migrasi terakhir `0004_alter_inventoryrecord_unit_price_verbose_name`. Migrasi baru menyambung dari situ.
- Migrasi `apps.manufacturing` terakhir `0006_periodclosing`. Migrasi `apps.purchase` terakhir `0008_backfill_item_uom`.
- `django.contrib.contenttypes` sudah di INSTALLED_APPS (`naveda_integra/settings/base.py:31`).
- FIFO same-EB harus tetap identik hasilnya (characterization dilindungi di Task 3/5). Fase ini TIDAK mengubah costing.
- Item bulk = `RMB`/`FGB`/`ITMB` → value-based (qty=1, unit_cost=total_value). Non-bulk inventory = `RM`/`FG`/`ITM`.
- `consume_stock` gagal keras (`InsufficientStockError`), tidak diam-diam mengembalikan nilai salah.

### Konvensi isolasi hierarkis (dipakai di banyak task)

Diberi `eb_lv1` (wajib), `eb_lv2` (opsional), `eb_lv3` (opsional):
- **requested_level** = `'lv3'` bila `eb_lv3` ada, else `'lv2'` bila `eb_lv2` ada, else `'lv1'`.
- **Tier kandidat** (urut terdekat → induk), tiap tier hanya layer inflow `remaining_qty > 0`, urut FIFO `tanggal, created_at`:
  - Tier `lv3` (bila `eb_lv3`): `entitas_bisnis_lv3 = eb_lv3`.
  - Tier `lv2` (bila `eb_lv2`): `entitas_bisnis_lv2 = eb_lv2, entitas_bisnis_lv3 IS NULL`.
  - Tier `lv1`: `entitas_bisnis = eb_lv1, entitas_bisnis_lv2 IS NULL, entitas_bisnis_lv3 IS NULL`.
- **used_fallback** = ada qty terkonsumsi dari tier yang lebih tinggi (lebih dekat root) daripada `requested_level`.
- **Isolasi sibling:** tier lv3 memfilter `entitas_bisnis_lv3 = eb_lv3` persis → cabang lain (lv3 berbeda) tak pernah masuk.

---

### Task 1: Model `StockMovement`, `StockConsumption`, dan `InsufficientStockError`

**Files:**
- Modify: `apps/inventory/models.py` (tambah dua model di akhir file)
- Create: `apps/inventory/ledger.py` (mulai dengan exception saja)
- Create: `apps/inventory/tests/__init__.py` (kosong; pindahkan tak perlu — buat paket test baru)
- Create: `apps/inventory/tests/test_stock_models.py`
- Migration: `apps/inventory/migrations/0005_stockmovement_stockconsumption.py` (via makemigrations)

Catatan: `apps/inventory/tests.py` yang ada tetap dipakai. Django menemukan test di `tests.py` **atau** paket `tests/`, tapi tidak keduanya. **Sebelum membuat paket `tests/`, cek**: jika `apps/inventory/tests.py` ada, ubah strategi — taruh test baru di dalam `apps/inventory/tests.py` (append) agar tak bentrok. Plan ini mengasumsikan append ke `apps/inventory/tests.py`.

**Interfaces:**
- Produces: `apps.inventory.models.StockMovement`, `apps.inventory.models.StockConsumption`, `apps.inventory.ledger.InsufficientStockError`.

- [ ] **Step 1: Tulis test model yang gagal**

Append ke `apps/inventory/tests.py`:

```python
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase as DjangoTestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import StockMovement, StockConsumption


class StockMovementModelTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_inflow_layer(self):
        mv = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('10'),
        )
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertIn('purchase_in', str(mv))

    def test_stock_consumption_links_out_and_in(self):
        inflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('4'),
        )
        outflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-02',
            movement_type='sale_out', qty=Decimal('-6'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('0'),
        )
        alloc = StockConsumption.objects.create(
            out_movement=outflow, in_movement=inflow,
            qty=Decimal('6'), unit_cost=Decimal('5'),
        )
        self.assertEqual(alloc.in_movement, inflow)
        self.assertEqual(alloc.out_movement, outflow)
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.StockMovementModelTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `cannot import name 'StockMovement'`.

- [ ] **Step 3: Tambah model**

Append ke `apps/inventory/models.py`:

```python
class StockMovement(models.Model):
    """Append-only authoritative stock ledger.

    Inflow rows (qty > 0) carry remaining_qty (FIFO layer). Outflow rows
    (qty < 0) have remaining_qty = 0 and link to consumed inflow layers via
    StockConsumption. Isolated per Entitas Bisnis (hierarchical).
    """
    MOVEMENT_TYPE_CHOICES = [
        ('purchase_in', 'Pembelian Masuk'),
        ('sale_out', 'Penjualan Keluar'),
        ('production_in', 'Produksi Masuk (FG)'),
        ('production_out', 'Produksi Keluar (RM)'),
        ('saldo_awal', 'Saldo Awal'),
    ]
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase', on_delete=models.PROTECT,
        related_name='stock_movements', verbose_name='Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='stock_movements', verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements_lv2',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements_lv3',
        verbose_name='Entitas Bisnis Lv3',
    )
    tanggal = models.DateField(db_index=True, verbose_name='Tanggal')
    movement_type = models.CharField(
        max_length=20, choices=MOVEMENT_TYPE_CHOICES, db_index=True,
        verbose_name='Jenis Pergerakan',
    )
    qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name='Qty (signed, base uom)',
    )
    unit_cost = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Biaya Satuan',
    )
    remaining_qty = models.DecimalField(
        max_digits=15, decimal_places=4, default=Decimal('0'),
        verbose_name='Sisa Qty (layer inflow)',
    )
    source_content_type = models.ForeignKey(
        'contenttypes.ContentType', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey('source_content_type', 'source_object_id')
    legacy_fifo_batch = models.ForeignKey(
        'purchase.FIFOBatch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='FIFOBatch (mirror)',
    )
    legacy_inventory_record = models.ForeignKey(
        'inventory.InventoryRecord', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='InventoryRecord (mirror)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        ordering = ['tanggal', 'created_at']
        indexes = [
            models.Index(fields=['item', 'entitas_bisnis', 'remaining_qty'],
                         name='idx_sm_item_eb_remaining'),
            models.Index(fields=['item', 'tanggal'], name='idx_sm_item_tanggal'),
            models.Index(fields=['source_content_type', 'source_object_id'],
                         name='idx_sm_source'),
        ]

    def __str__(self) -> str:
        return f'{self.item.item_id} | {self.movement_type} | {self.qty}'


class StockConsumption(models.Model):
    """Allocation linking an outflow movement to the inflow layer it consumed."""
    out_movement = models.ForeignKey(
        StockMovement, on_delete=models.CASCADE, related_name='consumptions_out',
        verbose_name='Movement Keluar',
    )
    in_movement = models.ForeignKey(
        StockMovement, on_delete=models.PROTECT, related_name='consumptions_in',
        verbose_name='Layer Inflow',
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Qty Dialokasikan')
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Biaya Layer')

    class Meta:
        verbose_name = 'Stock Consumption'
        verbose_name_plural = 'Stock Consumptions'
        indexes = [
            models.Index(fields=['out_movement'], name='idx_sc_out'),
            models.Index(fields=['in_movement'], name='idx_sc_in'),
        ]

    def __str__(self) -> str:
        return f'{self.out_movement_id} → {self.in_movement_id} × {self.qty}'
```

Tambahkan import di bagian atas `apps/inventory/models.py` (setelah `from django.db import models`):

```python
from decimal import Decimal
from django.contrib.contenttypes.fields import GenericForeignKey
```

(`from django.utils import timezone` sudah ada; jangan duplikat.)

- [ ] **Step 4: Buat file ledger dengan exception**

Create `apps/inventory/ledger.py`:

```python
"""Authoritative stock ledger engine — inflow, consumption, reversal, queries.

All quantities are in the item's base uom (Decimal). Bulk items (RMB/FGB/ITMB)
use the existing value-based convention (qty=1, unit_cost=total_value).
"""
from decimal import Decimal


class InsufficientStockError(ValueError):
    """Raised when consumption cannot be satisfied within the EB hierarchy."""
```

- [ ] **Step 5: Buat migrasi**

Run: `python manage.py makemigrations inventory --settings=naveda_integra.settings.test`
Expected: `apps/inventory/migrations/0005_stockmovement_stockconsumption.py` dibuat.

- [ ] **Step 6: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.StockMovementModelTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test).

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/models.py apps/inventory/ledger.py apps/inventory/tests.py apps/inventory/migrations/0005_stockmovement_stockconsumption.py
git commit -m "feat(inventory): add StockMovement + StockConsumption ledger models"
```

---

### Task 2: FK `entitas_bisnis_lv2`/`lv3` pada `ProductionOrder`

**Files:**
- Modify: `apps/manufacturing/models.py` (class `ProductionOrder`, tambah 2 FK setelah `entitas_bisnis`)
- Modify: `apps/manufacturing/tests.py` (tambah test)
- Migration: `apps/manufacturing/migrations/0007_productionorder_eb_lv2_lv3.py`

**Interfaces:**
- Produces: `ProductionOrder.entitas_bisnis_lv2`, `.entitas_bisnis_lv3` (FK nullable).

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/manufacturing/tests.py`:

```python
class ProductionOrderEBLevelTests(TestCase):
    def test_production_order_has_lv2_lv3(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.manufacturing.models import ProductionOrder
        tipe = TipeEntitas.objects.create(nama='PT')
        eb = EntitasBisnis.objects.create(nama='PT X', tipe_entitas=tipe)
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Divisi')
        lv3 = EntitasBisnisLv3.objects.create(parent_lv2=lv2, nama='Outlet')
        # Field wajib lain di-skip dgn hanya cek atribut model, bukan create penuh:
        self.assertTrue(hasattr(ProductionOrder, 'entitas_bisnis_lv2'))
        self.assertTrue(hasattr(ProductionOrder, 'entitas_bisnis_lv3'))
        field2 = ProductionOrder._meta.get_field('entitas_bisnis_lv2')
        field3 = ProductionOrder._meta.get_field('entitas_bisnis_lv3')
        self.assertTrue(field2.null)
        self.assertTrue(field3.null)
```

Pastikan `from django.test import TestCase` sudah diimpor di file (biasanya sudah).

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.manufacturing.tests.ProductionOrderEBLevelTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `ProductionOrder has no field 'entitas_bisnis_lv2'`.

- [ ] **Step 3: Tambah field**

Di `apps/manufacturing/models.py`, tepat setelah blok `entitas_bisnis = models.ForeignKey(...)` (baris ~105-110) dalam `ProductionOrder`, sisipkan:

```python
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT,
        null=True, blank=True, related_name='production_orders_lv2',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT,
        null=True, blank=True, related_name='production_orders_lv3',
        verbose_name='Entitas Bisnis Lv3',
    )
```

- [ ] **Step 4: Buat migrasi**

Run: `python manage.py makemigrations manufacturing --settings=naveda_integra.settings.test`
Expected: `apps/manufacturing/migrations/0007_productionorder_eb_lv2_lv3.py`.

- [ ] **Step 5: Jalankan test — harus lulus**

Run: `python manage.py test apps.manufacturing.tests.ProductionOrderEBLevelTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/manufacturing/models.py apps/manufacturing/tests.py apps/manufacturing/migrations/0007_productionorder_eb_lv2_lv3.py
git commit -m "feat(manufacturing): add lv2/lv3 EB fields to ProductionOrder"
```

---

### Task 3: `record_inflow` + helper tier kandidat + `get_available_stock`

**Files:**
- Modify: `apps/inventory/ledger.py`
- Modify: `apps/inventory/tests.py`

**Interfaces:**
- Consumes: `StockMovement` (Task 1).
- Produces:
  - `apps.inventory.ledger.record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal, movement_type, source=None, *, legacy_fifo_batch=None, legacy_inventory_record=None) -> StockMovement`
  - `apps.inventory.ledger._candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3) -> list[tuple[str, str, QuerySet]]`
  - `apps.inventory.ledger.requested_level(eb_lv2, eb_lv3) -> str`
  - `apps.inventory.ledger.get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None) -> Decimal`

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class RecordInflowTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.item = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')

    def test_record_inflow_creates_layer(self):
        from apps.inventory.ledger import record_inflow
        mv = record_inflow(
            self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
            '2026-01-01', 'purchase_in',
        )
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertEqual(mv.movement_type, 'purchase_in')

    def test_available_stock_lv1_only(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in')
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('5'),
                      '2026-01-02', 'purchase_in')
        self.assertEqual(get_available_stock(self.item, self.eb), Decimal('14'))

    def test_available_stock_hierarchical_sums_parent(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        # 6 di lv3, 10 di lv1 → dari sudut pandang lv3 tersedia 16 (naik ke induk)
        record_inflow(self.item, self.eb, self.lv2, self.lv3, Decimal('6'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in')
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3),
            Decimal('16'),
        )

    def test_available_stock_sibling_isolated(self):
        from apps.entitas_bisnis.models import EntitasBisnisLv3
        from apps.inventory.ledger import record_inflow, get_available_stock
        sibling = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        record_inflow(self.item, self.eb, self.lv2, self.lv3, Decimal('6'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        # Dari sudut pandang sibling (Outlet B), stok Outlet A tak terlihat (0)
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, sibling),
            Decimal('0'),
        )
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.RecordInflowTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `cannot import name 'record_inflow'`.

- [ ] **Step 3: Implementasi**

Append ke `apps/inventory/ledger.py`:

```python
from django.contrib.contenttypes.models import ContentType

from .models import StockMovement, StockConsumption


def requested_level(eb_lv2, eb_lv3) -> str:
    if eb_lv3 is not None:
        return 'lv3'
    if eb_lv2 is not None:
        return 'lv2'
    return 'lv1'


def _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
    """Return [(level_label, eb_name, queryset), ...] closest EB node first.

    Each queryset selects inflow layers (remaining_qty > 0) at that tier,
    FIFO-ordered. Sibling branches are never included.
    """
    base = StockMovement.objects.filter(item=item, remaining_qty__gt=0)
    tiers = []
    if eb_lv3 is not None:
        tiers.append((
            'lv3', eb_lv3.nama,
            base.filter(entitas_bisnis_lv3=eb_lv3).order_by('tanggal', 'created_at'),
        ))
    if eb_lv2 is not None:
        tiers.append((
            'lv2', eb_lv2.nama,
            base.filter(entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3__isnull=True)
                .order_by('tanggal', 'created_at'),
        ))
    tiers.append((
        'lv1', eb_lv1.nama,
        base.filter(entitas_bisnis=eb_lv1, entitas_bisnis_lv2__isnull=True,
                    entitas_bisnis_lv3__isnull=True)
            .order_by('tanggal', 'created_at'),
    ))
    return tiers


def get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None) -> Decimal:
    from django.db.models import Sum
    total = Decimal('0')
    for _level, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        agg = qs.aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0')
        total += agg
    return total


def record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal,
                  movement_type, source=None, *,
                  legacy_fifo_batch=None, legacy_inventory_record=None):
    """Create one inflow StockMovement layer (remaining_qty = qty)."""
    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    return StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=qty, unit_cost=unit_cost, remaining_qty=qty,
        source_content_type=ct, source_object_id=obj_id,
        legacy_fifo_batch=legacy_fifo_batch,
        legacy_inventory_record=legacy_inventory_record,
    )
```

- [ ] **Step 4: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.RecordInflowTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): record_inflow + hierarchical get_available_stock"
```

---

### Task 4: `consume_stock` non-bulk (FIFO + isolasi hierarkis + fallback report)

**Files:**
- Modify: `apps/inventory/ledger.py`
- Modify: `apps/inventory/tests.py`

**Interfaces:**
- Consumes: `_candidate_tiers`, `requested_level`, `StockMovement`, `StockConsumption`.
- Produces:
  - `apps.inventory.ledger.ConsumptionReport` (dataclass: `requested_level: str`, `used_fallback: bool`, `by_level: list[dict]`)
  - `apps.inventory.ledger.ConsumptionResult` (dataclass: `total_cost: Decimal`, `allocations: list[StockConsumption]`, `out_movement: StockMovement`, `report: ConsumptionReport`)
  - `apps.inventory.ledger.consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type, source=None, metode='fifo') -> ConsumptionResult`

Catatan: task ini menangani item **non-bulk**. Item bulk ditambahkan di Task 5.

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class ConsumeStockNonBulkTests(DjangoTestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            EntitasBisnis as EB, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EB.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        self.item = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')

    def _inflow(self, qty, cost, tanggal, lv2=None, lv3=None):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, lv2, lv3, Decimal(qty),
                             Decimal(cost), tanggal, 'purchase_in')

    def test_fifo_order_and_cogs(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        self._inflow('10', '8', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('12'),
                               '2026-01-03', 'sale_out')
        # 10@5 + 2@8 = 66
        self.assertEqual(result.total_cost, Decimal('66'))
        self.assertFalse(result.report.used_fallback)

    def test_insufficient_raises(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._inflow('5', '5', '2026-01-01')
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, None, None, Decimal('9'),
                          '2026-01-03', 'sale_out')

    def test_cross_branch_leak_prevented(self):
        """Regresi bug §A-4: jual di Outlet A tak boleh makan stok Outlet B."""
        from apps.inventory.ledger import consume_stock, InsufficientStockError, get_available_stock
        self._inflow('10', '5', '2026-01-01', lv2=self.lv2, lv3=self.lv3b)  # stok B
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, self.lv2, self.lv3a, Decimal('1'),
                          '2026-01-03', 'sale_out')
        # Stok B tetap utuh
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3b),
            Decimal('10'),
        )

    def test_hierarchical_fallback_to_parent(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('3', '5', '2026-01-01', lv2=self.lv2, lv3=self.lv3a)  # 3 di lv3
        self._inflow('10', '5', '2026-01-02')                              # 10 di lv1
        result = consume_stock(self.item, self.eb, self.lv2, self.lv3a, Decimal('8'),
                               '2026-01-03', 'sale_out')
        self.assertTrue(result.report.used_fallback)
        levels = {row['level']: row['qty'] for row in result.report.by_level}
        self.assertEqual(levels['lv3'], Decimal('3'))
        self.assertEqual(levels['lv1'], Decimal('5'))

    def test_remaining_qty_decremented(self):
        from apps.inventory.ledger import consume_stock
        layer = self._inflow('10', '5', '2026-01-01')
        consume_stock(self.item, self.eb, None, None, Decimal('4'),
                      '2026-01-03', 'sale_out')
        layer.refresh_from_db()
        self.assertEqual(layer.remaining_qty, Decimal('6'))
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.ConsumeStockNonBulkTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `cannot import name 'consume_stock'`.

- [ ] **Step 3: Implementasi**

Append ke `apps/inventory/ledger.py` (tambahkan `from dataclasses import dataclass, field` dan `from django.db import transaction` di bagian import atas file):

```python
@dataclass
class ConsumptionReport:
    requested_level: str
    used_fallback: bool
    by_level: list


@dataclass
class ConsumptionResult:
    total_cost: Decimal
    allocations: list
    out_movement: object
    report: ConsumptionReport


_LEVEL_RANK = {'lv1': 1, 'lv2': 2, 'lv3': 3}


@transaction.atomic
def consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
                  source=None, metode='fifo'):
    """Consume `qty` (base uom) of `item` within the EB hierarchy, FIFO.

    Non-bulk path. Raises InsufficientStockError if the hierarchy cannot cover qty.
    """
    req_level = requested_level(eb_lv2, eb_lv3)
    req_rank = _LEVEL_RANK[req_level]

    remaining = qty
    total_cost = Decimal('0')
    per_level = {}          # level -> {'eb_name': str, 'qty': Decimal}
    picked = []             # (in_layer, take)

    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        if remaining <= 0:
            break
        layers = qs.select_for_update()
        for layer in layers:
            if remaining <= 0:
                break
            take = min(layer.remaining_qty, remaining)
            if take <= 0:
                continue
            layer.remaining_qty -= take
            layer.save(update_fields=['remaining_qty'])
            total_cost += take * layer.unit_cost
            picked.append((layer, take))
            slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
            slot['qty'] += take
            remaining -= take

    if remaining > 0:
        raise InsufficientStockError(
            f'Stok tidak mencukupi untuk {item.item_id}. '
            f'Diminta {qty}, tersedia {qty - remaining} dalam hierarki EB.'
        )

    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    avg_cost = (total_cost / qty) if qty else Decimal('0')
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=-qty, unit_cost=avg_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=take, unit_cost=layer.unit_cost,
        )
        for layer, take in picked
    ]

    used_fallback = any(_LEVEL_RANK[lvl] < req_rank for lvl in per_level)
    by_level = [
        {'level': lvl, 'eb_name': per_level[lvl]['eb_name'], 'qty': per_level[lvl]['qty']}
        for lvl in sorted(per_level, key=lambda l: -_LEVEL_RANK[l])
    ]
    report = ConsumptionReport(
        requested_level=req_level, used_fallback=used_fallback, by_level=by_level,
    )
    return ConsumptionResult(
        total_cost=total_cost, allocations=allocations,
        out_movement=out_movement, report=report,
    )
```

- [ ] **Step 4: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.ConsumeStockNonBulkTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (5 test).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): consume_stock FIFO with hierarchical EB isolation + fallback report"
```

---

### Task 5: `consume_stock` cabang item bulk (value-based)

**Files:**
- Modify: `apps/inventory/ledger.py`
- Modify: `apps/inventory/tests.py`

**Interfaces:**
- Produces: `consume_stock` mendukung item bulk (`tipe_item in {'RMB','FGB','ITMB'}`) dengan konsumsi berbasis nilai; return `ConsumptionResult` di mana `qty` alokasi = 0 dan biaya diambil dari nilai layer (`remaining_qty * unit_cost`).

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class ConsumeStockBulkTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Pasir', tipe_item='RMB')

    def _bulk_inflow(self, total_value, tanggal):
        # Bulk: qty=1, unit_cost=total_value
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, None, None, Decimal('1'),
                             Decimal(total_value), tanggal, 'purchase_in')

    def test_bulk_value_deduction(self):
        from apps.inventory.ledger import consume_stock
        self._bulk_inflow('1000', '2026-01-01')
        self._bulk_inflow('500', '2026-01-02')
        # Konsumsi nilai 1200 → habiskan layer 1000, sisakan 300 dari layer 500
        result = consume_stock(self.item, self.eb, None, None, Decimal('1200'),
                               '2026-01-03', 'sale_out')
        self.assertEqual(result.total_cost, Decimal('1200'))

    def test_bulk_insufficient_value_raises(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._bulk_inflow('300', '2026-01-01')
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, None, None, Decimal('900'),
                          '2026-01-03', 'sale_out')
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.ConsumeStockBulkTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — konsumsi bulk mengurangi `remaining_qty` (0/1) bukan nilai, sehingga total_cost/hasil salah atau `InsufficientStockError` tak tepat.

- [ ] **Step 3: Implementasi cabang bulk**

Di `apps/inventory/ledger.py`, di awal `consume_stock` (setelah `req_level`/`req_rank` dihitung), tambahkan pengalihan:

```python
    is_bulk = item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if is_bulk:
        return _consume_stock_bulk(
            item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
            source, req_level, req_rank,
        )
```

Lalu tambahkan fungsi berikut setelah `consume_stock`:

```python
@transaction.atomic
def _consume_stock_bulk(item, eb_lv1, eb_lv2, eb_lv3, value, tanggal,
                        movement_type, source, req_level, req_rank):
    """Bulk value-based consumption. `value` is the amount of stock VALUE to deduct.

    Layer value = remaining_qty * unit_cost (qty is 0..1). Deduct proportionally
    by reducing remaining_qty so remaining value drops by the taken amount.
    """
    remaining_value = value
    total_cost = Decimal('0')
    per_level = {}
    picked = []  # (layer, value_taken)

    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3):
        if remaining_value <= 0:
            break
        for layer in qs.select_for_update():
            if remaining_value <= 0:
                break
            layer_value = layer.remaining_qty * layer.unit_cost
            take_value = min(layer_value, remaining_value)
            if take_value <= 0:
                continue
            # reduce remaining_qty so its value drops by take_value
            layer.remaining_qty = ((layer_value - take_value) / layer.unit_cost
                                   if layer.unit_cost else Decimal('0'))
            layer.save(update_fields=['remaining_qty'])
            total_cost += take_value
            picked.append((layer, take_value))
            slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
            slot['qty'] += take_value
            remaining_value -= take_value

    if remaining_value > 0:
        raise InsufficientStockError(
            f'Nilai stok bulk tidak mencukupi untuk {item.item_id}. '
            f'Diminta {value}, tersedia {value - remaining_value}.'
        )

    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        tanggal=tanggal, movement_type=movement_type,
        qty=Decimal('0'), unit_cost=total_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=Decimal('0'), unit_cost=layer.unit_cost,
        )
        for layer, _tv in picked
    ]
    used_fallback = any(_LEVEL_RANK[lvl] < req_rank for lvl in per_level)
    by_level = [
        {'level': lvl, 'eb_name': per_level[lvl]['eb_name'], 'qty': per_level[lvl]['qty']}
        for lvl in sorted(per_level, key=lambda l: -_LEVEL_RANK[l])
    ]
    report = ConsumptionReport(
        requested_level=req_level, used_fallback=used_fallback, by_level=by_level,
    )
    return ConsumptionResult(
        total_cost=total_cost, allocations=allocations,
        out_movement=out_movement, report=report,
    )
```

- [ ] **Step 4: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.ConsumeStockBulkTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS (2 test).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): bulk value-based branch in consume_stock"
```

---

### Task 6: Mirror ke ledger lama + `reverse_movements`

**Files:**
- Modify: `apps/inventory/ledger.py`
- Modify: `apps/inventory/tests.py`

**Interfaces:**
- Produces:
  - `consume_stock`/`_consume_stock_bulk` memirror pengurangan ke `layer.legacy_fifo_batch.remaining_qty` dan `layer.legacy_inventory_record.quantity` (non-bulk) atau nilai (bulk).
  - `apps.inventory.ledger.reverse_movements(source) -> None` — pulihkan layer inflow, hapus outflow + alokasi, pulihkan mirror.

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class MirrorAndReverseTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def _inflow_with_legacy(self, qty, cost, tanggal):
        from apps.purchase.models import FIFOBatch
        from apps.inventory.models import InventoryRecord
        from apps.inventory.ledger import record_inflow
        batch = FIFOBatch.objects.create(
            item=self.item, tanggal=tanggal, quantity_in=Decimal(qty),
            unit_price=Decimal(cost), remaining_qty=Decimal(qty),
        )
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal(qty),
            unit_price=Decimal(cost), tanggal=tanggal,
        )
        mv = record_inflow(self.item, self.eb, None, None, Decimal(qty), Decimal(cost),
                          tanggal, 'purchase_in',
                          legacy_fifo_batch=batch, legacy_inventory_record=rec)
        return mv, batch, rec

    def test_consume_mirrors_legacy(self):
        from apps.inventory.ledger import consume_stock
        mv, batch, rec = self._inflow_with_legacy('10', '5', '2026-01-01')
        consume_stock(self.item, self.eb, None, None, Decimal('4'),
                      '2026-01-03', 'sale_out')
        batch.refresh_from_db(); rec.refresh_from_db()
        self.assertEqual(batch.remaining_qty, Decimal('6'))
        self.assertEqual(rec.quantity, Decimal('6'))

    def test_reverse_restores_everything(self):
        from apps.inventory.ledger import consume_stock, reverse_movements
        from apps.inventory.models import StockMovement, StockConsumption
        mv, batch, rec = self._inflow_with_legacy('10', '5', '2026-01-01')
        item2 = self.item
        # gunakan objek sumber sederhana: pakai InventoryRecord rec sbg source
        result = consume_stock(self.item, self.eb, None, None, Decimal('4'),
                               '2026-01-03', 'sale_out', source=rec)
        reverse_movements(rec)
        mv.refresh_from_db(); batch.refresh_from_db(); rec.refresh_from_db()
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertEqual(batch.remaining_qty, Decimal('10'))
        self.assertEqual(rec.quantity, Decimal('10'))
        self.assertFalse(
            StockMovement.objects.filter(movement_type='sale_out').exists())
        self.assertFalse(StockConsumption.objects.exists())
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.MirrorAndReverseTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — mirror tak diperbarui / `reverse_movements` belum ada.

- [ ] **Step 3: Tambah mirror di konsumsi**

Di `apps/inventory/ledger.py`, buat helper mirror dan panggil saat mengurangi layer. Tambahkan fungsi:

```python
def _mirror_decrement(layer, take_qty, take_value):
    """Mirror a consumption decrement onto linked legacy rows.

    Non-bulk uses take_qty; bulk uses take_value (reduces InventoryRecord.total_value
    and FIFOBatch remaining value)."""
    batch = layer.legacy_fifo_batch
    rec = layer.legacy_inventory_record
    is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if batch is not None:
        if is_bulk:
            cur = batch.remaining_qty * batch.unit_price
            batch.remaining_qty = ((cur - take_value) / batch.unit_price
                                   if batch.unit_price else Decimal('0'))
        else:
            batch.remaining_qty -= take_qty
        batch.save(update_fields=['remaining_qty'])
    if rec is not None:
        if is_bulk:
            rec.total_value = (rec.total_value or Decimal('0')) - take_value
            rec.unit_price = rec.total_value
            rec.save(update_fields=['total_value', 'unit_price'])
        else:
            rec.quantity -= take_qty
            rec.total_value = rec.quantity * rec.unit_price
            rec.save(update_fields=['quantity', 'total_value'])
```

Di `consume_stock` (non-bulk), pada blok setelah `layer.save(update_fields=['remaining_qty'])`, tambahkan:

```python
            _mirror_decrement(layer, take, take * layer.unit_cost)
```

Di `_consume_stock_bulk`, setelah `layer.save(update_fields=['remaining_qty'])`, tambahkan:

```python
            _mirror_decrement(layer, Decimal('0'), take_value)
```

- [ ] **Step 4: Tambah `reverse_movements`**

Append ke `apps/inventory/ledger.py`:

```python
@transaction.atomic
def reverse_movements(source):
    """Reverse all outflow movements produced by `source`: restore inflow layers
    (and legacy mirrors), delete allocations and outflow rows."""
    ct = ContentType.objects.get_for_model(type(source))
    outflows = StockMovement.objects.filter(
        source_content_type=ct, source_object_id=source.pk,
        qty__lte=0,
    ).exclude(movement_type__in=('purchase_in', 'production_in', 'saldo_awal'))
    for out in outflows.select_for_update():
        for alloc in out.consumptions_out.select_related('in_movement').all():
            layer = alloc.in_movement
            is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            if is_bulk:
                # restore value: qty alloc is 0; use alloc.unit_cost * ? — bulk stores
                # value in out.unit_cost total; restore proportional via layer unit_cost.
                # We restore by recomputing from stored allocation value is not kept,
                # so restore using out.unit_cost split evenly is unsafe. Bulk reversal
                # restores the FULL out movement value across its layers by qty=0;
                # instead restore remaining_qty using saved unit_cost & value.
                restore_value = alloc.unit_cost * Decimal('0')  # placeholder guard
                # Bulk value restore: recompute from mirror is complex; restore layer
                # to pre-consumption by adding back the value taken, tracked below.
                _restore_bulk_layer(layer, alloc, out)
            else:
                layer.remaining_qty += alloc.qty
                layer.save(update_fields=['remaining_qty'])
                _mirror_restore(layer, alloc.qty, Decimal('0'))
        out.consumptions_out.all().delete()
    outflows.delete()
```

**Penting (bulk reversal):** karena `StockConsumption.qty = 0` untuk bulk, nilai yang dikonsumsi per layer tidak tersimpan. Untuk mendukung reversal bulk yang presisi, ubah Task 5/6: **simpan nilai konsumsi bulk pada `StockConsumption.qty`** sebagai *nilai* (bukan 0). Terapkan koreksi berikut sebelum lanjut:

- Di `_consume_stock_bulk`, ganti pembuatan `StockConsumption(... qty=Decimal('0') ...)` menjadi `qty=take_value` (rekam nilai yang diambil), dan `unit_cost=layer.unit_cost`.
- Hapus fungsi `_restore_bulk_layer` dan cabang bulk rumit di atas; gunakan reversal seragam:

Ganti isi loop `for alloc ...` di `reverse_movements` dengan versi seragam ini:

```python
        for alloc in out.consumptions_out.select_related('in_movement').all():
            layer = alloc.in_movement
            is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            if is_bulk:
                take_value = alloc.qty  # bulk: qty column stores value taken
                cur = layer.remaining_qty * layer.unit_cost
                layer.remaining_qty = ((cur + take_value) / layer.unit_cost
                                       if layer.unit_cost else Decimal('0'))
                layer.save(update_fields=['remaining_qty'])
                _mirror_restore(layer, Decimal('0'), take_value)
            else:
                layer.remaining_qty += alloc.qty
                layer.save(update_fields=['remaining_qty'])
                _mirror_restore(layer, alloc.qty, Decimal('0'))
```

Dan tambahkan `_mirror_restore` (kebalikan `_mirror_decrement`):

```python
def _mirror_restore(layer, take_qty, take_value):
    batch = layer.legacy_fifo_batch
    rec = layer.legacy_inventory_record
    is_bulk = layer.item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if batch is not None:
        if is_bulk:
            cur = batch.remaining_qty * batch.unit_price
            batch.remaining_qty = ((cur + take_value) / batch.unit_price
                                   if batch.unit_price else Decimal('0'))
        else:
            batch.remaining_qty += take_qty
        batch.save(update_fields=['remaining_qty'])
    if rec is not None:
        if is_bulk:
            rec.total_value = (rec.total_value or Decimal('0')) + take_value
            rec.unit_price = rec.total_value
            rec.save(update_fields=['total_value', 'unit_price'])
        else:
            rec.quantity += take_qty
            rec.total_value = rec.quantity * rec.unit_price
            rec.save(update_fields=['quantity', 'total_value'])
```

Juga: di Task 5 test `ConsumeStockBulkTests` tak memeriksa `alloc.qty`, jadi perubahan ini kompatibel.

- [ ] **Step 5: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.MirrorAndReverseTests apps.inventory.tests.ConsumeStockBulkTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): legacy mirror on consume + reverse_movements"
```

---

### Task 7: Integrasi Purchase inflow (dual-write dengan tautan legacy)

**Files:**
- Modify: `apps/purchase/services.py` (`create_fifo_batches` & `create_inventory_records`, atau tambahkan fungsi orkestrasi `create_stock_movements`)
- Modify: `apps/purchase/tests.py`

**Interfaces:**
- Produces: fungsi `apps.purchase.services.create_stock_movements(purchase_header) -> list[StockMovement]` yang membuat layer inflow tertaut ke `FIFOBatch` + `InventoryRecord` yang baru dibuat.

Catatan desain: `create_fifo_batches` dan `create_inventory_records` saat ini berjalan terpisah tanpa saling tahu. Agar penautan 1:1 mudah, buat satu fungsi orkestrasi baru yang dipanggil setelah keduanya, mencocokkan batch↔record via `purchase_item`.

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/purchase/tests.py` (gunakan pola setUp EB/Item yang sudah ada di file; jika perlu, buat kelas mandiri):

```python
class CreateStockMovementsTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        from apps.purchase.models import (
            ItemMasterPurchase, SubTransactionType, PurchaseHeader,
            PurchaseEntitasBisnis, PurchaseItem,
        )
        from apps.master_data.models import Akun
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.akun = Akun.objects.create(kode='1.1.1', nama='Kas')
        self.akun2 = Akun.objects.create(kode='1.2.1', nama='Persediaan')
        self.stt = SubTransactionType.objects.create(
            nama='Pembelian', module='purchase', direction='inflow',
            default_offset_account=self.akun,
        )
        self.header = PurchaseHeader.objects.create(tanggal='2026-01-01')
        self.peb = PurchaseEntitasBisnis.objects.create(
            purchase_header=self.header, entitas_bisnis=self.eb)
        self.pi = PurchaseItem.objects.create(
            purchase_eb=self.peb, item=self.item, sub_transaction_type=self.stt,
            coa_account=self.akun2, offset_coa_account=self.akun,
            quantity=Decimal('10'), unit_price=Decimal('5'))

    def test_creates_linked_stock_movement(self):
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
        )
        from apps.inventory.models import StockMovement
        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        movements = create_stock_movements(self.header)
        self.assertEqual(len(movements), 1)
        mv = movements[0]
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertIsNotNone(mv.legacy_fifo_batch)
        self.assertIsNotNone(mv.legacy_inventory_record)
        self.assertEqual(mv.entitas_bisnis, self.eb)
```

Pastikan `from decimal import Decimal` dan `from django.test import TestCase` ada di file (biasanya sudah).

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.purchase.tests.CreateStockMovementsTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `cannot import name 'create_stock_movements'`.

- [ ] **Step 3: Implementasi**

Append ke `apps/purchase/services.py`:

```python
def create_stock_movements(purchase_header: PurchaseHeader) -> list:
    """Create StockMovement inflow layers linked to the FIFOBatch + InventoryRecord
    that create_fifo_batches / create_inventory_records already made for this purchase."""
    from apps.inventory.ledger import record_inflow
    from apps.inventory.models import InventoryRecord

    movements = []
    for eb_group in purchase_header.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
    ).all():
        for pi in eb_group.items.select_related('item', 'sub_transaction_type').all():
            if pi.item.tipe_item not in ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'):
                continue
            if pi.sub_transaction_type.direction != 'inflow':
                continue
            is_bulk = pi.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            batch = pi.fifo_batches.order_by('-created_at').first()
            rec = InventoryRecord.objects.filter(purchase_item=pi).order_by('-created_at').first()
            qty = Decimal('1') if is_bulk else pi.quantity
            unit_cost = pi.total_value if is_bulk else pi.unit_price
            mv = record_inflow(
                pi.item, eb_group.entitas_bisnis,
                eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                qty, unit_cost, purchase_header.tanggal, 'purchase_in',
                source=pi, legacy_fifo_batch=batch, legacy_inventory_record=rec,
            )
            movements.append(mv)
    return movements
```

- [ ] **Step 4: Panggil dari view purchase**

Di `apps/purchase/views.py`, setelah tiap pasangan `create_fifo_batches(purchase)` + `create_inventory_records(purchase)` (baris ~1426-1427 dan ~1468-1469), tambahkan baris pemanggilan. Impor fungsi di blok import (baris ~30-32):

```python
    create_automated_journals, create_fifo_batches, create_stock_movements,
```

Lalu setelah kedua create (dua lokasi):

```python
                create_stock_movements(purchase)
```

- [ ] **Step 5: Jalankan test — harus lulus**

Run: `python manage.py test apps.purchase.tests.CreateStockMovementsTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/purchase/services.py apps/purchase/views.py apps/purchase/tests.py
git commit -m "feat(purchase): dual-write StockMovement inflow linked to legacy ledgers"
```

---

### Task 8: Integrasi Sales outflow (ganti isi `process_sales_fifo` + `reverse_sales_fifo`)

**Files:**
- Modify: `apps/sales/services.py` (`process_sales_fifo`, `reverse_sales_fifo`; tambah bangun `SalesItemFIFOAllocation` dari hasil `consume_stock`)
- Modify: `apps/sales/views.py` (tampilkan `messages.warning` saat fallback)
- Modify: `apps/sales/tests.py`

**Interfaces:**
- Consumes: `consume_stock`, `reverse_movements`.
- Produces: `process_sales_fifo` mengonsumsi via engine baru (isolasi EB), memirror otomatis; return `list[ConsumptionReport]` untuk notifikasi.

Catatan: SalesEntitasBisnis punya `entitas_bisnis`/`_lv2`/`_lv3`. SalesItem dipakai sebagai `source` konsumsi (satu out_movement per SalesItem).

- [ ] **Step 1: Tulis test yang gagal (isolasi + fallback di level sales)**

Append ke `apps/sales/tests.py` (ikuti pola setUp yang ada; buat item + EB lv2/lv3 + inflow via `record_inflow`):

```python
class SalesEBIsolationTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.purchase.models import ItemMasterPurchase
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        self.item = ItemMasterPurchase.objects.create(
            nama='Gula', tipe_item='RM', coa_account=None)

    def _sales_with_item(self, lv2, lv3, qty):
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        header = SalesHeader.objects.create(tanggal='2026-01-03')
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
            entitas_bisnis_lv2=lv2, entitas_bisnis_lv3=lv3)
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, quantity=Decimal(qty),
            unit_price=Decimal('10'), total_sales=Decimal('10') * Decimal(qty))
        return header

    def test_sale_does_not_consume_sibling_stock(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.sales.services import process_sales_fifo
        # stok hanya di Outlet B
        record_inflow(self.item, self.eb, self.lv2, self.lv3b, Decimal('10'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        header = self._sales_with_item(self.lv2, self.lv3a, '1')
        with self.assertRaises(Exception):
            process_sales_fifo(header)
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3b),
            Decimal('10'))
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.sales.tests.SalesEBIsolationTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `process_sales_fifo` lama tak memfilter EB, konsumsi berhasil (tak raise), stok B berkurang.

- [ ] **Step 3: Tulis ulang `process_sales_fifo`**

Di `apps/sales/services.py`, ganti isi `process_sales_fifo` (baris ~223-337) dengan versi berbasis engine. Simpan bentuk lama sebagai referensi di git history. Versi baru:

```python
def process_sales_fifo(sales_header: SalesHeader) -> list:
    """FIFO/value outflow for all sale items via the authoritative stock ledger.

    Returns a list of ConsumptionReport (for fallback UI notifications).
    Updates cogs_amount + inventory_account on each SalesItem, and mirrors to
    FIFOBatch / InventoryRecord automatically (via linked layers).
    """
    from apps.inventory.ledger import consume_stock, InsufficientStockError
    from decimal import Decimal as _D

    reports = []
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.select_related(
            'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
        ).all():
            for si in eb_group.items.select_related('item').all():
                is_bulk = si.item.tipe_item in ('RMB', 'FGB', 'ITMB')
                if is_bulk:
                    amount = si.hpp_terpakai or _D('0')
                    if amount <= 0:
                        continue
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        amount, sales_header.tanggal, 'sale_out', source=si)
                    si.cogs_amount = result.total_cost
                else:
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        si.quantity, sales_header.tanggal, 'sale_out', source=si)
                    si.cogs_amount = result.total_cost
                si.inventory_account_id = si.item.coa_account_id
                si.save()
                _build_sales_allocations(si, result)
                reports.append(result.report)
    return reports


def _build_sales_allocations(si, result):
    """Rebuild SalesItemFIFOAllocation rows from StockConsumption for legacy display."""
    for alloc in result.allocations:
        rec = alloc.in_movement.legacy_inventory_record
        if rec is None:
            continue
        SalesItemFIFOAllocation.objects.create(
            sales_item=si, inventory_record=rec,
            quantity_consumed=alloc.qty,
            cogs_amount=alloc.qty * alloc.unit_cost,
        )
```

- [ ] **Step 4: Tulis ulang `reverse_sales_fifo`**

Ganti isi `reverse_sales_fifo` (baris ~349-429) dengan:

```python
def reverse_sales_fifo(sales_header: SalesHeader) -> None:
    """Reverse stock consumption for a sales transaction via the ledger engine."""
    from apps.inventory.ledger import reverse_movements
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.all():
                reverse_movements(si)
                si.fifo_allocations.all().delete()
```

- [ ] **Step 5: Notifikasi fallback di view**

Di `apps/sales/views.py`, di titik `process_sales_fifo(sales)` (baris ~1029), ubah menjadi menangkap laporan dan tampilkan warning. Impor `messages` bila belum (`from django.contrib import messages`). Ganti:

```python
        reports = process_sales_fifo(sales)
        for rep in reports:
            if rep.used_fallback:
                sumber = ', '.join(
                    f"{row['qty']} dari {row['eb_name']} ({row['level']})"
                    for row in rep.by_level if row['level'] != rep.requested_level)
                messages.warning(
                    request,
                    f'Stok di level {rep.requested_level} tidak mencukupi; '
                    f'sebagian diambil dari induk: {sumber}.')
```

- [ ] **Step 6: Jalankan test — harus lulus**

Run: `python manage.py test apps.sales.tests.SalesEBIsolationTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 7: Jalankan seluruh test sales (regresi)**

Run: `python manage.py test apps.sales --settings=naveda_integra.settings.test -v 1`
Expected: test yang sudah ada tetap hijau (atau kegagalan yang murni pra-eksis django-axes login, bukan dari perubahan ini). Bila ada kegagalan terkait FIFO same-EB, perbaiki logika hingga hasil COGS identik sebelum lanjut.

- [ ] **Step 8: Commit**

```bash
git add apps/sales/services.py apps/sales/views.py apps/sales/tests.py
git commit -m "feat(sales): consume via authoritative stock ledger with EB isolation + fallback warnings"
```

---

### Task 9: Integrasi Manufacturing (konsumsi RM + FG inflow + form EB lv2/lv3)

**Files:**
- Modify: `apps/manufacturing/services.py` (`process_production` konsumsi RM via `consume_stock`; FG via `record_inflow`; `reverse_production`)
- Modify: `apps/manufacturing/forms.py` (tambah `entitas_bisnis_lv2`/`lv3` bila ada ModelForm ProductionOrder)
- Modify: `apps/manufacturing/tests.py`

**Interfaces:**
- Consumes: `consume_stock`, `record_inflow`, `reverse_movements`.
- Produces: konsumsi RM produksi terisolasi EB (lv1/lv2/lv3 dari ProductionOrder); FG jadi layer `production_in` tertaut mirror.

- [ ] **Step 1: Inspeksi titik integrasi**

Run: `grep -nE "_consume_fifo|FIFOBatch.objects.create|InventoryRecord.objects.create|def process_production|def reverse_production" apps/manufacturing/services.py`
Catat baris pembuatan FG FIFOBatch + InventoryRecord (≈377-397, 605-625) dan restore RM di reverse (≈641-685).

- [ ] **Step 2: Tulis test yang gagal**

Append ke `apps/manufacturing/tests.py` (pakai helper `_make_eb`/fixture yang ada di file):

```python
class ProductionEBIsolationTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.purchase.models import ItemMasterPurchase
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Pabrik A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Pabrik B')
        self.rm = ItemMasterPurchase.objects.create(nama='Tepung', tipe_item='RM')

    def test_production_consume_isolated_by_eb(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError, record_inflow
        # stok RM hanya di Pabrik B
        record_inflow(self.rm, self.eb, self.lv2, self.lv3b, Decimal('100'),
                      Decimal('2'), '2026-01-01', 'purchase_in')
        # produksi di Pabrik A minta 10 → harus gagal (tak lihat stok B)
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.rm, self.eb, self.lv2, self.lv3a, Decimal('10'),
                          '2026-01-03', 'production_out')
```

(Test unit-level ini mengunci perilaku engine untuk konteks produksi; integrasi penuh `process_production` diverifikasi oleh test manufacturing yang ada.)

- [ ] **Step 3: Ganti konsumsi RM di `process_production`**

Konteks aktual (baris ~342-351): loop `for line in bom.lines...` memanggil `_consume_fifo(line.raw_material_id, qty_needed)` lalu membuat `ProductionRMConsumption` per `(batch, qty)` dengan `fifo_batch=batch, unit_cost=batch.unit_price`. Ganti seluruh isi loop tersebut menjadi:

```python
        from apps.inventory.ledger import consume_stock
        for line in bom.lines.select_related('raw_material').all():
            qty_needed = line.qty_required * qty_produced
            _rm_result = consume_stock(
                line.raw_material, production_order.entitas_bisnis,
                production_order.entitas_bisnis_lv2, production_order.entitas_bisnis_lv3,
                qty_needed, production_order.tanggal, 'production_out',
                source=production_order)
            total_rm_cost += _rm_result.total_cost
            for alloc in _rm_result.allocations:
                ProductionRMConsumption.objects.create(
                    production_order=production_order,
                    bom_line=line,
                    fifo_batch=alloc.in_movement.legacy_fifo_batch,
                    qty_consumed=alloc.qty,
                    unit_cost=alloc.unit_cost,
                )
```

Catatan: `alloc.in_movement.legacy_fifo_batch` bisa `None` untuk stok yang tak punya mirror FIFOBatch — `ProductionRMConsumption.fifo_batch` harus mengizinkan null. Verifikasi field; bila `fifo_batch` non-null wajib, lewati baris jejak saat `legacy_fifo_batch is None` (guard `if alloc.in_movement.legacy_fifo_batch_id`).

- [ ] **Step 4: Ganti pembuatan FG jadi `record_inflow` tertaut**

Konteks aktual `process_production` (≈373-399): `fg_item = bom.finished_good`; FG FIFOBatch dibuat **tanpa variabel** (`FIFOBatch.objects.create(...)`); InventoryRecord disimpan sebagai `inv_record`; qty = `qty_produced`, biaya = `unit_cost`.

Pertama, tangkap FG batch ke variabel — ubah `FIFOBatch.objects.create(` (FG, `purchase_item=None`) menjadi:

```python
            fg_batch = FIFOBatch.objects.create(
```

Lalu, tepat setelah blok `inv_record = InventoryRecord.objects.create(...)` FG selesai, tambahkan:

```python
            from apps.inventory.ledger import record_inflow
            record_inflow(
                fg_item, entitas_bisnis,
                production_order.entitas_bisnis_lv2, production_order.entitas_bisnis_lv3,
                qty_produced, unit_cost, production_order.tanggal, 'production_in',
                source=production_order,
                legacy_fifo_batch=fg_batch, legacy_inventory_record=inv_record)
```

(`entitas_bisnis` sudah didefinisikan sebagai `production_order.entitas_bisnis` di awal `process_production` — verifikasi; jika tidak, pakai `production_order.entitas_bisnis`.)

- [ ] **Step 5: Ganti restore RM di `reverse_production`**

Di `reverse_production` (baris ~641), ganti blok restore RM FIFOBatch manual dengan:

```python
        from apps.inventory.ledger import reverse_movements
        reverse_movements(production_order)
```

Pertahankan penghapusan FG InventoryRecord/FIFOBatch legacy yang ada bila belum tercakup mirror; hindari double-delete (mirror FG dibuat via record_inflow tak menghapus legacy pada reverse — hapus manual seperti kode lama).

- [ ] **Step 6: Form EB lv2/lv3**

Jika ada `ProductionOrderForm` di `apps/manufacturing/forms.py`, tambahkan `'entitas_bisnis_lv2', 'entitas_bisnis_lv3'` ke `Meta.fields`. Bila tidak ada ModelForm, lewati (pemilihan EB via view/template lain — catat untuk verifikasi manual).

- [ ] **Step 7: Jalankan test**

Run: `python manage.py test apps.manufacturing.tests.ProductionEBIsolationTests apps.manufacturing --settings=naveda_integra.settings.test -v 1`
Expected: test baru PASS; test manufacturing lama tetap hijau (COGS produksi same-EB identik).

- [ ] **Step 8: Commit**

```bash
git add apps/manufacturing/services.py apps/manufacturing/forms.py apps/manufacturing/tests.py
git commit -m "feat(manufacturing): consume RM + emit FG via authoritative stock ledger, EB-isolated"
```

---

### Task 10: Backfill migration + command `reconcile_stock_ledger`

**Files:**
- Create: `apps/inventory/backfill.py` (logika backfill sebagai fungsi murni, dipanggil migrasi + testable)
- Create: `apps/inventory/migrations/0006_backfill_stock_movements.py`
- Create: `apps/inventory/management/__init__.py`, `apps/inventory/management/commands/__init__.py`
- Create: `apps/inventory/management/commands/reconcile_stock_ledger.py`
- Modify: `apps/inventory/tests.py`

**Interfaces:**
- Consumes: `FIFOBatch`, `InventoryRecord`, `StockMovement`.
- Produces:
  - `apps.inventory.backfill.backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem) -> int`
  - management command `reconcile_stock_ledger`.

- [ ] **Step 1: Tulis test backfill yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class BackfillStockMovementsTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_backfill_creates_layers_with_eb_and_links(self):
        from apps.purchase.models import FIFOBatch, PurchaseItem
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.inventory.backfill import backfill_stock_movements
        batch = FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01', quantity_in=Decimal('10'),
            unit_price=Decimal('5'), remaining_qty=Decimal('6'))
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('6'),
            unit_price=Decimal('5'), tanggal='2026-01-01')
        n = backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)
        self.assertEqual(n, 1)
        mv = StockMovement.objects.get()
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertEqual(mv.remaining_qty, Decimal('6'))
        self.assertEqual(mv.entitas_bisnis, self.eb)
        self.assertEqual(mv.legacy_fifo_batch_id, batch.id)
        self.assertEqual(mv.legacy_inventory_record_id, rec.id)
```

- [ ] **Step 2: Jalankan test — harus gagal**

Run: `python manage.py test apps.inventory.tests.BackfillStockMovementsTests --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `No module named 'apps.inventory.backfill'`.

- [ ] **Step 3: Tulis fungsi backfill**

Create `apps/inventory/backfill.py`:

```python
"""Backfill StockMovement inflow layers from existing FIFOBatch + InventoryRecord.

Driven by FIFOBatch (authoritative FIFO remaining/cost). EB attribution comes
from the batch's purchase_item.purchase_eb, or from a matching InventoryRecord
for saldo-awal batches. Historical outflows are NOT reconstructed; remaining_qty
is snapshotted from the current FIFOBatch state.
"""
from decimal import Decimal


def _eb_from_purchase_item(pi):
    peb = pi.purchase_eb
    return peb.entitas_bisnis, peb.entitas_bisnis_lv2, peb.entitas_bisnis_lv3


def backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem):
    """Create one inflow StockMovement per FIFOBatch. Returns count created.

    Idempotent: skips batches that already have a linked StockMovement.
    """
    created = 0
    for batch in FIFOBatch.objects.all().iterator():
        if StockMovement.objects.filter(legacy_fifo_batch=batch).exists():
            continue
        eb1 = eb2 = eb3 = None
        rec = None
        if batch.purchase_item_id:
            pi = PurchaseItem.objects.select_related(
                'purchase_eb__entitas_bisnis',
                'purchase_eb__entitas_bisnis_lv2',
                'purchase_eb__entitas_bisnis_lv3',
            ).get(pk=batch.purchase_item_id)
            eb1, eb2, eb3 = _eb_from_purchase_item(pi)
            rec = InventoryRecord.objects.filter(purchase_item=pi).order_by('created_at').first()
        else:
            rec = InventoryRecord.objects.filter(
                item=batch.item, tanggal=batch.tanggal, unit_price=batch.unit_price,
            ).order_by('created_at').first()
            if rec is not None:
                eb1 = rec.entitas_bisnis
                eb2 = rec.entitas_bisnis_lv2
                eb3 = rec.entitas_bisnis_lv3
        if eb1 is None:
            # EB tak teratribusi — lewati; dilaporkan oleh reconcile command.
            continue
        movement_type = 'purchase_in' if batch.purchase_item_id else 'saldo_awal'
        StockMovement.objects.create(
            item=batch.item, entitas_bisnis=eb1,
            entitas_bisnis_lv2=eb2, entitas_bisnis_lv3=eb3,
            tanggal=batch.tanggal, movement_type=movement_type,
            qty=batch.quantity_in, unit_cost=batch.unit_price,
            remaining_qty=batch.remaining_qty,
            legacy_fifo_batch=batch, legacy_inventory_record=rec,
        )
        created += 1
    return created
```

- [ ] **Step 4: Jalankan test — harus lulus**

Run: `python manage.py test apps.inventory.tests.BackfillStockMovementsTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 5: Buat migrasi data**

Create `apps/inventory/migrations/0006_backfill_stock_movements.py`:

```python
from django.db import migrations


def forwards(apps, schema_editor):
    from apps.inventory.backfill import backfill_stock_movements
    FIFOBatch = apps.get_model('purchase', 'FIFOBatch')
    InventoryRecord = apps.get_model('inventory', 'InventoryRecord')
    StockMovement = apps.get_model('inventory', 'StockMovement')
    PurchaseItem = apps.get_model('purchase', 'PurchaseItem')
    backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)


def backwards(apps, schema_editor):
    StockMovement = apps.get_model('inventory', 'StockMovement')
    StockMovement.objects.filter(legacy_fifo_batch__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0005_stockmovement_stockconsumption'),
        ('purchase', '0008_backfill_item_uom'),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

**Catatan:** `backfill_stock_movements` memakai `select_related`/`get` pada historical models. Historical model dari `apps.get_model` mendukung query manager standar & FK traversal, jadi aman. `StockMovement.objects.create` di historical model juga oke (semua field konkret).

- [ ] **Step 6: Tulis command rekonsiliasi**

Create `apps/inventory/management/__init__.py` (kosong), `apps/inventory/management/commands/__init__.py` (kosong), dan `apps/inventory/management/commands/reconcile_stock_ledger.py`:

```python
"""Reconcile StockMovement remaining vs legacy FIFOBatch/InventoryRecord."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.purchase.models import FIFOBatch
from apps.inventory.models import StockMovement, InventoryRecord


class Command(BaseCommand):
    help = 'Report drift between StockMovement and legacy stock ledgers.'

    def handle(self, *args, **options):
        drift = 0
        # 1. Per item: sum(StockMovement.remaining inflow) vs sum(FIFOBatch.remaining)
        items = set(FIFOBatch.objects.values_list('item_id', flat=True))
        items |= set(StockMovement.objects.values_list('item_id', flat=True))
        for item_id in sorted(i for i in items if i is not None):
            sm = (StockMovement.objects.filter(item_id=item_id, qty__gt=0)
                  .aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0'))
            fb = (FIFOBatch.objects.filter(item_id=item_id)
                  .aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0'))
            if sm != fb:
                drift += 1
                self.stdout.write(self.style.WARNING(
                    f'[item {item_id}] StockMovement={sm} vs FIFOBatch={fb} (diff {sm - fb})'))
        # 2. FIFOBatch tanpa StockMovement tertaut (EB tak teratribusi / anomali)
        orphan = FIFOBatch.objects.exclude(
            id__in=StockMovement.objects.filter(
                legacy_fifo_batch__isnull=False).values_list('legacy_fifo_batch_id', flat=True)
        ).count()
        if orphan:
            drift += 1
            self.stdout.write(self.style.WARNING(
                f'{orphan} FIFOBatch tanpa StockMovement tertaut (cek atribusi EB).'))
        if drift == 0:
            self.stdout.write(self.style.SUCCESS('Rekonsiliasi cocok: tidak ada drift.'))
        else:
            self.stdout.write(self.style.ERROR(f'Ditemukan {drift} kategori drift.'))
```

- [ ] **Step 7: Test command rekonsiliasi (smoke)**

Append ke `apps/inventory/tests.py`:

```python
class ReconcileCommandTests(DjangoTestCase):
    def test_reconcile_runs_clean(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('reconcile_stock_ledger', stdout=out)
        self.assertIn('Rekonsiliasi cocok', out.getvalue())
```

- [ ] **Step 8: Jalankan test**

Run: `python manage.py test apps.inventory.tests.ReconcileCommandTests apps.inventory.tests.BackfillStockMovementsTests --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/inventory/backfill.py apps/inventory/migrations/0006_backfill_stock_movements.py apps/inventory/management apps/inventory/tests.py
git commit -m "feat(inventory): backfill StockMovement from legacy ledgers + reconcile command"
```

---

### Task 11: Regression sweep + admin registration

**Files:**
- Modify: `apps/inventory/admin.py` (registrasi read-only `StockMovement`)

- [ ] **Step 1: Registrasi admin StockMovement (read-only, untuk audit)**

Append ke `apps/inventory/admin.py`:

```python
from apps.inventory.models import StockMovement, StockConsumption


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('item', 'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
                    'tanggal', 'movement_type', 'qty', 'unit_cost', 'remaining_qty')
    list_filter = ('movement_type', 'tanggal')
    search_fields = ('item__nama', 'item__item_id')
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(StockConsumption)
class StockConsumptionAdmin(admin.ModelAdmin):
    list_display = ('out_movement', 'in_movement', 'qty', 'unit_cost')

    def has_add_permission(self, request):
        return False
```

Pastikan `from django.contrib import admin` sudah ada di atas file.

- [ ] **Step 2: Jalankan seluruh test suite**

Run: `python manage.py test --settings=naveda_integra.settings.test -v 1`
Expected: tak ada regresi baru. Kegagalan yang tersisa hanya `django-axes` `AxesBackendRequestParameterRequired` pra-eksis (login di test setUp beberapa app) — bandingkan jumlah/traceback dengan kondisi sebelum Fase 2 bila ragu.

- [ ] **Step 3: Verifikasi migrasi konsisten**

Run: `python manage.py makemigrations --check --dry-run --settings=naveda_integra.settings.test`
Expected: hanya migrasi `pajak` pra-eksis yang mungkin muncul (di luar cakupan). Tidak ada perubahan model `inventory`/`manufacturing`/`purchase` yang belum termigrasi.

- [ ] **Step 4: Commit**

```bash
git add apps/inventory/admin.py
git commit -m "feat(inventory): read-only admin for StockMovement + StockConsumption; Fase 2 regression sweep"
```

---

## Self-Review

**Spec coverage:**
- StockMovement + StockConsumption model (§C.1, C.2) → Task 1. ✅
- ProductionOrder lv2/lv3 (§C.3) → Task 2. ✅
- record_inflow, get_available_stock hierarkis (§D.1, D.4) → Task 3. ✅
- consume_stock FIFO + isolasi hierarkis + fallback report (§D.2, D.7) → Task 4. ✅
- Item bulk value-based (§C.1) → Task 5. ✅
- Mirror ke ledger lama + reverse_movements (§D.2, D.3) → Task 6. ✅
- Purchase dual-write (§D.5) → Task 7. ✅
- Sales outflow + fallback UI (§D.5, D.7) → Task 8. ✅
- Manufacturing (§D.5) + form EB → Task 9. ✅
- Backfill + reconcile (§E) → Task 10. ✅
- Regresi + admin audit → Task 11. ✅
- Regresi bug §A-4 & isolasi sibling & fallback (§F.2, F.3) → test di Task 4 & 8 & 9. ✅
- Non-goals (§G): LIFO/Average, Warehouse, transfer/adjustment/opname/retur, hapus ledger lama — tidak disentuh. ✅

**Placeholder scan:** Task 6 sengaja memuat koreksi in-line (bulk `StockConsumption.qty` menyimpan nilai) — instruksinya eksplisit dan lengkap, bukan placeholder. Tidak ada TBD/TODO logika.

**Type consistency:** `consume_stock` → `ConsumptionResult(total_cost, allocations, out_movement, report)`; `report.by_level` = list of `{'level','eb_name','qty'}` konsisten dipakai di Task 4/5/8. `record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal, movement_type, source, *, legacy_fifo_batch, legacy_inventory_record)` konsisten Task 3/7/9/10. `_mirror_decrement`/`_mirror_restore(layer, take_qty, take_value)` konsisten Task 6. `backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)` konsisten Task 10 helper & migrasi.

**Catatan verifikasi manual (untuk pelaksana):** Task 9 mengasumsikan nama variabel FG (`fg_qty`, `fg_unit_cost`, `fg_batch`, `inv_record`) dan atribut `production_order.bom.finished_good` — WAJIB diverifikasi terhadap kode `process_production` aktual sebelum menempel; sesuaikan bila berbeda. Task 8 mengasumsikan `SalesItem.total_sales`/`hpp_terpakai`/`cogs_amount` (sudah dikonfirmasi ada di services lama).
