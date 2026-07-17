# Costing Multi-Metode (Fase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Buat `consume_stock` menghormati metode biaya persediaan per-item — FIFO (ada), LIFO, dan moving weighted average — lalu wiring ke Sales & Manufacturing.

**Architecture:** Satu entry point `consume_stock` menormalkan metode item, memilih strategi pengambilan per-tier EB: sequential (FIFO/LIFO, biaya = biaya layer) atau proportional average (biaya = rata-rata tertimbang tier). Isolasi hierarki EB & gudang tak berubah. Item bulk tetap value-based/method-agnostic.

**Tech Stack:** Django 5 (Python 3.13), Decimal, Django TestCase (`python manage.py test`).

**Referensi spec:** `docs/superpowers/specs/2026-07-17-costing-multi-metode-fase3-design.md`

**Semua perintah dijalankan dari direktori `naveda_integra/`** (lokasi `manage.py`).

---

## File Structure

- Modify: `apps/inventory/ledger.py` — `_normalize_method` (baru), `_candidate_tiers` (param `order`), `_take_tier_sequential`/`_take_tier_average` (baru), refactor body `consume_stock`.
- Modify: `apps/inventory/tests.py` — test costing multi-metode.
- Modify: `apps/sales/services.py` — `process_sales_fifo` teruskan `metode`.
- Modify: `apps/manufacturing/services.py` — konsumsi RM teruskan `metode`; `_simulate_fifo_cost` + `get_bom_preview` method-aware.
- Modify: `apps/manufacturing/tests.py` — test simulasi LIFO/average.

Tidak ada model baru, tidak ada migrasi.

---

## Task 1: Normalisasi & validasi metode

**Files:**
- Modify: `apps/inventory/ledger.py`
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan class ini di akhir `apps/inventory/tests.py`:

```python
class NormalizeMethodTests(DjangoTestCase):
    def test_empty_defaults_to_fifo(self):
        from apps.inventory.ledger import _normalize_method
        self.assertEqual(_normalize_method(''), 'fifo')
        self.assertEqual(_normalize_method(None), 'fifo')

    def test_known_methods(self):
        from apps.inventory.ledger import _normalize_method
        self.assertEqual(_normalize_method('fifo'), 'fifo')
        self.assertEqual(_normalize_method('lifo'), 'lifo')
        self.assertEqual(_normalize_method('average'), 'average')
        self.assertEqual(_normalize_method('weighted_moving_average'), 'average')

    def test_case_insensitive_and_trimmed(self):
        from apps.inventory.ledger import _normalize_method
        self.assertEqual(_normalize_method('  LIFO '), 'lifo')

    def test_unknown_raises(self):
        from apps.inventory.ledger import _normalize_method
        with self.assertRaises(ValueError):
            _normalize_method('xyz')
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.inventory.tests.NormalizeMethodTests -v 2`
Expected: FAIL — `cannot import name '_normalize_method'`.

- [ ] **Step 3: Implementasi minimal**

Di `apps/inventory/ledger.py`, ubah import decimal (baris ~7) menjadi:

```python
from decimal import Decimal, ROUND_DOWN
```

Lalu tambahkan setelah baris `OUTFLOW_MOVEMENT_TYPES = {'sale_out', 'production_out'}`:

```python
_METHOD_ALIASES = {
    '': 'fifo',
    'fifo': 'fifo',
    'lifo': 'lifo',
    'average': 'average',
    'weighted_moving_average': 'average',
}


def _normalize_method(metode) -> str:
    """Petakan pilihan metode item ke strategi engine ('fifo'|'lifo'|'average').

    Kosong/None → 'fifo'. String tak dikenal → ValueError (jangan diam-diam FIFO).
    """
    key = (metode or '').strip().lower()
    if key not in _METHOD_ALIASES:
        raise ValueError(f'Metode biaya persediaan tak didukung: {metode!r}')
    return _METHOD_ALIASES[key]
```

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.NormalizeMethodTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): _normalize_method for costing strategy resolution"
```

---

## Task 2: Refactor `consume_stock` ke helper per-tier (FIFO tetap sama)

Refactor murni: perilaku FIFO tak berubah, hanya struktur. Mengunci regresi sebelum menambah LIFO/average.

**Files:**
- Modify: `apps/inventory/ledger.py`

- [ ] **Step 1: Parametrize `_candidate_tiers` dengan `order`**

Ubah signature (baris ~38) menjadi:

```python
def _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse=None, *, order='fifo'):
```

Di dalam body, tepat sebelum membangun `tiers`, tambahkan:

```python
    order_by = ('tanggal', 'created_at') if order == 'fifo' else ('-tanggal', '-created_at')
```

Ganti ketiga `.order_by('tanggal', 'created_at')` di fungsi ini menjadi `.order_by(*order_by)`.

(`get_available_stock` memanggil tanpa `order` → default 'fifo'; urutan tak memengaruhi jumlah, jadi aman.)

- [ ] **Step 2: Tambahkan helper pengambilan sequential**

Tambahkan fungsi baru tepat sebelum `def consume_stock`:

```python
def _take_tier_sequential(layers, remaining):
    """FIFO/LIFO: `layers` sudah terurut. Ambil di biaya asli tiap layer.

    Mengembalikan (picked, cost, taken) dengan
    picked = [(layer, take, alloc_unit_cost), ...].
    Meng-update remaining_qty tiap layer + mirror legacy secara in-place.
    """
    picked = []
    cost = Decimal('0')
    taken = Decimal('0')
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.remaining_qty, remaining)
        if take <= 0:
            continue
        layer.remaining_qty -= take
        layer.save(update_fields=['remaining_qty'])
        _mirror_decrement(layer, take, take * layer.unit_cost)
        picked.append((layer, take, layer.unit_cost))
        cost += take * layer.unit_cost
        taken += take
        remaining -= take
    return picked, cost, taken
```

- [ ] **Step 3: Ganti body non-bulk `consume_stock`**

Di `consume_stock`, setelah blok bulk (`if is_bulk: return _consume_stock_bulk(...)`), ganti seluruh bagian non-bulk (dari `remaining = qty` sampai sebelum pembuatan `out_movement`) dengan:

```python
    method = _normalize_method(metode)
    order = 'lifo' if method == 'lifo' else 'fifo'

    remaining = qty
    total_cost = Decimal('0')
    per_level = {}          # level -> {'eb_name': str, 'qty': Decimal}
    picked = []             # (layer, take, alloc_unit_cost)

    for level, eb_name, qs in _candidate_tiers(
        item, eb_lv1, eb_lv2, eb_lv3, warehouse, order=order,
    ):
        if remaining <= 0:
            break
        layers = list(qs.select_for_update())
        if method == 'average':
            tier_picked, tier_cost, tier_qty = _take_tier_average(layers, remaining)
        else:
            tier_picked, tier_cost, tier_qty = _take_tier_sequential(layers, remaining)
        if tier_qty <= 0:
            continue
        picked.extend(tier_picked)
        total_cost += tier_cost
        remaining -= tier_qty
        slot = per_level.setdefault(level, {'eb_name': eb_name, 'qty': Decimal('0')})
        slot['qty'] += tier_qty

    if remaining > 0:
        raise InsufficientStockError(
            f'Stok tidak mencukupi untuk {item.item_id}. '
            f'Diminta {qty}, tersedia {qty - remaining} dalam hierarki EB.'
        )
```

Lalu ganti pembuatan `allocations` (yang tadinya membaca `(layer, take)`) menjadi membaca triple:

```python
    allocations = [
        StockConsumption.objects.create(
            out_movement=out_movement, in_movement=layer,
            qty=take, unit_cost=alloc_unit_cost,
        )
        for layer, take, alloc_unit_cost in picked
    ]
```

Bagian `out_movement = StockMovement.objects.create(...)` (dengan `avg_cost = total_cost / qty`) dan blok `report`/`return` **tak berubah**.

> Catatan: `_take_tier_average` belum ada — akan dibuat di Task 4. Sampai saat itu, jangan pakai metode 'average'. Test FIFO tetap hijau karena tak menyentuh cabang average.

- [ ] **Step 4: Jalankan test regresi FIFO, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.ConsumeStockNonBulkTests apps.inventory.tests.RecordInflowTests -v 2`
Expected: PASS (semua test FIFO lama hijau — perilaku default tak berubah).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py
git commit -m "refactor(inventory): extract per-tier consumption helper, keep FIFO behavior"
```

---

## Task 3: LIFO

**Files:**
- Modify: `apps/inventory/tests.py`

Kode engine sudah mendukung LIFO (Task 2 mengalihkan `order='lifo'`). Task ini hanya menambah test yang mengunci perilaku.

- [ ] **Step 1: Tulis test yang gagal (seharusnya langsung lulus setelah Task 2 — konfirmasi)**

Tambahkan class di `apps/inventory/tests.py`:

```python
class ConsumeStockLifoTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Beras', tipe_item='RM')

    def _inflow(self, qty, cost, tanggal):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, None, None, Decimal(qty),
                             Decimal(cost), tanggal, 'purchase_in')

    def test_lifo_consumes_newest_first(self):
        from apps.inventory.ledger import consume_stock
        l1 = self._inflow('10', '5', '2026-01-01')   # tua, murah
        l2 = self._inflow('10', '8', '2026-01-02')   # baru, mahal
        # LIFO: 10@8 + 2@5 = 90
        result = consume_stock(self.item, self.eb, None, None, Decimal('12'),
                               '2026-01-03', 'sale_out', metode='lifo')
        self.assertEqual(result.total_cost, Decimal('90'))
        l1.refresh_from_db(); l2.refresh_from_db()
        self.assertEqual(l2.remaining_qty, Decimal('0'))
        self.assertEqual(l1.remaining_qty, Decimal('8'))

    def test_fifo_vs_lifo_differ_on_same_stock(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        self._inflow('10', '8', '2026-01-02')
        fifo = consume_stock(self.item, self.eb, None, None, Decimal('12'),
                             '2026-01-03', 'sale_out', metode='fifo')
        self.assertEqual(fifo.total_cost, Decimal('66'))  # 10@5 + 2@8
```

- [ ] **Step 2: Jalankan test**

Run: `python manage.py test apps.inventory.tests.ConsumeStockLifoTests -v 2`
Expected: PASS (2 tests). Jika gagal, periksa `order` di Task 2 Step 1/3.

- [ ] **Step 3: Commit**

```bash
git add apps/inventory/tests.py
git commit -m "test(inventory): lock LIFO costing behavior"
```

---

## Task 4: Moving weighted average (proporsional)

**Files:**
- Modify: `apps/inventory/ledger.py`
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan class di `apps/inventory/tests.py`:

```python
class ConsumeStockAverageTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Minyak', tipe_item='RM')

    def _inflow(self, qty, cost, tanggal):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, None, None, Decimal(qty),
                             Decimal(cost), tanggal, 'purchase_in')

    def test_average_single_sale_uses_weighted_avg(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '100', '2026-01-01')
        self._inflow('10', '200', '2026-01-02')  # avg = 150
        result = consume_stock(self.item, self.eb, None, None, Decimal('5'),
                               '2026-01-03', 'sale_out', metode='average')
        self.assertEqual(result.total_cost, Decimal('750'))  # 5 × 150

    def test_average_repeated_sale_keeps_avg_stable(self):
        """Invariant proporsional: penjualan kedua memakai avg yang sama (150),
        bukan avg yang menggelembung (166.67 kalau salah pakai urutan FIFO)."""
        from apps.inventory.ledger import consume_stock
        l1 = self._inflow('10', '100', '2026-01-01')
        l2 = self._inflow('10', '200', '2026-01-02')
        consume_stock(self.item, self.eb, None, None, Decimal('5'),
                      '2026-01-03', 'sale_out', metode='average')
        # Setelah jual 5: proporsional → L1=7.5, L2=7.5, avg tetap 150
        l1.refresh_from_db(); l2.refresh_from_db()
        self.assertEqual(l1.remaining_qty, Decimal('7.5'))
        self.assertEqual(l2.remaining_qty, Decimal('7.5'))
        result2 = consume_stock(self.item, self.eb, None, None, Decimal('5'),
                                '2026-01-04', 'sale_out', metode='average')
        self.assertEqual(result2.total_cost, Decimal('750'))  # tetap 5 × 150

    def test_average_full_consumption(self):
        from apps.inventory.ledger import consume_stock, get_available_stock
        self._inflow('10', '100', '2026-01-01')
        self._inflow('10', '200', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('20'),
                               '2026-01-03', 'sale_out', metode='average')
        self.assertEqual(result.total_cost, Decimal('3000'))  # 20 × 150
        self.assertEqual(get_available_stock(self.item, self.eb), Decimal('0'))

    def test_average_alloc_unit_cost_is_avg(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '100', '2026-01-01')
        self._inflow('10', '200', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('5'),
                               '2026-01-03', 'sale_out', metode='average')
        for alloc in result.allocations:
            self.assertEqual(alloc.unit_cost, Decimal('150.0000'))

    def test_average_reversal_restores_layers(self):
        from apps.inventory.ledger import consume_stock, reverse_movements
        l1 = self._inflow('10', '100', '2026-01-01')
        l2 = self._inflow('10', '200', '2026-01-02')
        consume_stock(self.item, self.eb, None, None, Decimal('5'),
                      '2026-01-03', 'sale_out', metode='average', source=self.item)
        reverse_movements(self.item)
        l1.refresh_from_db(); l2.refresh_from_db()
        self.assertEqual(l1.remaining_qty, Decimal('10'))
        self.assertEqual(l2.remaining_qty, Decimal('10'))
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.inventory.tests.ConsumeStockAverageTests -v 2`
Expected: FAIL — `name '_take_tier_average' is not defined` (dipanggil dari `consume_stock`).

- [ ] **Step 3: Implementasi `_take_tier_average`**

Di `apps/inventory/ledger.py`, tambahkan tepat setelah `_take_tier_sequential`:

```python
def _take_tier_average(layers, remaining):
    """Moving weighted average dalam satu tier.

    Biaya = qty × rata-rata tertimbang tier (dihitung sebelum pengurangan).
    Qty dikurangi PROPORSIONAL di semua layer agar rata-rata sisa tetap benar
    untuk konsumsi berikutnya. Sisa pembulatan dibebankan ke layer terakhir.

    Mengembalikan (picked, cost, taken) dengan
    picked = [(layer, take, avg), ...].
    """
    Q = Decimal('0.0001')
    active = [l for l in layers if l.remaining_qty > 0]
    total_qty = sum((l.remaining_qty for l in active), Decimal('0'))
    if total_qty <= 0:
        return [], Decimal('0'), Decimal('0')
    total_value = sum((l.remaining_qty * l.unit_cost for l in active), Decimal('0'))
    avg = (total_value / total_qty).quantize(Q)
    take_total = min(remaining, total_qty)

    if take_total >= total_qty:
        per_layer = [(l, l.remaining_qty) for l in active]
    else:
        fraction = take_total / total_qty
        per_layer = [(l, (l.remaining_qty * fraction).quantize(Q, rounding=ROUND_DOWN))
                     for l in active]
        allocated = sum((t for _, t in per_layer), Decimal('0'))
        residual = take_total - allocated
        if residual != 0:
            l_last, t_last = per_layer[-1]
            per_layer[-1] = (l_last, t_last + residual)

    picked = []
    cost = Decimal('0')
    taken = Decimal('0')
    for layer, take in per_layer:
        if take <= 0:
            continue
        layer.remaining_qty -= take
        layer.save(update_fields=['remaining_qty'])
        _mirror_decrement(layer, take, take * avg)
        picked.append((layer, take, avg))
        cost += take * avg
        taken += take
    return picked, cost, taken
```

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `python manage.py test apps.inventory.tests.ConsumeStockAverageTests -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests.py
git commit -m "feat(inventory): moving weighted average costing (proportional)"
```

---

## Task 5: Integrasi metode via `consume_stock` (alias & error)

**Files:**
- Modify: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan class di `apps/inventory/tests.py`:

```python
class ConsumeStockMethodResolutionTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Garam', tipe_item='RM')

    def _inflow(self, qty, cost, tanggal):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, None, None, Decimal(qty),
                             Decimal(cost), tanggal, 'purchase_in')

    def test_empty_method_defaults_fifo(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        self._inflow('10', '8', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('12'),
                               '2026-01-03', 'sale_out', metode='')
        self.assertEqual(result.total_cost, Decimal('66'))  # FIFO

    def test_weighted_moving_average_alias(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '100', '2026-01-01')
        self._inflow('10', '200', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('5'),
                               '2026-01-03', 'sale_out',
                               metode='weighted_moving_average')
        self.assertEqual(result.total_cost, Decimal('750'))  # sama dengan average

    def test_unknown_method_raises(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        with self.assertRaises(ValueError):
            consume_stock(self.item, self.eb, None, None, Decimal('1'),
                          '2026-01-03', 'sale_out', metode='rata2')

    def test_bulk_item_ignores_metode(self):
        """Item bulk (RMB/FGB/ITMB) value-based & method-agnostic (spec §B.4):
        metode tak dikenal pun tak memicu ValueError — cabang bulk tak validasi."""
        from apps.inventory.ledger import record_inflow, consume_stock
        bulk = ItemMasterPurchase.objects.create(nama='Pasir', tipe_item='RMB')
        # Konvensi bulk: nilai layer = remaining_qty × unit_cost = 1 × 1000 = 1000
        record_inflow(bulk, self.eb, None, None, Decimal('1'), Decimal('1000'),
                      '2026-01-01', 'purchase_in')
        # `value` = 400 (nilai stok yang dipotong), metode 'garbage' diabaikan
        result = consume_stock(bulk, self.eb, None, None, Decimal('400'),
                               '2026-01-03', 'sale_out', metode='garbage')
        self.assertEqual(result.total_cost, Decimal('400'))
```

- [ ] **Step 2: Jalankan test**

Run: `python manage.py test apps.inventory.tests.ConsumeStockMethodResolutionTests -v 2`
Expected: PASS (4 tests) — logika sudah ada dari Task 1–4. Jika `test_unknown_method_raises` gagal, pastikan `_normalize_method` dipanggil di `consume_stock` sebelum loop. `test_bulk_item_ignores_metode` mengunci bahwa cabang bulk dipanggil sebelum `_normalize_method`.

- [ ] **Step 3: Commit**

```bash
git add apps/inventory/tests.py
git commit -m "test(inventory): method alias + unknown-method error via consume_stock"
```

---

## Task 6: Wiring Sales — teruskan metode item

**Files:**
- Modify: `apps/sales/services.py:244-255`

- [ ] **Step 1: Ubah kedua panggilan `consume_stock` di `process_sales_fifo`**

Di `apps/sales/services.py`, pada cabang bulk (baris ~244) tambahkan argumen `metode`:

```python
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        amount, sales_header.tanggal, 'sale_out', source=si,
                        metode=si.item.metode_biaya_persediaan,
                        warehouse=si.warehouse)
```

Dan pada cabang non-bulk (baris ~251):

```python
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        si.quantity, sales_header.tanggal, 'sale_out', source=si,
                        metode=si.item.metode_biaya_persediaan,
                        warehouse=si.warehouse)
```

(Untuk item bulk `metode` diabaikan engine, tapi diteruskan agar seragam.)

- [ ] **Step 2: Jalankan test regresi Sales**

Run: `python manage.py test apps.sales -v 1`
Expected: PASS — item existing punya `metode_biaya_persediaan=''` → FIFO, perilaku tak berubah.

- [ ] **Step 3: Commit**

```bash
git add apps/sales/services.py
git commit -m "feat(sales): honor item costing method in process_sales_fifo"
```

---

## Task 7: Wiring Manufacturing — konsumsi RM teruskan metode

**Files:**
- Modify: `apps/manufacturing/services.py:345-349`

- [ ] **Step 1: Ubah panggilan `consume_stock` RM**

Di `apps/manufacturing/services.py` (dalam `process_production`, baris ~345):

```python
            _rm_result = consume_stock(
                line.raw_material, production_order.entitas_bisnis,
                production_order.entitas_bisnis_lv2, production_order.entitas_bisnis_lv3,
                qty_needed, production_order.tanggal, 'production_out',
                source=production_order,
                metode=line.raw_material.metode_biaya_persediaan,
                warehouse=production_order.warehouse_rm)
```

- [ ] **Step 2: Jalankan test regresi Manufacturing**

Run: `python manage.py test apps.manufacturing -v 1`
Expected: PASS — RM existing `metode_biaya_persediaan=''` → FIFO, tak berubah.

- [ ] **Step 3: Commit**

```bash
git add apps/manufacturing/services.py
git commit -m "feat(manufacturing): honor RM costing method in process_production"
```

---

## Task 8: Manufacturing preview simulasi method-aware

**Files:**
- Modify: `apps/manufacturing/services.py:52-122`
- Test: `apps/manufacturing/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan class di `apps/manufacturing/tests.py` (ikuti pola fixtures class simulasi FIFO yang ada — buat item RM + dua FIFOBatch beda harga/tanggal). Gunakan model `FIFOBatch` seperti test existing:

```python
class SimulateCostMethodTests(TestCase):
    def setUp(self):
        from apps.purchase.models import ItemMasterPurchase, FIFOBatch
        self.rm = ItemMasterPurchase.objects.create(nama='RM-M', tipe_item='RM')
        FIFOBatch.objects.create(item=self.rm, quantity=Decimal('10'),
                                 remaining_qty=Decimal('10'), unit_price=Decimal('100'),
                                 tanggal='2026-01-01')
        FIFOBatch.objects.create(item=self.rm, quantity=Decimal('10'),
                                 remaining_qty=Decimal('10'), unit_price=Decimal('200'),
                                 tanggal='2026-01-02')

    def test_fifo_default(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('12'))
        self.assertEqual(cost, Decimal('1400'))   # 10×100 + 2×200
        self.assertEqual(filled, Decimal('12'))

    def test_lifo(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('12'), metode='lifo')
        self.assertEqual(cost, Decimal('2200'))   # 10×200 + 2×100
        self.assertEqual(filled, Decimal('12'))

    def test_average(self):
        from apps.manufacturing.services import _simulate_fifo_cost
        cost, filled = _simulate_fifo_cost(self.rm.pk, Decimal('5'), metode='average')
        self.assertEqual(cost, Decimal('750'))     # 5 × 150
        self.assertEqual(filled, Decimal('5'))
```

> Cek nama field `FIFOBatch` yang benar dari test simulasi yang sudah ada di file ini (mis. `quantity`/`unit_price`/`tanggal`) dan samakan. Jika field berbeda, sesuaikan `setUp`.

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `python manage.py test apps.manufacturing.tests.SimulateCostMethodTests -v 2`
Expected: FAIL — `_simulate_fifo_cost() got an unexpected keyword argument 'metode'`.

- [ ] **Step 3: Tambahkan param `metode` ke `_simulate_fifo_cost`**

Ganti fungsi `_simulate_fifo_cost` (baris ~52-80) menjadi:

```python
def _simulate_fifo_cost(item_id: int, quantity: Decimal, metode: str = 'fifo') -> tuple[Decimal, Decimal]:
    """Read-only simulasi biaya konsumsi — cocok dengan posting nyata per metode.

    metode: '' / 'fifo' → tertua dulu; 'lifo' → terbaru dulu;
            'average' / 'weighted_moving_average' → qty × rata-rata tertimbang.
    Mengembalikan (total_cost, qty_filled).
    """
    from apps.inventory.ledger import _normalize_method
    method = _normalize_method(metode)
    batches = FIFOBatch.objects.filter(item_id=item_id, remaining_qty__gt=0)

    if method == 'average':
        agg = batches.aggregate(
            total_qty=Sum('remaining_qty'),
            total_value=Sum(F('remaining_qty') * F('unit_price')),
        )
        total_qty = agg['total_qty'] or Decimal('0')
        total_value = agg['total_value'] or Decimal('0')
        if total_qty <= 0:
            return Decimal('0'), Decimal('0')
        avg = (total_value / total_qty).quantize(Decimal('0.0001'))
        qty_filled = min(quantity, total_qty)
        return (avg * qty_filled).quantize(Decimal('0.0001')), qty_filled

    order_by = ('tanggal', 'created_at') if method == 'fifo' else ('-tanggal', '-created_at')
    batches = batches.order_by(*order_by)
    remaining = quantity
    total_cost = Decimal('0')
    qty_filled = Decimal('0')
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_qty, remaining)
        total_cost += take * batch.unit_price
        qty_filled += take
        remaining -= take
    return total_cost, qty_filled
```

Pastikan `F` dan `Sum` sudah di-import di atas file (mereka dipakai `_average_unit_cost` sekitar baris 40-43 — jadi sudah ada).

- [ ] **Step 4: Teruskan metode item di `get_bom_preview`**

Di `get_bom_preview` (baris ~103), ubah panggilan:

```python
        fifo_cost, qty_filled = _simulate_fifo_cost(
            line.raw_material_id, qty_total,
            metode=line.raw_material.metode_biaya_persediaan,
        )
```

- [ ] **Step 5: Jalankan test baru + regresi simulasi lama**

Run: `python manage.py test apps.manufacturing.tests.SimulateCostMethodTests -v 2`
Expected: PASS (3 tests).

Run: `python manage.py test apps.manufacturing -v 1`
Expected: PASS — test `_simulate_fifo_cost(pk, qty)` lama tetap jalan (default `metode='fifo'`).

- [ ] **Step 6: Commit**

```bash
git add apps/manufacturing/services.py apps/manufacturing/tests.py
git commit -m "feat(manufacturing): method-aware RM cost simulation in preview"
```

---

## Task 9: Verifikasi menyeluruh

**Files:** tidak ada perubahan kode.

- [ ] **Step 1: Jalankan seluruh test app terdampak**

Run: `python manage.py test apps.inventory apps.sales apps.manufacturing -v 1`
Expected: PASS semua. Bila ada gagal, perbaiki sebelum lanjut (jangan klaim selesai tanpa output hijau).

- [ ] **Step 2: Cek tak ada pemanggil `consume_stock` lain yang terlewat**

Run: `grep -rn "consume_stock(" apps/ --include=*.py | grep -v "def consume_stock" | grep -v ledger.py`
Expected: hanya baris di `apps/sales/services.py` dan `apps/manufacturing/services.py` yang sudah diperbarui (Task 6 & 7). Bila ada pemanggil lain, teruskan `metode=<item>.metode_biaya_persediaan` dengan pola yang sama.

- [ ] **Step 3: Commit akhir (bila ada penyesuaian dari Step 2)**

```bash
git add -A
git commit -m "chore(inventory): finalize Fase 3 costing multi-metode wiring"
```

---

## Catatan Eksekusi

- Item bulk (RMB/FGB/ITMB): metode diabaikan (jalur `_consume_stock_bulk` tak berubah) — ini disengaja per spec §B.4. Tidak ada test yang mengubah perilaku bulk.
- Data historis tidak di-recompute; hanya transaksi baru memakai metode item. Item lama dengan `metode_biaya_persediaan=''` tetap FIFO.
- Reversal average bergantung pada `StockConsumption.qty` per layer (proporsi tersimpan) — `reverse_movements` yang ada sudah menangani ini tanpa perubahan.
