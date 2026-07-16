# Warehouse (Multi-Gudang) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambah dimensi lokasi fisik (`Warehouse`) ke ledger stok tunggal (`StockMovement`), di-scope ke bisnis/tenant (EntitasBisnis lv1), ortogonal terhadap dimensi akuntansi EB, dengan konsumsi terkunci-gudang (opsional, tanpa fallback antar gudang), lalu di-wire ke Pembelian, Penjualan, Manufaktur, dan Saldo Awal.

**Architecture:** `Warehouse` (master, `apps/inventory/models.py`) `FK → EntitasBisnis` (lv1). `StockMovement` dapat FK `warehouse` nullable. Engine di `apps/inventory/ledger.py` menerima `warehouse=None`: inflow menyimpan apa adanya; outflow dengan `warehouse` diisi memfilter layer **persis** gudang itu (tanpa fallback, tak menyentuh layer NULL), dengan `warehouse=None` = perilaku Fase 2 identik. Wiring per-baris (`PurchaseItem.warehouse`, `SalesItem.warehouse`), dua field di `ProductionOrder` (`warehouse_rm`, `warehouse_fg`), dan per-detail-row Saldo Awal (yang sekaligus menutup celah dual-write Fase 2: Saldo Awal persediaan belum menulis `StockMovement`).

**Tech Stack:** Django 6.0, PostgreSQL (prod) / SQLite in-memory (test), `django.contrib.contenttypes` GenericForeignKey (sudah dipakai `StockMovement.source`), Decimal untuk semua kuantitas/biaya. Grid item Pembelian/Penjualan berbasis JSON (bukan Django formset); form Manufaktur = `ModelForm`.

## Global Constraints

- Django >= 6.0. Semua kuantitas/biaya `DecimalField` (jangan float).
- Test dijalankan: `python manage.py test <path> --settings=naveda_integra.settings.test -v 2`.
- Verifikasi Postgres parity untuk task ledger & wiring (bukan hanya SQLite) — jalankan minimal test ledger & satu test wiring pada Postgres lokal sebelum menandai task selesai.
- Migrasi baru dibuat via `python manage.py makemigrations <app>` (penomoran otomatis menyambung dari HEAD tiap app). Sertakan migrasi mundur yang aman (default Django reversible untuk AddField/CreateModel).
- FIFO same-warehouse (atau `warehouse=None`) harus tetap identik hasilnya dengan Fase 2. Fase ini TIDAK mengubah costing.
- Item bulk = `RMB`/`FGB`/`ITMB` → value-based (qty=1, unit_cost=total_value). Non-bulk inventory = `RM`/`FG`/`ITM`.
- `consume_stock` gagal keras (`InsufficientStockError`), tidak diam-diam mengembalikan nilai salah.
- **Invariant tenant:** bila `warehouse` diisi pada movement apa pun, `warehouse.entitas_bisnis_id == movement.entitas_bisnis_id` (lv1) wajib benar. Divalidasi di ledger (fail-loud `ValueError`) dan di form.
- Hierarki EB: `EntitasBisnis` (lv1) = bisnis/tenant; `EntitasBisnisLv2`/`EntitasBisnisLv3` = cabang/sub-unit. Warehouse di-scope ke lv1.
- Granularitas gudang Pembelian/Penjualan = **per baris item** (sumber kebenaran); UI menyediakan toggle "seragam per grup" yang hanya mengisi semua baris dengan gudang sama.

---

### Task 1: Model `Warehouse` + admin

**Files:**
- Modify: `apps/inventory/models.py` (tambah model `Warehouse` sebelum `StockMovement`)
- Modify: `apps/inventory/admin.py` (register `Warehouse`)
- Test: `apps/inventory/tests.py` (append)
- Migration: `apps/inventory/migrations/` (via makemigrations)

**Interfaces:**
- Produces: `apps.inventory.models.Warehouse` dengan field `entitas_bisnis (FK EntitasBisnis)`, `kode`, `nama`, `alamat`, `is_active`, `created_at`; `unique_together = (entitas_bisnis, kode)`.

- [ ] **Step 1: Tulis test model yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class WarehouseModelTest(DjangoTestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        tipe = TipeEntitas.objects.create(nama='Retail-WHT')
        self.biz_a = EntitasBisnis.objects.create(nama='Bisnis A', tipe_entitas=tipe)
        self.biz_b = EntitasBisnis.objects.create(nama='Bisnis B', tipe_entitas=tipe)

    def test_create_and_str(self):
        from apps.inventory.models import Warehouse
        wh = Warehouse.objects.create(entitas_bisnis=self.biz_a, kode='GD01', nama='Gudang Utama')
        self.assertTrue(wh.is_active)
        self.assertEqual(str(wh), 'GD01 — Gudang Utama')

    def test_kode_unique_per_business_only(self):
        from django.db import IntegrityError
        from apps.inventory.models import Warehouse
        Warehouse.objects.create(entitas_bisnis=self.biz_a, kode='GD01', nama='A-Utama')
        # kode sama di bisnis berbeda: boleh
        Warehouse.objects.create(entitas_bisnis=self.biz_b, kode='GD01', nama='B-Utama')
        # kode sama di bisnis sama: ditolak
        with self.assertRaises(IntegrityError):
            Warehouse.objects.create(entitas_bisnis=self.biz_a, kode='GD01', nama='A-Dup')
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.inventory.tests.WarehouseModelTest --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `ImportError: cannot import name 'Warehouse'`.

- [ ] **Step 3: Implementasi model `Warehouse`**

Di `apps/inventory/models.py`, tambahkan sebelum `class StockMovement` (pastikan `EntitasBisnis` di-referensikan via string app-label agar tak menambah import siklik):

```python
class Warehouse(models.Model):
    """Physical stock location, scoped to a business/tenant (EntitasBisnis lv1).

    Orthogonal to the accounting EB hierarchy: a warehouse belongs to exactly
    one business but may be used by any of that business's branches (lv2/lv3).
    """
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='warehouses', verbose_name='Bisnis (Entitas Bisnis Lv1)',
    )
    kode = models.CharField(max_length=30, verbose_name='Kode Gudang')
    nama = models.CharField(max_length=255, verbose_name='Nama Gudang')
    alamat = models.TextField(blank=True, null=True, verbose_name='Alamat')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Gudang'
        verbose_name_plural = 'Gudang'
        unique_together = (('entitas_bisnis', 'kode'),)
        ordering = ['entitas_bisnis', 'kode']

    def __str__(self) -> str:
        return f'{self.kode} — {self.nama}'
```

- [ ] **Step 4: Buat migrasi**

Run: `python manage.py makemigrations inventory`
Expected: membuat migrasi baru `..._warehouse.py` dengan `CreateModel Warehouse`.

- [ ] **Step 5: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.WarehouseModelTest --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Register admin**

Di `apps/inventory/admin.py` tambahkan:

```python
from .models import Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'entitas_bisnis', 'is_active', 'created_at')
    list_filter = ('entitas_bisnis', 'is_active')
    search_fields = ('kode', 'nama')
    autocomplete_fields = ('entitas_bisnis',)
```

Catatan: bila `EntitasBisnisAdmin` belum punya `search_fields`, `autocomplete_fields` akan error saat load admin — bila demikian, ganti `autocomplete_fields = ('entitas_bisnis',)` menjadi `raw_id_fields = ('entitas_bisnis',)`. Cek dengan menjalankan `python manage.py check`.

- [ ] **Step 7: Verifikasi admin ter-load**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 8: Commit**

```bash
git add apps/inventory/models.py apps/inventory/admin.py apps/inventory/migrations/ apps/inventory/tests.py
git commit -m "feat(inventory): Warehouse master model (tenant-scoped) + admin"
```

---

### Task 2: Field `StockMovement.warehouse` + index + admin display

**Files:**
- Modify: `apps/inventory/models.py` (tambah field `warehouse` + index di `StockMovement`)
- Modify: `apps/inventory/admin.py` (tambah `warehouse` ke StockMovement admin bila ada)
- Test: `apps/inventory/tests.py` (append)
- Migration: via makemigrations

**Interfaces:**
- Consumes: `apps.inventory.models.Warehouse` (Task 1).
- Produces: `StockMovement.warehouse` (nullable FK ke `Warehouse`, PROTECT).

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/inventory/tests.py`:

```python
class StockMovementWarehouseFieldTest(DjangoTestCase):
    def test_warehouse_nullable_and_assignable(self):
        from decimal import Decimal
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        from apps.purchase.models import ItemMasterPurchase
        from apps.inventory.models import Warehouse, StockMovement
        tipe = TipeEntitas.objects.create(nama='T-SMWH')
        biz = EntitasBisnis.objects.create(nama='Biz-SMWH', tipe_entitas=tipe)
        item = ItemMasterPurchase.objects.create(item_id='ITM-SMWH', nama_item='X', tipe_item='RM')
        wh = Warehouse.objects.create(entitas_bisnis=biz, kode='GD1', nama='G1')
        # null diperbolehkan
        m_null = StockMovement.objects.create(
            item=item, entitas_bisnis=biz, tanggal='2026-07-16',
            movement_type='purchase_in', qty=Decimal('5'), unit_cost=Decimal('10'),
            remaining_qty=Decimal('5'))
        self.assertIsNone(m_null.warehouse)
        # bisa di-set
        m_wh = StockMovement.objects.create(
            item=item, entitas_bisnis=biz, warehouse=wh, tanggal='2026-07-16',
            movement_type='purchase_in', qty=Decimal('5'), unit_cost=Decimal('10'),
            remaining_qty=Decimal('5'))
        self.assertEqual(m_wh.warehouse_id, wh.pk)
```

Catatan: sesuaikan kolom `ItemMasterPurchase.objects.create(...)` bila field wajibnya berbeda — cek definisi di `apps/purchase/models.py:466` dan pola pembuatan item di `apps/inventory/tests.py` yang sudah ada (Fase 2) lalu tiru persis argumennya.

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.inventory.tests.StockMovementWarehouseFieldTest --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `TypeError`/`FieldError` untuk `warehouse`.

- [ ] **Step 3: Tambah field + index**

Di `apps/inventory/models.py`, dalam `StockMovement`, tambahkan field setelah `entitas_bisnis_lv3` (agar dekat dimensi lain):

```python
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements',
        verbose_name='Gudang',
    )
```

Dan tambahkan satu index di `StockMovement.Meta.indexes`:

```python
            models.Index(fields=['item', 'warehouse', 'remaining_qty'],
                         name='idx_sm_item_wh_remaining'),
```

- [ ] **Step 4: Buat migrasi**

Run: `python manage.py makemigrations inventory`
Expected: migrasi baru `AddField warehouse` + `AddIndex idx_sm_item_wh_remaining`.

- [ ] **Step 5: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.StockMovementWarehouseFieldTest --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Tambah `warehouse` ke StockMovement admin (bila ada)**

Cari `StockMovement` di `apps/inventory/admin.py` (admin read-only dari Fase 2). Tambahkan `'warehouse'` ke `list_display` dan `list_filter`. Bila `list_display` didefinisikan sebagai tuple, sisipkan setelah `entitas_bisnis`. Jalankan `python manage.py check` → `no issues`.

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/models.py apps/inventory/admin.py apps/inventory/migrations/ apps/inventory/tests.py
git commit -m "feat(inventory): StockMovement.warehouse nullable FK + index + admin"
```

---

### Task 3: Ledger — parameter `warehouse`, filter, dan validasi tenant

**Files:**
- Modify: `apps/inventory/ledger.py` (`_candidate_tiers`, `get_available_stock`, `record_inflow`, `consume_stock`, `_consume_stock_bulk`, helper validasi)
- Test: `apps/inventory/tests.py` (append)

**Interfaces:**
- Consumes: `StockMovement.warehouse` (Task 2).
- Produces (tanda tangan final):
  - `record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal, movement_type, source=None, *, warehouse=None, legacy_fifo_batch=None, legacy_inventory_record=None)`
  - `consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type, source=None, metode='fifo', *, warehouse=None)`
  - `get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None)`
  - `_candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse=None)`
  - `_validate_warehouse_tenant(warehouse, eb_lv1)` (raise `ValueError` bila lintas-bisnis).

- [ ] **Step 1: Tulis test yang gagal — kunci gudang, NULL exact-match, tenant, regresi**

Append ke `apps/inventory/tests.py`. (Bangun item & EB memakai pola factory yang sudah ada di file ini dari Fase 2; contoh di bawah memakai konstruktor langsung — samakan argumennya dengan test Fase 2 yang lulus.)

```python
class LedgerWarehouseTest(DjangoTestCase):
    def setUp(self):
        from decimal import Decimal
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        from apps.purchase.models import ItemMasterPurchase
        from apps.inventory.models import Warehouse
        self.D = Decimal
        tipe = TipeEntitas.objects.create(nama='T-LWH')
        self.biz = EntitasBisnis.objects.create(nama='Biz-LWH', tipe_entitas=tipe)
        self.biz_other = EntitasBisnis.objects.create(nama='Biz-Other-LWH', tipe_entitas=tipe)
        self.item = ItemMasterPurchase.objects.create(item_id='ITM-LWH', nama_item='X', tipe_item='RM')
        self.wh_a = Warehouse.objects.create(entitas_bisnis=self.biz, kode='A', nama='Gudang A')
        self.wh_b = Warehouse.objects.create(entitas_bisnis=self.biz, kode='B', nama='Gudang B')
        self.wh_foreign = Warehouse.objects.create(entitas_bisnis=self.biz_other, kode='X', nama='Asing')

    def _inflow(self, qty, cost, wh, tanggal='2026-07-16'):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.biz, None, None, self.D(qty), self.D(cost),
                             tanggal, 'purchase_in', warehouse=wh)

    def test_consume_locked_to_warehouse_ignores_other(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '100', self.wh_a)
        self._inflow('10', '999', self.wh_b)
        res = consume_stock(self.item, self.biz, None, None, self.D('6'),
                            '2026-07-17', 'sale_out', warehouse=self.wh_a)
        # hanya layer A (cost 100) terpakai
        self.assertEqual(res.total_cost, self.D('600'))

    def test_insufficient_in_warehouse_even_if_other_has_stock(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._inflow('5', '100', self.wh_a)
        self._inflow('100', '100', self.wh_b)
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.biz, None, None, self.D('20'),
                          '2026-07-17', 'sale_out', warehouse=self.wh_a)

    def test_warehouse_given_does_not_touch_null_layers(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._inflow('10', '100', None)   # layer NULL
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.biz, None, None, self.D('3'),
                          '2026-07-17', 'sale_out', warehouse=self.wh_a)

    def test_warehouse_none_is_fase2_behavior_consumes_any(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('4', '100', self.wh_a)
        self._inflow('4', '100', None)
        # tanpa warehouse → boleh melintasi gudang & NULL (perilaku Fase 2)
        res = consume_stock(self.item, self.biz, None, None, self.D('8'),
                            '2026-07-17', 'sale_out')
        self.assertEqual(res.total_cost, self.D('800'))

    def test_tenant_validation_rejects_foreign_warehouse(self):
        from apps.inventory.ledger import record_inflow
        with self.assertRaises(ValueError):
            record_inflow(self.item, self.biz, None, None, self.D('1'), self.D('1'),
                          '2026-07-16', 'purchase_in', warehouse=self.wh_foreign)

    def test_available_stock_per_warehouse(self):
        from apps.inventory.ledger import get_available_stock
        self._inflow('10', '100', self.wh_a)
        self._inflow('3', '100', self.wh_b)
        self.assertEqual(get_available_stock(self.item, self.biz, warehouse=self.wh_a), self.D('10'))
        self.assertEqual(get_available_stock(self.item, self.biz, warehouse=self.wh_b), self.D('3'))
        self.assertEqual(get_available_stock(self.item, self.biz), self.D('13'))
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.inventory.tests.LedgerWarehouseTest --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `record_inflow() got an unexpected keyword argument 'warehouse'`.

- [ ] **Step 3: Tambah helper validasi tenant**

Di `apps/inventory/ledger.py`, setelah `class InsufficientStockError`, tambahkan:

```python
def _validate_warehouse_tenant(warehouse, eb_lv1):
    """Fail-loud jika gudang bukan milik bisnis (lv1) movement ini."""
    if warehouse is not None and warehouse.entitas_bisnis_id != eb_lv1.pk:
        raise ValueError(
            f'Gudang {warehouse.kode} milik bisnis lain, '
            f'bukan {eb_lv1} — stok tak boleh lintas bisnis.'
        )
```

- [ ] **Step 4: Filter warehouse di `_candidate_tiers`**

Ubah tanda tangan dan `base` queryset:

```python
def _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse=None):
    base = StockMovement.objects.filter(item=item, remaining_qty__gt=0)
    if warehouse is not None:
        base = base.filter(warehouse=warehouse)   # exact-match; layer NULL tak ikut
    tiers = []
    # ... sisanya TIDAK berubah ...
```

(Sisa body `_candidate_tiers` tetap persis seperti sekarang.)

- [ ] **Step 5: Teruskan `warehouse` di `get_available_stock`**

```python
def get_available_stock(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None):
    from django.db.models import Sum
    total = Decimal('0')
    for _level, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
        agg = qs.aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0')
        total += agg
    return total
```

- [ ] **Step 6: `record_inflow` — param + validasi + simpan**

Ubah tanda tangan menjadi keyword-only `warehouse`:

```python
def record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal,
                  movement_type, source=None, *, warehouse=None,
                  legacy_fifo_batch=None, legacy_inventory_record=None):
    _validate_warehouse_tenant(warehouse, eb_lv1)
    ct = obj_id = None
    if source is not None:
        ct = ContentType.objects.get_for_model(type(source))
        obj_id = source.pk
    return StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        warehouse=warehouse,
        tanggal=tanggal, movement_type=movement_type,
        qty=qty, unit_cost=unit_cost, remaining_qty=qty,
        source_content_type=ct, source_object_id=obj_id,
        legacy_fifo_batch=legacy_fifo_batch,
        legacy_inventory_record=legacy_inventory_record,
    )
```

- [ ] **Step 7: `consume_stock` — param + validasi + teruskan filter + simpan outflow**

Ubah tanda tangan menjadi `..., metode='fifo', *, warehouse=None`. Di awal body tambahkan `_validate_warehouse_tenant(warehouse, eb_lv1)`. Teruskan `warehouse` ke pemanggilan `_candidate_tiers(...)` di loop non-bulk **dan** ke `_consume_stock_bulk(...)`. Set `warehouse=warehouse` pada `StockMovement.objects.create(...)` untuk baris outflow. Konkретnya:

```python
def consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
                  source=None, metode='fifo', *, warehouse=None):
    _validate_warehouse_tenant(warehouse, eb_lv1)
    req_level = requested_level(eb_lv2, eb_lv3)
    req_rank = _LEVEL_RANK[req_level]

    is_bulk = item.tipe_item in ('RMB', 'FGB', 'ITMB')
    if is_bulk:
        return _consume_stock_bulk(
            item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type,
            source, req_level, req_rank, warehouse=warehouse,
        )
    # ... loop tak berubah kecuali baris berikut:
    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
        ...
    # saat membuat out_movement:
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        warehouse=warehouse,
        tanggal=tanggal, movement_type=movement_type,
        qty=-qty, unit_cost=avg_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
```

- [ ] **Step 8: `_consume_stock_bulk` — param + teruskan filter + simpan**

Ubah tanda tangan menambahkan keyword-only `warehouse=None`; teruskan ke `_candidate_tiers`; set `warehouse=warehouse` pada `out_movement`:

```python
def _consume_stock_bulk(item, eb_lv1, eb_lv2, eb_lv3, value, tanggal,
                        movement_type, source, req_level, req_rank, *, warehouse=None):
    ...
    for level, eb_name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
        ...
    out_movement = StockMovement.objects.create(
        item=item, entitas_bisnis=eb_lv1,
        entitas_bisnis_lv2=eb_lv2, entitas_bisnis_lv3=eb_lv3,
        warehouse=warehouse,
        tanggal=tanggal, movement_type=movement_type,
        qty=Decimal('0'), unit_cost=total_cost, remaining_qty=Decimal('0'),
        source_content_type=ct, source_object_id=obj_id,
    )
```

- [ ] **Step 9: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.LedgerWarehouseTest --settings=naveda_integra.settings.test -v 2`
Expected: PASS (7 test).

- [ ] **Step 10: Regresi ledger penuh + Postgres parity**

Run: `python manage.py test apps.inventory --settings=naveda_integra.settings.test -v 2`
Expected: semua test inventory (termasuk karakterisasi FIFO Fase 2) PASS — bukti `warehouse=None` tak mengubah perilaku lama.
Lalu ulangi test `LedgerWarehouseTest` pada Postgres lokal (settings dev Postgres) untuk parity.

- [ ] **Step 11: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): warehouse-aware ledger (lock-on-consume + tenant guard)"
```

---

### Task 4: Wiring Pembelian (`PurchaseItem.warehouse`)

**Files:**
- Modify: `apps/purchase/models.py` (tambah `PurchaseItem.warehouse`)
- Modify: `apps/purchase/views.py:1418` & `:1461` (set `warehouse_id` saat create `PurchaseItem`)
- Modify: `apps/purchase/services.py:186` (`create_stock_movements` teruskan `warehouse=pi.warehouse`)
- Modify: `apps/purchase/views.py:535`/`:613` render context (`warehouses` per bisnis) + `templates/purchase/purchase_form.html` (kolom gudang + toggle)
- Test: `apps/purchase/tests.py` (append)
- Migration: via makemigrations

**Interfaces:**
- Consumes: `Warehouse` (Task 1), `record_inflow(..., warehouse=...)` (Task 3).
- Produces: `PurchaseItem.warehouse` (nullable FK).

- [ ] **Step 1: Tulis test service yang gagal**

Append ke `apps/purchase/tests.py` sebuah test yang: membuat `PurchaseHeader`+`PurchaseEntitasBisnis`+`PurchaseItem` (item `RM`, `sub_transaction_type.direction='inflow'`) dengan `warehouse=wh` (wh milik EB yang sama), memanggil `create_stock_movements(header)`, lalu memastikan `StockMovement` inflow yang dibuat punya `warehouse_id == wh.pk`. Tiru pola setup dari test `create_stock_movements` Fase 2 yang sudah ada di file ini (cari `create_stock_movements` di `apps/purchase/tests.py`).

```python
def test_purchase_stock_movement_carries_warehouse(self):
    from apps.inventory.models import Warehouse, StockMovement
    from apps.purchase.services import create_stock_movements
    wh = Warehouse.objects.create(entitas_bisnis=self.eb, kode='PGD', nama='Gudang Beli')
    self.pi.warehouse = wh
    self.pi.save(update_fields=['warehouse'])
    create_stock_movements(self.ph)
    mv = StockMovement.objects.get(source_object_id=self.pi.pk,
                                   source_content_type__model='purchaseitem')
    self.assertEqual(mv.warehouse_id, wh.pk)
```

(Sesuaikan `self.eb/self.pi/self.ph` dengan nama fixture pada TestCase yang kamu tempati; bila belum ada TestCase yang menyiapkan `create_stock_movements`, buat setUp meniru test Fase 2 terdekat.)

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.purchase.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `PurchaseItem` tak punya atribut `warehouse`.

- [ ] **Step 3: Tambah field `PurchaseItem.warehouse`**

Di `apps/purchase/models.py` dalam `class PurchaseItem`:

```python
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='purchase_items',
        verbose_name='Gudang',
    )
```

Run: `python manage.py makemigrations purchase`

- [ ] **Step 4: Teruskan warehouse di `create_stock_movements`**

Di `apps/purchase/services.py`, panggilan `record_inflow(...)` (baris ~186) tambahkan argumen keyword:

```python
            mv = record_inflow(
                pi.item, eb_group.entitas_bisnis,
                eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                qty, unit_cost, purchase_header.tanggal, 'purchase_in',
                source=pi, warehouse=pi.warehouse,
                legacy_fifo_batch=batch, legacy_inventory_record=rec,
            )
```

- [ ] **Step 5: Jalankan test service, pastikan lulus**

Run: `python manage.py test apps.purchase.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Persist `warehouse_id` dari JSON di view**

Di `apps/purchase/views.py`, pada kedua blok `PurchaseItem.objects.create(...)` (baris ~1418 dan ~1461), tambahkan:

```python
                        warehouse_id=(item_data.get('warehouse_id') or None),
```

- [ ] **Step 7: Validasi tenant di view (server-side guard)**

Sebelum `PurchaseItem.objects.create`, bila `item_data.get('warehouse_id')` terisi, pastikan gudang milik bisnis eb_group (lv1). Tambahkan sekali di dekat resolusi eb_group:

```python
from apps.inventory.models import Warehouse
# ... di dalam loop pembuatan item, saat warehouse_id ada:
wh_id = item_data.get('warehouse_id') or None
if wh_id and not Warehouse.objects.filter(
        pk=wh_id, entitas_bisnis_id=eb_resolved['lv1_id']).exists():
    raise ValueError('Gudang tidak valid untuk bisnis ini.')
```

(Gunakan variabel lv1 id yang tersedia di scope tersebut — cek nama pada blok create eb_group setempat, mis. `eb_resolved['lv1_id']` atau `eb_group.entitas_bisnis_id`.)

- [ ] **Step 8: Sediakan daftar gudang di context render form**

Di `apps/purchase/views.py` fungsi `purchase_create` (dan handler edit yang me-render `purchase_form.html`), tambahkan ke context:

```python
from apps.inventory.models import Warehouse
warehouses = list(
    Warehouse.objects.filter(is_active=True)
    .values('id', 'kode', 'nama', 'entitas_bisnis_id')
)
# ... 'warehouses_json': safe_json(warehouses),
```

(Gunakan util `safe_json` yang sudah dipakai view purchase; bila belum diimpor, impor dari `naveda_integra.json_utils`.)

- [ ] **Step 9: Kolom gudang + toggle di template**

Di `templates/purchase/purchase_form.html`, pada grid baris item (tempat kolom item/qty/harga dirender oleh JS), tambahkan:
- Satu `<select class="ni-input wh-select">` per baris, di-populate dari `warehouses_json` **difilter** `entitas_bisnis_id === <lv1 grup baris>`; nilai `<option value="">— (opsional)</option>` sebagai default kosong. Simpan pilihan ke properti `warehouse_id` pada objek baris di state JS yang dikirim sebagai `item_data`.
- Satu toggle per grup EB: checkbox/tombol "Gudang seragam". Saat aktif, tampilkan satu `<select>` grup; `onchange`-nya menyalin nilai ke `warehouse_id` semua baris grup dan menonaktifkan select per-baris. Saat non-aktif, select per-baris aktif kembali.

Snippet JS inti (slot ke fungsi render baris + handler grup yang sudah ada — cari fungsi yang membangun objek `item_data`):

```javascript
// populate select per baris
function warehouseOptions(lv1Id, selected) {
  const opts = ['<option value="">— (opsional)</option>'];
  WAREHOUSES.filter(w => String(w.entitas_bisnis_id) === String(lv1Id))
    .forEach(w => {
      const sel = String(w.id) === String(selected) ? ' selected' : '';
      opts.push(`<option value="${w.id}"${sel}>${w.kode} — ${w.nama}</option>`);
    });
  return opts.join('');
}
// toggle seragam: copy nilai ke semua baris grup
function applyUniformWarehouse(groupEl, whId) {
  groupEl.querySelectorAll('.wh-select').forEach(sel => {
    sel.value = whId; sel.disabled = !!whId;
    sel.dispatchEvent(new Event('change'));
  });
}
```

`WAREHOUSES` di-inisialisasi dari `{{ warehouses_json|safe }}`. Pastikan saat mengumpulkan `item_data` untuk POST, sertakan `warehouse_id: row.warehouse_id || ''`.

- [ ] **Step 10: Uji manual alur form (verify)**

Jalankan app, buat pembelian item RM dengan gudang dipilih, simpan, buka Django admin `StockMovement` → baris inflow membawa gudang tsb. Ulangi dengan toggle "seragam". Gunakan skill `verify`/`run` untuk menggerakkan alur nyata.

- [ ] **Step 11: Commit**

```bash
git add apps/purchase/ templates/purchase/purchase_form.html
git commit -m "feat(purchase): per-line warehouse selection wired to stock ledger inflow"
```

---

### Task 5: Wiring Penjualan (`SalesItem.warehouse`)

**Files:**
- Modify: `apps/sales/models.py` (tambah `SalesItem.warehouse`)
- Modify: `apps/sales/views.py:1041` (set `warehouse_id`)
- Modify: `apps/sales/services.py:244` & `:250` (`process_sales_fifo` teruskan `warehouse=si.warehouse`)
- Modify: `apps/sales/views.py` render context + `templates/sales/sales_form.html` (kolom gudang + toggle)
- Test: `apps/sales/tests.py` (append)
- Migration: via makemigrations

**Interfaces:**
- Consumes: `Warehouse` (Task 1), `consume_stock(..., warehouse=...)` (Task 3).
- Produces: `SalesItem.warehouse` (nullable FK).

- [ ] **Step 1: Tulis test yang gagal (kunci gudang saat jual)**

Append ke `apps/sales/tests.py`. Skenario: dua inflow item sama, EB sama, gudang A & B; buat penjualan `SalesItem` dengan `warehouse=A`; jalankan `process_sales_fifo(header)`; pastikan `cogs_amount` hanya dari layer A, dan `StockMovement` outflow membawa `warehouse_id == A`. Tiru setup FIFO dari test Fase 2 di file ini.

```python
def test_sale_consumes_only_selected_warehouse(self):
    from decimal import Decimal
    from apps.inventory.models import Warehouse, StockMovement
    from apps.inventory.ledger import record_inflow
    from apps.sales.services import process_sales_fifo
    wh_a = Warehouse.objects.create(entitas_bisnis=self.eb, kode='SA', nama='SGudang A')
    wh_b = Warehouse.objects.create(entitas_bisnis=self.eb, kode='SB', nama='SGudang B')
    record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('100'),
                  '2026-07-16', 'purchase_in', warehouse=wh_a)
    record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('999'),
                  '2026-07-16', 'purchase_in', warehouse=wh_b)
    self.si.warehouse = wh_a
    self.si.quantity = Decimal('6')
    self.si.save()
    process_sales_fifo(self.sales_header)
    self.si.refresh_from_db()
    self.assertEqual(self.si.cogs_amount, Decimal('600'))
    out = StockMovement.objects.get(source_object_id=self.si.pk,
                                    source_content_type__model='salesitem')
    self.assertEqual(out.warehouse_id, wh_a.pk)
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.sales.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — `SalesItem` tak punya `warehouse`.

- [ ] **Step 3: Tambah field `SalesItem.warehouse`**

Di `apps/sales/models.py` dalam `class SalesItem`:

```python
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='sales_items',
        verbose_name='Gudang',
    )
```

Run: `python manage.py makemigrations sales`

- [ ] **Step 4: Teruskan warehouse di `process_sales_fifo`**

Di `apps/sales/services.py`, kedua panggilan `consume_stock(...)` (bulk baris ~244, non-bulk ~250) tambahkan `warehouse=si.warehouse`:

```python
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        amount, sales_header.tanggal, 'sale_out',
                        source=si, warehouse=si.warehouse)
```

(dan identik pada cabang non-bulk dengan `si.quantity`).

- [ ] **Step 5: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.sales.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Persist `warehouse_id` dari JSON**

Di `apps/sales/views.py` blok `SalesItem.objects.create(...)` (baris ~1041) tambahkan:

```python
                        warehouse_id=(item_data.get('warehouse_id') or None),
```

Tambahkan juga guard tenant seperti Task 4 Step 7 (gunakan lv1 id eb_group setempat).

- [ ] **Step 7: Context + template (kolom gudang + toggle)**

Sama seperti Task 4 Step 8–9, terapkan pada `apps/sales/views.py` (fungsi `sales_create` dan handler yang me-render `sales/sales_form.html`) dan `templates/sales/sales_form.html`. Gunakan snippet JS `warehouseOptions`/`applyUniformWarehouse` yang sama; pastikan `warehouse_id` disertakan saat menyusun `item_data` POST.

- [ ] **Step 8: Uji manual (verify)**

Buat penjualan dengan gudang dipilih; pastikan konsumsi FIFO hanya dari gudang itu; coba pilih gudang yang stoknya kurang padahal gudang lain cukup → error/ pesan stok tak cukup muncul.

- [ ] **Step 9: Commit**

```bash
git add apps/sales/ templates/sales/sales_form.html
git commit -m "feat(sales): per-line warehouse selection wired to ledger consumption (locked)"
```

---

### Task 6: Wiring Manufaktur (`ProductionOrder.warehouse_rm`, `warehouse_fg`)

**Files:**
- Modify: `apps/manufacturing/models.py` (`ProductionOrder`: dua field)
- Modify: `apps/manufacturing/forms.py:53` (`ProductionOrderForm.Meta.fields` + widgets)
- Modify: `apps/manufacturing/services.py:345` (RM: `warehouse=production_order.warehouse_rm`), `:414` & `:661` (FG: `warehouse=production_order.warehouse_fg`)
- Test: `apps/manufacturing/tests.py` (append)
- Migration: via makemigrations

**Interfaces:**
- Consumes: `Warehouse` (Task 1), `consume_stock`/`record_inflow` warehouse (Task 3).
- Produces: `ProductionOrder.warehouse_rm`, `ProductionOrder.warehouse_fg`.

- [ ] **Step 1: Tulis test yang gagal**

Append ke `apps/manufacturing/tests.py`: buat production order dengan `warehouse_rm=A`, `warehouse_fg=B` (keduanya milik EB order); sediakan stok RM di gudang A via `record_inflow(..., warehouse=A)`; jalankan proses produksi; pastikan (a) RM outflow `StockMovement` ber-`warehouse=A`, (b) FG inflow `StockMovement` ber-`warehouse=B`. Tiru setup produksi dari test Fase 2/Manufaktur yang sudah ada.

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.manufacturing.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — field tak ada.

- [ ] **Step 3: Tambah dua field**

Di `apps/manufacturing/models.py` dalam `class ProductionOrder`:

```python
    warehouse_rm = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='production_orders_rm',
        verbose_name='Gudang Bahan Baku',
    )
    warehouse_fg = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='production_orders_fg',
        verbose_name='Gudang Hasil Produksi',
    )
```

Run: `python manage.py makemigrations manufacturing`

- [ ] **Step 4: Teruskan warehouse di service**

Di `apps/manufacturing/services.py`:
- RM (baris ~345): tambahkan `warehouse=production_order.warehouse_rm` pada `consume_stock(...)`.
- FG completed (baris ~414): tambahkan `warehouse=production_order.warehouse_fg` pada `record_inflow(...)`.
- FG jalur WIP-approval (baris ~661): tambahkan `warehouse=production_order.warehouse_fg` pada `record_inflow(...)`.

- [ ] **Step 5: Tambah field ke form**

Di `apps/manufacturing/forms.py`, `ProductionOrderForm.Meta.fields` tambahkan `'warehouse_rm', 'warehouse_fg'` (mis. setelah `'entitas_bisnis_lv3'`), dan widget:

```python
            'warehouse_rm': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse_fg': forms.Select(attrs={'class': 'ni-input'}),
```

Opsional (peningkatan): di `__init__` form, batasi queryset kedua field ke gudang milik bisnis terpilih bila `entitas_bisnis` tersedia; jika tidak, biarkan default (semua aktif) — guard tenant di ledger tetap menangkap kesalahan.

- [ ] **Step 6: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.manufacturing.tests -k warehouse --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 7: Regresi manufaktur + Postgres parity**

Run: `python manage.py test apps.manufacturing --settings=naveda_integra.settings.test -v 2`
Expected: semua PASS (termasuk reversal & bulk FG Fase 2). Ulangi test warehouse pada Postgres.

- [ ] **Step 8: Commit**

```bash
git add apps/manufacturing/
git commit -m "feat(manufacturing): RM-source + FG-dest warehouse on production order"
```

---

### Task 7: Wiring Saldo Awal (mirror ledger + gudang per baris)

**Files:**
- Modify: `apps/jurnal/views.py:1372-1416` (blok persediaan: tambah `record_inflow` mirror + `warehouse` per detail row)
- Modify: `templates/jurnal/saldo_awal.html` (kolom gudang pada detail persediaan)
- Test: `apps/jurnal/tests.py` (buat bila belum ada) atau `apps/inventory/tests.py`
- Migration: tidak ada (tak ada model baru)

**Interfaces:**
- Consumes: `Warehouse` (Task 1), `record_inflow(..., warehouse=...)` (Task 3).
- Produces: Saldo Awal persediaan kini menulis `StockMovement` (`movement_type='saldo_awal'`) tertaut ke `FIFOBatch`+`InventoryRecord` yang sama, membawa gudang.

- [ ] **Step 1: Tulis test yang gagal**

Buat test yang memanggil helper ekstraksi (lihat Step 3) atau mem-POST ke view `jurnal:saldo_awal` dengan satu baris akun persediaan berisi `detail_rows=[{item_id, qty, unit_price, warehouse_id}]`, lalu memastikan: (a) `FIFOBatch` & `InventoryRecord` dibuat (perilaku lama), (b) **`StockMovement` `saldo_awal` dibuat** dan tertaut `legacy_fifo_batch`/`legacy_inventory_record`, (c) `StockMovement.warehouse_id == warehouse_id`. Karena view berbasis request, uji lewat Django test `Client` dengan user login (ikuti pola test view yang sudah ada di repo; perhatikan django-axes — gunakan fixture login yang dipakai test lain).

Bila pengujian via Client terlalu berat, refaktor blok persediaan ke fungsi murni di Step 3 dan uji fungsi itu langsung (lebih disukai — lihat Step 3).

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.jurnal.tests -k saldo_awal_stock --settings=naveda_integra.settings.test -v 2`
Expected: FAIL — tak ada `StockMovement` dibuat / `warehouse` tak tersimpan.

- [ ] **Step 3: Ekstrak blok persediaan ke fungsi murni + tambah mirror**

Di `apps/jurnal/views.py`, ganti blok inline persediaan (baris ~1372–1416) dengan pemanggilan fungsi baru `create_saldo_awal_persediaan(persediaan_rows, eb_id, tanggal)` yang ditaruh dekat view (atau di `apps/jurnal/services.py` bila ada). Fungsi meniru logika lama **plus** `record_inflow`:

```python
def create_saldo_awal_persediaan(persediaan_rows, eb_id, tanggal):
    from decimal import Decimal
    from apps.purchase.models import FIFOBatch, ItemMasterPurchase
    from apps.inventory.models import InventoryRecord, Warehouse
    from apps.inventory.ledger import record_inflow
    from apps.entitas_bisnis.models import EntitasBisnis

    all_item_ids = {
        int(d['item_id'])
        for r in persediaan_rows for d in r.get('detail_rows', [])
        if str(d.get('item_id', '')).isdigit()
    }
    items_map = {i.pk: i for i in ItemMasterPurchase.objects.filter(pk__in=all_item_ids)}
    eb = EntitasBisnis.objects.get(pk=eb_id)
    for row in persediaan_rows:
        for d in row.get('detail_rows', []):
            try:
                item_pk = int(str(d.get('item_id', '')))
                qty = Decimal(str(d.get('qty') or 0))
                unit_price = Decimal(str(d.get('unit_price') or 0))
            except (ValueError, TypeError):
                continue
            if qty <= 0 or unit_price < 0:
                continue
            item = items_map.get(item_pk)
            if not item:
                continue
            wh = None
            wh_id = d.get('warehouse_id') or None
            if wh_id:
                wh = Warehouse.objects.filter(pk=wh_id, entitas_bisnis_id=eb_id).first()
                if wh is None:
                    raise ValueError('Gudang tidak valid untuk bisnis ini.')
            rec = InventoryRecord.objects.create(
                item=item, purchase_item=None, entitas_bisnis_id=eb_id,
                quantity=qty, unit_price=unit_price, tanggal=tanggal)
            batch = FIFOBatch.objects.create(
                purchase_item=None, item=item, tanggal=tanggal,
                quantity_in=qty, unit_price=unit_price, remaining_qty=qty)
            record_inflow(
                item, eb, None, None, qty, unit_price, tanggal, 'saldo_awal',
                warehouse=wh, legacy_fifo_batch=batch, legacy_inventory_record=rec)
```

Lalu di view, ganti blok lama menjadi:

```python
            if persediaan_rows:
                create_saldo_awal_persediaan(persediaan_rows, eb_id, tanggal)
```

Catatan: konvensi bulk (qty=1) TIDAK diterapkan di sini — Saldo Awal mempertahankan qty/unit_price apa adanya agar `StockMovement` konsisten dengan `FIFOBatch`/`InventoryRecord` yang ditautkannya (konsumsi bulk membaca `remaining_qty * unit_cost` = nilai total yang benar).

- [ ] **Step 4: Kolom gudang di template Saldo Awal**

Di `templates/jurnal/saldo_awal.html`, pada grid `detail_rows` tipe `persediaan`, tambahkan `<select class="ni-input">` gudang per baris detail, di-populate dari daftar gudang bisnis terpilih (`entitas_bisnis` header). Sertakan `warehouse_id` pada objek `detail_rows` yang di-serialize ke `rows_data`. Sediakan daftar gudang lewat context view `saldo_awal` (tambahkan `Warehouse.objects.filter(is_active=True).values(...)` seperti Task 4 Step 8). Gudang difilter ke `entitas_bisnis` yang dipilih di form.

- [ ] **Step 5: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.jurnal.tests -k saldo_awal_stock --settings=naveda_integra.settings.test -v 2`
Expected: PASS.

- [ ] **Step 6: Uji manual (verify)**

Input Saldo Awal dengan baris persediaan + gudang; simpan; cek admin `StockMovement` → ada baris `saldo_awal` dengan gudang & tertaut FIFOBatch. Cek `neraca_saldo` tetap seimbang (jurnal tak berubah).

- [ ] **Step 7: Commit**

```bash
git add apps/jurnal/views.py templates/jurnal/saldo_awal.html apps/jurnal/tests.py
git commit -m "feat(jurnal): saldo awal persediaan writes stock ledger + per-row warehouse"
```

---

### Task 8: Regression sweep + reconcile

**Files:**
- Test only (jalankan suite penuh); tak ada perubahan kode kecuali perbaikan regresi yang ditemukan.

- [ ] **Step 1: Jalankan suite penuh**

Run: `python manage.py test --settings=naveda_integra.settings.test -v 1`
Expected: nol kegagalan baru vs baseline pra-plan. Baseline dikenal: ~90 test gagal/error karena isu setup login django-axes + error import pytest yang sudah ada sebelumnya (lihat catatan sesi Fase 2). Bandingkan daftar kegagalan dengan baseline; setiap kegagalan baru wajib diselidiki (skill `systematic-debugging`) dan diperbaiki sebelum lanjut.

- [ ] **Step 2: Postgres parity untuk alur kunci**

Jalankan pada Postgres lokal: `apps.inventory` (ledger), satu test wiring tiap app (purchase/sales/manufacturing/jurnal `-k warehouse`/`-k saldo_awal_stock`).
Expected: PASS identik dengan SQLite.

- [ ] **Step 3: Reconcile ledger vs legacy (spot check)**

Untuk beberapa item uji, verifikasi `get_available_stock(item, eb)` (agregat semua gudang, `warehouse=None`) tetap cocok dengan saldo `FIFOBatch`/`InventoryRecord` seperti sebelum fase ini — bukti bahwa dimensi gudang tidak mengubah total saldo. Gunakan command reconcile Fase 2 bila tersedia (`apps/inventory/management/commands/`), jika ada.

- [ ] **Step 4: Commit (bila ada perbaikan)**

```bash
git add -A
git commit -m "test(inventory): warehouse phase regression sweep — no new failures"
```

---

## Catatan Non-Goal (jangan dikerjakan di plan ini)

- Transfer/mutasi antar gudang → Fase 6. (Konsekuensi: stok terkunci gudang; escape hatch = kosongkan gudang di transaksi.)
- Stock Card / Movement / Valuation per gudang → Fase 8.
- Allow-list pemetaan gudang↔cabang (lv2/lv3) → tak diperlukan (bebas dalam satu bisnis).
- Deprecate/hapus ledger lama `FIFOBatch`/`InventoryRecord` atau menambah `warehouse` padanya → di luar cakupan.
- Costing multi-metode (LIFO/Average) → Fase 3.
