# Fase 8 — Pelaporan Inventory & Aset Tetap: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only reporting layer (Inventory Valuation, HPP/COGS, Slow/Fast Moving, Asset Register) plus a reports hub, all sourced from the authoritative `StockMovement`/`StockConsumption` ledger, with XLSX + print-PDF export.

**Architecture:** Pure query/aggregation functions live in `apps/inventory/reports.py` and `apps/aset_tetap/reports.py` (no HTTP, unit-tested). Thin Django views call them, apply EB-tree filtering via existing `_resolve_eb_lv1_ids`, and render templates or export. No model or migration changes.

**Tech Stack:** Django 6.0, pytest (`DJANGO_SETTINGS_MODULE=naveda_integra.settings.test`), openpyxl (XLSX export, existing convention), Decimal arithmetic.

**Conventions confirmed from codebase:**
- Tests: `django.test.TestCase`, files named `tests_fase8*.py`; run with `pytest`.
- Test data: `TipeEntitas.objects.create(nama='PT')`, `EntitasBisnis.objects.create(nama=..., tipe_entitas=...)`, `ItemMasterPurchase.objects.create(nama=..., tipe_item='RM')`, `Warehouse.objects.create(entitas_bisnis=eb, nama=...)`.
- Ledger helpers: `apps.inventory.ledger.record_inflow(item, eb_lv1, eb_lv2, eb_lv3, qty, unit_cost, tanggal, movement_type, *, warehouse=None)` and `consume_stock(item, eb_lv1, eb_lv2, eb_lv3, qty, tanggal, movement_type, source=None, metode='fifo', *, warehouse=None)`.
- Export ("Excel") = openpyxl XLSX, matching `inventory_export` at [apps/inventory/views.py:1313](../../apps/inventory/views.py). PDF = print-friendly HTML template rendered for browser printing, matching `inventory_export_pdf`.
- EB filter helpers: `_get_eb_tree(user)` and `_resolve_eb_lv1_ids(list[str], user) -> set[int]` in `apps/purchase/views.py`.
- Item category: `item.kategori` (FK, `.nama`). Asset category derived via `aset.item.kategori`.

---

## Task 1: Inventory Valuation report function

**Files:**
- Create: `apps/inventory/reports.py`
- Test: `apps/inventory/tests_fase8.py`

- [ ] **Step 1: Write the failing test**

Create `apps/inventory/tests_fase8.py`:

```python
"""Tests Fase 8 — laporan inventory (valuation, hpp, velocity)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger, reports


class ValuationReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_valuation_sums_remaining_layers(self):
        # 20 @ 4 and 10 @ 6; consume 5 (FIFO) -> remaining 15 @ 4 + 10 @ 6
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('6'), date(2026, 1, 2), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('5'),
                             date(2026, 1, 3), 'sale_out', warehouse=self.wh)

        result = reports.valuation_report({self.eb.pk})
        rows = result['rows']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['on_hand_qty'], Decimal('25'))
        # 15*4 + 10*6 = 60 + 60 = 120
        self.assertEqual(row['total_value'], Decimal('120'))
        self.assertEqual(result['grand_total_value'], Decimal('120'))

    def test_valuation_isolates_eb(self):
        eb_b = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        result = reports.valuation_report({eb_b.pk})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['grand_total_value'], Decimal('0'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/inventory/tests_fase8.py::ValuationReportTests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.inventory.reports'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/inventory/reports.py`:

```python
"""Laporan inventory — valuasi, HPP, velocity. Read-only, sumber StockMovement.

Semua fungsi murni (tanpa request). Kuantitas & nilai dalam base uom (Decimal).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from .models import StockMovement, StockConsumption

INVENTORY_TIPE_ITEMS = ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB')


def _kategori_nama(item) -> str:
    return item.kategori.nama if getattr(item, 'kategori', None) else '(Tanpa Kategori)'


def valuation_report(eb_lv1_ids, *, warehouse_id=None, tipe_item=None, as_of=None):
    """Nilai persediaan on-hand dari layer inflow tersisa (remaining_qty > 0).

    eb_lv1_ids: iterable PK EntitasBisnis lv1 yang boleh diakses.
    as_of: bila diisi, hanya layer dengan tanggal <= as_of (aproksimasi untuk
    tanggal lampau; eksak untuk hari ini). Kembalikan dict rows + subtotal.
    """
    eb_ids = list(eb_lv1_ids)
    layers = (
        StockMovement.objects
        .filter(remaining_qty__gt=0, entitas_bisnis_id__in=eb_ids,
                item__tipe_item__in=INVENTORY_TIPE_ITEMS)
        .select_related('item', 'item__kategori', 'item__stock_uom', 'warehouse')
    )
    if warehouse_id:
        layers = layers.filter(warehouse_id=warehouse_id)
    if tipe_item:
        layers = layers.filter(item__tipe_item=tipe_item)
    if as_of:
        layers = layers.filter(tanggal__lte=as_of)

    agg = defaultdict(lambda: {'on_hand_qty': Decimal('0'), 'total_value': Decimal('0')})
    meta = {}
    for lyr in layers:
        key = lyr.item_id
        agg[key]['on_hand_qty'] += lyr.remaining_qty
        agg[key]['total_value'] += lyr.remaining_qty * lyr.unit_cost
        meta[key] = lyr.item

    rows = []
    sub_kat = defaultdict(lambda: Decimal('0'))
    grand = Decimal('0')
    for item_id, vals in agg.items():
        item = meta[item_id]
        qty = vals['on_hand_qty']
        value = vals['total_value']
        unit_cost_avg = (value / qty).quantize(Decimal('0.0001')) if qty else Decimal('0')
        kategori = _kategori_nama(item)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'tipe_item': item.tipe_item,
            'kategori': kategori,
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'on_hand_qty': qty,
            'unit_cost_avg': unit_cost_avg,
            'total_value': value,
        })
        sub_kat[kategori] += value
        grand += value

    rows.sort(key=lambda r: (r['kategori'], r['item_id']))
    return {
        'rows': rows,
        'subtotals_kategori': dict(sub_kat),
        'grand_total_value': grand,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/inventory/tests_fase8.py::ValuationReportTests -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/reports.py apps/inventory/tests_fase8.py
git commit -m "feat(inventory): laporan valuasi persediaan dari StockMovement (Fase 8)"
```

---

## Task 2: HPP / COGS report function

**Files:**
- Modify: `apps/inventory/reports.py` (add `hpp_report`)
- Test: `apps/inventory/tests_fase8.py` (add `HppReportTests`)

- [ ] **Step 1: Write the failing test**

Append to `apps/inventory/tests_fase8.py`:

```python
class HppReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_hpp_fifo_across_two_layers(self):
        # 10 @ 4, then 10 @ 6; sell 15 FIFO -> HPP = 10*4 + 5*6 = 70
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('6'), date(2026, 1, 2), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('15'),
                             date(2026, 1, 10), 'sale_out', warehouse=self.wh)

        result = reports.hpp_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(len(result['rows']), 1)
        row = result['rows'][0]
        self.assertEqual(row['qty_terjual'], Decimal('15'))
        self.assertEqual(row['total_hpp'], Decimal('70'))
        self.assertEqual(result['grand_total_hpp'], Decimal('70'))

    def test_hpp_excludes_out_of_range(self):
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('5'),
                             date(2026, 2, 10), 'sale_out', warehouse=self.wh)
        result = reports.hpp_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['grand_total_hpp'], Decimal('0'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/inventory/tests_fase8.py::HppReportTests -v`
Expected: FAIL — `AttributeError: module 'apps.inventory.reports' has no attribute 'hpp_report'`

- [ ] **Step 3: Write minimal implementation**

Add to `apps/inventory/reports.py`:

```python
def hpp_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *, warehouse_id=None):
    """HPP (COGS) untuk penjualan pada rentang tanggal, biaya layer-akurat.

    Sumber: gerakan sale_out pada rentang, biaya diambil dari StockConsumption
    (qty*unit_cost per layer). return_customer pada rentang mengurangi qty & HPP.
    """
    eb_ids = list(eb_lv1_ids)
    out_qs = (
        StockMovement.objects
        .filter(movement_type='sale_out', entitas_bisnis_id__in=eb_ids,
                tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)
        .select_related('item', 'item__kategori', 'item__stock_uom')
    )
    if warehouse_id:
        out_qs = out_qs.filter(warehouse_id=warehouse_id)

    agg = defaultdict(lambda: {'qty': Decimal('0'), 'hpp': Decimal('0')})
    meta = {}
    for mv in out_qs:
        # qty pada outflow bertanda negatif; qty terjual = -qty
        agg[mv.item_id]['qty'] += -mv.qty
        hpp = Decimal('0')
        for alloc in StockConsumption.objects.filter(out_movement=mv):
            hpp += alloc.qty * alloc.unit_cost
        agg[mv.item_id]['hpp'] += hpp
        meta[mv.item_id] = mv.item

    # retur pelanggan mengurangi HPP & qty (pembalik penjualan)
    ret_qs = (
        StockMovement.objects
        .filter(movement_type='return_customer', entitas_bisnis_id__in=eb_ids,
                tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)
        .select_related('item')
    )
    if warehouse_id:
        ret_qs = ret_qs.filter(warehouse_id=warehouse_id)
    for mv in ret_qs:
        if mv.item_id in agg:
            agg[mv.item_id]['qty'] -= mv.qty  # inflow qty positif -> kurangi
            agg[mv.item_id]['hpp'] -= mv.qty * mv.unit_cost

    rows = []
    sub_kat = defaultdict(lambda: Decimal('0'))
    grand = Decimal('0')
    for item_id, vals in agg.items():
        item = meta[item_id]
        kategori = _kategori_nama(item)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'kategori': kategori,
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'qty_terjual': vals['qty'],
            'total_hpp': vals['hpp'],
        })
        sub_kat[kategori] += vals['hpp']
        grand += vals['hpp']

    rows.sort(key=lambda r: (r['kategori'], r['item_id']))
    return {
        'rows': rows,
        'subtotals_kategori': dict(sub_kat),
        'grand_total_hpp': grand,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/inventory/tests_fase8.py::HppReportTests -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/reports.py apps/inventory/tests_fase8.py
git commit -m "feat(inventory): laporan HPP/COGS dari StockConsumption (Fase 8)"
```

---

## Task 3: Slow/Fast Moving (velocity) report function

**Files:**
- Modify: `apps/inventory/reports.py` (add `velocity_report`)
- Test: `apps/inventory/tests_fase8.py` (add `VelocityReportTests`)

- [ ] **Step 1: Write the failing test**

Append to `apps/inventory/tests_fase8.py`:

```python
class VelocityReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')

    def test_fast_tag_without_movement_flags_mismatch(self):
        item = ItemMasterPurchase.objects.create(
            nama='Kopi', tipe_item='RM', velocity_category='fast')
        ledger.record_inflow(item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        rows = reports.velocity_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        row = next(r for r in rows if r['item'].pk == item.pk)
        self.assertEqual(row['qty_keluar'], Decimal('0'))
        self.assertTrue(row['mismatch_flag'])
        self.assertEqual(row['on_hand'], Decimal('10'))

    def test_movement_metrics_computed(self):
        item = ItemMasterPurchase.objects.create(
            nama='Teh', tipe_item='RM', velocity_category='slow')
        ledger.record_inflow(item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(item, self.eb, None, None, Decimal('6'),
                             date(2026, 1, 20), 'sale_out', warehouse=self.wh)
        rows = reports.velocity_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        row = next(r for r in rows if r['item'].pk == item.pk)
        self.assertEqual(row['qty_keluar'], Decimal('6'))
        self.assertEqual(row['jumlah_gerakan'], 1)
        self.assertEqual(row['on_hand'], Decimal('4'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/inventory/tests_fase8.py::VelocityReportTests -v`
Expected: FAIL — `AttributeError: ... has no attribute 'velocity_report'`

- [ ] **Step 3: Write minimal implementation**

Add to `apps/inventory/reports.py` (add `from .ledger import OUTFLOW_MOVEMENT_TYPES` to imports at top):

```python
def velocity_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *,
                    warehouse_id=None, velocity_filter=None):
    """Slow/Fast moving: tag manual velocity_category + metrik aktual per item.

    Untuk tiap item persediaan dalam scope EB: total qty keluar & jumlah gerakan
    pada rentang, hari sejak keluar terakhir, on-hand saat ini. mismatch_flag
    True bila tag 'fast'/'medium' tapi tak ada gerakan keluar pada rentang, atau
    tag 'dead' tapi ADA gerakan.
    """
    from datetime import date as _date
    eb_ids = list(eb_lv1_ids)

    base = StockMovement.objects.filter(
        entitas_bisnis_id__in=eb_ids, item__tipe_item__in=INVENTORY_TIPE_ITEMS)
    if warehouse_id:
        base = base.filter(warehouse_id=warehouse_id)

    # item-item yang punya gerakan apa pun dalam scope
    items = {}
    for mv in base.select_related('item', 'item__kategori', 'item__stock_uom'):
        items[mv.item_id] = mv.item

    outflow = base.filter(
        movement_type__in=OUTFLOW_MOVEMENT_TYPES,
        tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)

    qty_keluar = defaultdict(lambda: Decimal('0'))
    jumlah = defaultdict(int)
    last_out = {}
    for mv in outflow:
        qty_keluar[mv.item_id] += -mv.qty
        jumlah[mv.item_id] += 1
        if mv.item_id not in last_out or mv.tanggal > last_out[mv.item_id]:
            last_out[mv.item_id] = mv.tanggal

    onhand = defaultdict(lambda: Decimal('0'))
    for r in base.filter(remaining_qty__gt=0).values('item_id').annotate(
            s=Sum('remaining_qty')):
        onhand[r['item_id']] = r['s'] or Decimal('0')

    today = _date.today()
    rows = []
    for item_id, item in items.items():
        vc = item.velocity_category or ''
        if velocity_filter and vc != velocity_filter:
            continue
        qk = qty_keluar[item_id]
        moved = qk > 0
        last = last_out.get(item_id)
        mismatch = (vc in ('fast', 'medium') and not moved) or (vc == 'dead' and moved)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'kategori': _kategori_nama(item),
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'velocity_category': vc,
            'velocity_label': item.get_velocity_category_display() if vc else '(Belum ditag)',
            'qty_keluar': qk,
            'jumlah_gerakan': jumlah[item_id],
            'hari_sejak_keluar_terakhir': (today - last).days if last else None,
            'on_hand': onhand[item_id],
            'mismatch_flag': mismatch,
        })

    rows.sort(key=lambda r: (-r['qty_keluar'], r['item_id']))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/inventory/tests_fase8.py::VelocityReportTests -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/reports.py apps/inventory/tests_fase8.py
git commit -m "feat(inventory): laporan slow/fast moving (velocity) (Fase 8)"
```

---

## Task 4: Asset Register report function

**Files:**
- Modify: `apps/aset_tetap/reports.py` (add `asset_register`)
- Test: Create `apps/aset_tetap/tests_fase8_register.py`

- [ ] **Step 1: Write the failing test**

Create `apps/aset_tetap/tests_fase8_register.py`:

```python
"""Tests Fase 8 — asset register."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from apps.aset_tetap.models import AsetTetapRecord
from apps.aset_tetap import reports


class AssetRegisterTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.kat = KategoriItem.objects.create(nama='Kendaraan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Truk', tipe_item='ATP', kategori=self.kat)

    def _mk(self, harga, akum, status='aktif'):
        return AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('1'),
            harga_perolehan=Decimal(harga), akumulasi_penyusutan=Decimal(akum),
            tanggal_perolehan=date(2026, 1, 1), status=status)

    def test_register_rows_and_subtotal(self):
        self._mk('100000000', '20000000')
        self._mk('50000000', '10000000')
        result = reports.asset_register({self.eb.pk}, group_by='kategori')
        self.assertEqual(len(result['rows']), 2)
        sub = result['subtotals']['Kendaraan']
        self.assertEqual(sub['harga_perolehan'], Decimal('150000000'))
        self.assertEqual(sub['nilai_buku'], Decimal('120000000'))
        self.assertEqual(result['grand_total']['nilai_buku'], Decimal('120000000'))

    def test_register_filters_status(self):
        self._mk('100000000', '0', status='aktif')
        self._mk('50000000', '0', status='dilepas')
        result = reports.asset_register({self.eb.pk}, status='aktif')
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['harga_perolehan'], Decimal('100000000'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest apps/aset_tetap/tests_fase8_register.py -v`
Expected: FAIL — `AttributeError: module 'apps.aset_tetap.reports' has no attribute 'asset_register'`

- [ ] **Step 3: Write minimal implementation**

Add to `apps/aset_tetap/reports.py` (add `from collections import defaultdict` at top):

```python
def asset_register(eb_lv1_ids, *, kategori_id=None, lokasi_id=None,
                   departemen_id=None, pic=None, status=None, group_by='kategori'):
    """Asset register terfilter dengan subtotal per dimensi grouping.

    group_by: 'kategori' | 'lokasi' | 'departemen'. Nilai perolehan memakai
    total_value (quantity*harga_perolehan). Kembalikan rows + subtotals + grand.
    """
    qs = (AsetTetapRecord.objects
          .filter(entitas_bisnis_id__in=list(eb_lv1_ids))
          .select_related('item', 'item__kategori', 'lokasi_aset', 'departemen'))
    if kategori_id:
        qs = qs.filter(item__kategori_id=kategori_id)
    if lokasi_id:
        qs = qs.filter(lokasi_aset_id=lokasi_id)
    if departemen_id:
        qs = qs.filter(departemen_id=departemen_id)
    if pic:
        qs = qs.filter(pic__icontains=pic)
    if status:
        qs = qs.filter(status=status)

    def _group_key(a):
        if group_by == 'lokasi':
            return a.lokasi_aset.nama if a.lokasi_aset else '(Tanpa Lokasi)'
        if group_by == 'departemen':
            return a.departemen.nama if a.departemen else '(Tanpa Departemen)'
        return a.item.kategori.nama if a.item and a.item.kategori else '(Tanpa Kategori)'

    rows = []
    subtotals = defaultdict(lambda: {
        'harga_perolehan': Decimal('0'), 'akumulasi': Decimal('0'),
        'nilai_buku': Decimal('0')})
    grand = {'harga_perolehan': Decimal('0'), 'akumulasi': Decimal('0'),
             'nilai_buku': Decimal('0')}
    for a in qs:
        perolehan = a.total_value or Decimal('0')
        akum = a.akumulasi_penyusutan or Decimal('0')
        nb = a.nilai_buku
        gk = _group_key(a)
        rows.append({
            'aset': a,
            'kode': a.aset_number,
            'nama': a.item.nama if a.item else '',
            'kategori': a.item.kategori.nama if a.item and a.item.kategori else '',
            'lokasi': a.lokasi_aset.nama if a.lokasi_aset else '',
            'departemen': a.departemen.nama if a.departemen else '',
            'pic': a.pic or '',
            'tanggal_perolehan': a.tanggal_perolehan,
            'harga_perolehan': perolehan,
            'akumulasi_penyusutan': akum,
            'nilai_buku': nb,
            'status': a.get_status_display(),
            'kondisi': a.get_kondisi_display(),
            'group_key': gk,
        })
        subtotals[gk]['harga_perolehan'] += perolehan
        subtotals[gk]['akumulasi'] += akum
        subtotals[gk]['nilai_buku'] += nb
        grand['harga_perolehan'] += perolehan
        grand['akumulasi'] += akum
        grand['nilai_buku'] += nb

    rows.sort(key=lambda r: (r['group_key'], r['kode']))
    return {'rows': rows, 'subtotals': dict(subtotals), 'grand_total': grand,
            'group_by': group_by}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest apps/aset_tetap/tests_fase8_register.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add apps/aset_tetap/reports.py apps/aset_tetap/tests_fase8_register.py
git commit -m "feat(aset_tetap): asset register report + subtotal per dimensi (Fase 8)"
```

---

## Task 5: Inventory report views (valuasi, hpp, velocity) + XLSX/PDF export

**Files:**
- Modify: `apps/inventory/views.py` (add views at end, before final blank line)
- Modify: `apps/inventory/urls.py`

- [ ] **Step 1: Add the three report views**

Append to `apps/inventory/views.py` (imports already present: `Decimal`, `timezone`, `render`, `HttpResponse`, `login_required`, `ratelimit`, `rate_from`, `_get_eb_tree`, `_resolve_eb_lv1_ids`, `Warehouse`; add `from . import reports` and `from apps.purchase.models import ItemMasterPurchase, KategoriItem` inside each view or at top — follow existing local-import style):

```python
# ── Laporan Fase 8 ───────────────────────────────────────────────────────────

def _report_eb_ids(request):
    """Resolve EB filter selections to lv1 ids the user may access.

    Bila tak ada filter, pakai seluruh lv1 yang terjangkau dari eb_tree.
    """
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    if eb_filter_list:
        return _resolve_eb_lv1_ids(eb_filter_list, request.user), eb_filter_list
    # kumpulkan semua lv1 dari tree
    ids = {node['id'] for node in _get_eb_tree(request.user) if node.get('id')}
    return ids, eb_filter_list


def _month_range(request):
    from datetime import date
    today = timezone.now().date()
    default_dari = today.replace(day=1)
    dari = request.GET.get('tanggal_dari') or default_dari.isoformat()
    sampai = request.GET.get('tanggal_sampai') or today.isoformat()
    return dari, sampai


@login_required
def laporan_valuasi(request):
    from . import reports
    from apps.purchase.models import ItemMasterPurchase
    eb_ids, eb_filter_list = _report_eb_ids(request)
    wh_id = request.GET.get('warehouse') or None
    tipe = request.GET.get('tipe') or None
    as_of = request.GET.get('as_of') or None
    data = reports.valuation_report(eb_ids, warehouse_id=wh_id, tipe_item=tipe, as_of=as_of)

    export = request.GET.get('export')
    if export == 'csv':
        return _export_valuasi_xlsx(data)
    if export == 'pdf':
        return render(request, 'inventory/_laporan_print.html', {
            'title': 'Laporan Valuasi Persediaan', 'generated_at': timezone.now(),
            'columns': ['Kategori', 'Item', 'Nama', 'Satuan', 'On-hand', 'Biaya/Unit', 'Nilai'],
            'rows': [[r['kategori'], r['item_id'], r['nama'], r['satuan'],
                      r['on_hand_qty'], r['unit_cost_avg'], r['total_value']] for r in data['rows']],
            'total_label': 'Total Nilai', 'total_value': data['grand_total_value'],
        })

    return render(request, 'inventory/laporan_valuasi.html', {
        'title': 'Laporan Valuasi Persediaan', 'data': data,
        'items_tipe': [('RM', 'Raw Material'), ('FG', 'Finished Good'), ('ITM', 'Item Lainnya'),
                       ('RMB', 'Raw Material (Bulk)'), ('FGB', 'Finished Good (Bulk)'),
                       ('ITMB', 'Item Lainnya (Bulk)')],
        'warehouses': Warehouse.objects.filter(is_active=True).order_by('kode'),
        'eb_tree': _get_eb_tree(request.user), 'eb_filter_list': eb_filter_list,
        'wh_filter': wh_id or '', 'tipe_filter': tipe or '', 'as_of': as_of or '',
    })


@login_required
def laporan_hpp(request):
    from . import reports
    eb_ids, eb_filter_list = _report_eb_ids(request)
    wh_id = request.GET.get('warehouse') or None
    dari, sampai = _month_range(request)
    data = reports.hpp_report(eb_ids, dari, sampai, warehouse_id=wh_id)

    export = request.GET.get('export')
    if export == 'csv':
        return _export_hpp_xlsx(data)
    if export == 'pdf':
        return render(request, 'inventory/_laporan_print.html', {
            'title': f'Laporan HPP {dari} s/d {sampai}', 'generated_at': timezone.now(),
            'columns': ['Kategori', 'Item', 'Nama', 'Satuan', 'Qty Terjual', 'Total HPP'],
            'rows': [[r['kategori'], r['item_id'], r['nama'], r['satuan'],
                      r['qty_terjual'], r['total_hpp']] for r in data['rows']],
            'total_label': 'Total HPP', 'total_value': data['grand_total_hpp'],
        })

    return render(request, 'inventory/laporan_hpp.html', {
        'title': 'Laporan HPP (COGS)', 'data': data,
        'warehouses': Warehouse.objects.filter(is_active=True).order_by('kode'),
        'eb_tree': _get_eb_tree(request.user), 'eb_filter_list': eb_filter_list,
        'wh_filter': wh_id or '', 'tanggal_dari': dari, 'tanggal_sampai': sampai,
    })


@login_required
def laporan_velocity(request):
    from . import reports
    eb_ids, eb_filter_list = _report_eb_ids(request)
    wh_id = request.GET.get('warehouse') or None
    dari, sampai = _month_range(request)
    vc = request.GET.get('velocity') or None
    rows = reports.velocity_report(eb_ids, dari, sampai, warehouse_id=wh_id, velocity_filter=vc)

    export = request.GET.get('export')
    if export == 'csv':
        return _export_velocity_xlsx(rows)
    if export == 'pdf':
        return render(request, 'inventory/_laporan_print.html', {
            'title': f'Laporan Slow/Fast Moving {dari} s/d {sampai}',
            'generated_at': timezone.now(),
            'columns': ['Item', 'Nama', 'Tag', 'Qty Keluar', 'Gerakan', 'Hari Idle', 'On-hand', 'Mismatch'],
            'rows': [[r['item_id'], r['nama'], r['velocity_label'], r['qty_keluar'],
                      r['jumlah_gerakan'],
                      r['hari_sejak_keluar_terakhir'] if r['hari_sejak_keluar_terakhir'] is not None else '-',
                      r['on_hand'], 'YA' if r['mismatch_flag'] else ''] for r in rows],
            'total_label': '', 'total_value': None,
        })

    return render(request, 'inventory/laporan_velocity.html', {
        'title': 'Laporan Slow/Fast Moving', 'rows': rows,
        'velocity_choices': [('fast', 'Fast Moving'), ('medium', 'Medium (B)'),
                             ('slow', 'Slow (C)'), ('dead', 'Dead Stock')],
        'warehouses': Warehouse.objects.filter(is_active=True).order_by('kode'),
        'eb_tree': _get_eb_tree(request.user), 'eb_filter_list': eb_filter_list,
        'wh_filter': wh_id or '', 'tanggal_dari': dari, 'tanggal_sampai': sampai,
        'velocity_filter': vc or '',
    })


def _xlsx_response(title, headers, data_rows, numeric_cols, filename):
    """Bangun XLSX satu-sheet (pola sama dengan inventory_export)."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]
    hf = Font(bold=True)
    fill = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hf
        c.fill = fill
        c.alignment = Alignment(horizontal='center')
    for rnum, row in enumerate(data_rows, 2):
        for col, val in enumerate(row, 1):
            c = ws.cell(row=rnum, column=col,
                        value=float(val) if col in numeric_cols and val is not None else val)
            if col in numeric_cols:
                c.alignment = Alignment(horizontal='right')
                c.number_format = '#,##0.00'
    for i in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 18
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(resp)
    return resp


def _export_valuasi_xlsx(data):
    headers = ['Kategori', 'Item ID', 'Nama', 'Tipe', 'Satuan', 'On-hand', 'Biaya/Unit', 'Nilai']
    rows = [[r['kategori'], r['item_id'], r['nama'], r['tipe_item'], r['satuan'],
             r['on_hand_qty'], r['unit_cost_avg'], r['total_value']] for r in data['rows']]
    return _xlsx_response('Valuasi', headers, rows, {6, 7, 8}, 'valuasi_persediaan.xlsx')


def _export_hpp_xlsx(data):
    headers = ['Kategori', 'Item ID', 'Nama', 'Satuan', 'Qty Terjual', 'Total HPP']
    rows = [[r['kategori'], r['item_id'], r['nama'], r['satuan'],
             r['qty_terjual'], r['total_hpp']] for r in data['rows']]
    return _xlsx_response('HPP', headers, rows, {5, 6}, 'laporan_hpp.xlsx')


def _export_velocity_xlsx(rows_in):
    headers = ['Item ID', 'Nama', 'Kategori', 'Tag Velocity', 'Qty Keluar', 'Jml Gerakan',
               'Hari Idle', 'On-hand', 'Mismatch']
    rows = [[r['item_id'], r['nama'], r['kategori'], r['velocity_label'], r['qty_keluar'],
             r['jumlah_gerakan'],
             r['hari_sejak_keluar_terakhir'] if r['hari_sejak_keluar_terakhir'] is not None else '',
             r['on_hand'], 'YA' if r['mismatch_flag'] else ''] for r in rows_in]
    return _xlsx_response('Velocity', headers, rows, {5, 6, 8}, 'slow_fast_moving.xlsx')
```

Note: `_get_eb_tree` returns nodes; confirm each node dict exposes an `id` key for lv1. If the key differs, adjust `_report_eb_ids` to read the correct lv1-id key (inspect `_get_eb_tree` output before finalizing this view).

- [ ] **Step 2: Wire the URLs**

In `apps/inventory/urls.py`, add inside `urlpatterns` (after the `kartu-stok/` line):

```python
    path('laporan/hub/', views.laporan_hub, name='laporan_hub'),
    path('laporan/valuasi/', views.laporan_valuasi, name='laporan_valuasi'),
    path('laporan/hpp/', views.laporan_hpp, name='laporan_hpp'),
    path('laporan/velocity/', views.laporan_velocity, name='laporan_velocity'),
```

(`laporan_hub` view is added in Task 8; add the URL now — Django only imports lazily at request time, and Task 8 lands before any run.)

- [ ] **Step 3: Verify EB-tree node shape**

Run: `python manage.py shell -c "from apps.purchase.views import _get_eb_tree; from django.contrib.auth import get_user_model; u=get_user_model().objects.first(); import json; print([{k:n.get(k) for k in ('id','nama','lv1_id')} for n in _get_eb_tree(u)][:3])"`
Expected: prints node dicts. Confirm the lv1 primary-key key name; if it is not `id`, update `_report_eb_ids` accordingly before proceeding.

- [ ] **Step 4: Commit**

```bash
git add apps/inventory/views.py apps/inventory/urls.py
git commit -m "feat(inventory): view+url laporan valuasi/hpp/velocity + export xlsx/pdf (Fase 8)"
```

---

## Task 6: Inventory report templates

**Files:**
- Create: `templates/inventory/_laporan_print.html`
- Create: `templates/inventory/laporan_valuasi.html`
- Create: `templates/inventory/laporan_hpp.html`
- Create: `templates/inventory/laporan_velocity.html`

- [ ] **Step 1: Shared print template**

Create `templates/inventory/_laporan_print.html`:

```html
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 12px; margin: 24px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    .meta { color: #555; margin-bottom: 12px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #999; padding: 4px 6px; text-align: left; }
    th { background: #D9E1F2; }
    td.num, th.num { text-align: right; }
    tfoot td { font-weight: bold; }
    @media print { .noprint { display: none; } }
  </style>
</head>
<body>
  <button class="noprint" onclick="window.print()">Cetak / Simpan PDF</button>
  <h1>{{ title }}</h1>
  <div class="meta">Dibuat: {{ generated_at|date:"d M Y H:i" }}</div>
  <table>
    <thead><tr>{% for c in columns %}<th>{{ c }}</th>{% endfor %}</tr></thead>
    <tbody>
      {% for row in rows %}
      <tr>{% for cell in row %}<td>{{ cell }}</td>{% endfor %}</tr>
      {% empty %}
      <tr><td colspan="{{ columns|length }}">Tidak ada data.</td></tr>
      {% endfor %}
    </tbody>
    {% if total_label %}
    <tfoot><tr><td colspan="{{ columns|length|add:'-1' }}">{{ total_label }}</td>
      <td class="num">{{ total_value|floatformat:2 }}</td></tr></tfoot>
    {% endif %}
  </table>
</body>
</html>
```

- [ ] **Step 2: Valuation template**

Create `templates/inventory/laporan_valuasi.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <div class="ni-page__actions">
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=csv">Excel</a>
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=pdf" target="_blank">PDF</a>
    </div>
  </div>

  <form method="get" class="ni-filter-bar">
    <label>Tipe
      <select name="tipe" class="ni-input">
        <option value="">Semua</option>
        {% for code, label in items_tipe %}
          <option value="{{ code }}" {% if tipe_filter == code %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Gudang
      <select name="warehouse" class="ni-input">
        <option value="">Semua</option>
        {% for w in warehouses %}
          <option value="{{ w.pk }}" {% if wh_filter == w.pk|stringformat:'s' %}selected{% endif %}>{{ w.kode }} — {{ w.nama }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Per Tanggal
      <input type="date" name="as_of" value="{{ as_of }}" class="ni-input">
    </label>
    <button type="submit" class="ni-btn ni-btn--primary">Terapkan</button>
  </form>

  <table class="ni-table">
    <thead>
      <tr><th>Kategori</th><th>Item</th><th>Nama</th><th>Satuan</th>
          <th class="ni-text-right">On-hand</th><th class="ni-text-right">Biaya/Unit</th>
          <th class="ni-text-right">Nilai</th></tr>
    </thead>
    <tbody>
      {% for r in data.rows %}
      <tr>
        <td>{{ r.kategori }}</td><td>{{ r.item_id }}</td><td>{{ r.nama }}</td><td>{{ r.satuan }}</td>
        <td class="ni-text-right">{{ r.on_hand_qty|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.unit_cost_avg|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.total_value|floatformat:2 }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="7">Tidak ada data persediaan pada filter ini.</td></tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr><td colspan="6" class="ni-text-right"><strong>Total Nilai</strong></td>
          <td class="ni-text-right"><strong>{{ data.grand_total_value|floatformat:2 }}</strong></td></tr>
    </tfoot>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 3: HPP template**

Create `templates/inventory/laporan_hpp.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <div class="ni-page__actions">
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=csv">Excel</a>
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=pdf" target="_blank">PDF</a>
    </div>
  </div>

  <form method="get" class="ni-filter-bar">
    <label>Dari <input type="date" name="tanggal_dari" value="{{ tanggal_dari }}" class="ni-input"></label>
    <label>Sampai <input type="date" name="tanggal_sampai" value="{{ tanggal_sampai }}" class="ni-input"></label>
    <label>Gudang
      <select name="warehouse" class="ni-input">
        <option value="">Semua</option>
        {% for w in warehouses %}
          <option value="{{ w.pk }}" {% if wh_filter == w.pk|stringformat:'s' %}selected{% endif %}>{{ w.kode }} — {{ w.nama }}</option>
        {% endfor %}
      </select>
    </label>
    <button type="submit" class="ni-btn ni-btn--primary">Terapkan</button>
  </form>

  <table class="ni-table">
    <thead>
      <tr><th>Kategori</th><th>Item</th><th>Nama</th><th>Satuan</th>
          <th class="ni-text-right">Qty Terjual</th><th class="ni-text-right">Total HPP</th></tr>
    </thead>
    <tbody>
      {% for r in data.rows %}
      <tr>
        <td>{{ r.kategori }}</td><td>{{ r.item_id }}</td><td>{{ r.nama }}</td><td>{{ r.satuan }}</td>
        <td class="ni-text-right">{{ r.qty_terjual|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.total_hpp|floatformat:2 }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="6">Tidak ada penjualan pada rentang ini.</td></tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr><td colspan="5" class="ni-text-right"><strong>Total HPP</strong></td>
          <td class="ni-text-right"><strong>{{ data.grand_total_hpp|floatformat:2 }}</strong></td></tr>
    </tfoot>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Velocity template**

Create `templates/inventory/laporan_velocity.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <div class="ni-page__actions">
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=csv">Excel</a>
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=pdf" target="_blank">PDF</a>
    </div>
  </div>

  <form method="get" class="ni-filter-bar">
    <label>Dari <input type="date" name="tanggal_dari" value="{{ tanggal_dari }}" class="ni-input"></label>
    <label>Sampai <input type="date" name="tanggal_sampai" value="{{ tanggal_sampai }}" class="ni-input"></label>
    <label>Tag
      <select name="velocity" class="ni-input">
        <option value="">Semua</option>
        {% for code, label in velocity_choices %}
          <option value="{{ code }}" {% if velocity_filter == code %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Gudang
      <select name="warehouse" class="ni-input">
        <option value="">Semua</option>
        {% for w in warehouses %}
          <option value="{{ w.pk }}" {% if wh_filter == w.pk|stringformat:'s' %}selected{% endif %}>{{ w.kode }} — {{ w.nama }}</option>
        {% endfor %}
      </select>
    </label>
    <button type="submit" class="ni-btn ni-btn--primary">Terapkan</button>
  </form>

  <table class="ni-table">
    <thead>
      <tr><th>Item</th><th>Nama</th><th>Kategori</th><th>Tag</th>
          <th class="ni-text-right">Qty Keluar</th><th class="ni-text-right">Gerakan</th>
          <th class="ni-text-right">Hari Idle</th><th class="ni-text-right">On-hand</th><th>Catatan</th></tr>
    </thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>{{ r.item_id }}</td><td>{{ r.nama }}</td><td>{{ r.kategori }}</td><td>{{ r.velocity_label }}</td>
        <td class="ni-text-right">{{ r.qty_keluar|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.jumlah_gerakan }}</td>
        <td class="ni-text-right">{% if r.hari_sejak_keluar_terakhir is not None %}{{ r.hari_sejak_keluar_terakhir }}{% else %}—{% endif %}</td>
        <td class="ni-text-right">{{ r.on_hand|floatformat:2 }}</td>
        <td>{% if r.mismatch_flag %}<span class="ni-badge ni-badge--warning">Tag ≠ realita</span>{% endif %}</td>
      </tr>
      {% empty %}
      <tr><td colspan="9">Tidak ada data.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 5: Smoke-check the pages render**

Run: `python manage.py check`
Expected: `System check identified no issues`.
(Full page render is verified in Task 9 via the test client.)

- [ ] **Step 6: Commit**

```bash
git add templates/inventory/_laporan_print.html templates/inventory/laporan_valuasi.html templates/inventory/laporan_hpp.html templates/inventory/laporan_velocity.html
git commit -m "feat(inventory): template laporan valuasi/hpp/velocity + print (Fase 8)"
```

---

## Task 7: Asset register view + URL + template

**Files:**
- Modify: `apps/aset_tetap/views.py`
- Modify: `apps/aset_tetap/urls.py`
- Create: `templates/aset_tetap/laporan_register.html`

- [ ] **Step 1: Add the view**

Append to `apps/aset_tetap/views.py` (add imports `from django.http import HttpResponse`, `from django.utils import timezone`, `from apps.purchase.views import _get_eb_tree, _resolve_eb_lv1_ids` if not present; and `from . import reports`):

```python
@login_required
def laporan_register(request):
    from . import reports
    from apps.purchase.models import KategoriItem
    from apps.aset_tetap.models import LokasiAset
    from apps.entitas_bisnis.models import EntitasBisnisLv3

    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    if eb_filter_list:
        eb_ids = _resolve_eb_lv1_ids(eb_filter_list, request.user)
    else:
        eb_ids = {n['id'] for n in _get_eb_tree(request.user) if n.get('id')}

    kategori_id = request.GET.get('kategori') or None
    lokasi_id = request.GET.get('lokasi') or None
    departemen_id = request.GET.get('departemen') or None
    pic = request.GET.get('pic') or None
    status = request.GET.get('status') or None
    group_by = request.GET.get('group_by') or 'kategori'

    data = reports.asset_register(
        eb_ids, kategori_id=kategori_id, lokasi_id=lokasi_id,
        departemen_id=departemen_id, pic=pic, status=status, group_by=group_by)

    if request.GET.get('export') == 'csv':
        return _export_register_xlsx(data)
    if request.GET.get('export') == 'pdf':
        return render(request, 'inventory/_laporan_print.html', {
            'title': 'Asset Register', 'generated_at': timezone.now(),
            'columns': ['Kode', 'Nama', 'Kategori', 'Lokasi', 'Departemen', 'PIC',
                        'Perolehan', 'Akumulasi', 'Nilai Buku', 'Status'],
            'rows': [[r['kode'], r['nama'], r['kategori'], r['lokasi'], r['departemen'],
                      r['pic'], r['harga_perolehan'], r['akumulasi_penyusutan'],
                      r['nilai_buku'], r['status']] for r in data['rows']],
            'total_label': 'Total Nilai Buku', 'total_value': data['grand_total']['nilai_buku'],
        })

    return render(request, 'aset_tetap/laporan_register.html', {
        'title': 'Asset Register', 'data': data,
        'kategori_list': KategoriItem.objects.order_by('nama'),
        'lokasi_list': LokasiAset.objects.order_by('nama'),
        'departemen_list': EntitasBisnisLv3.objects.order_by('nama'),
        'status_choices': [('aktif', 'Aktif'), ('dilepas', 'Dilepas')],
        'group_choices': [('kategori', 'Kategori'), ('lokasi', 'Lokasi'), ('departemen', 'Departemen')],
        'eb_tree': _get_eb_tree(request.user), 'eb_filter_list': eb_filter_list,
        'kategori_filter': kategori_id or '', 'lokasi_filter': lokasi_id or '',
        'departemen_filter': departemen_id or '', 'pic_filter': pic or '',
        'status_filter': status or '', 'group_by': group_by,
    })


def _export_register_xlsx(data):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Asset Register'
    headers = ['Kode', 'Nama', 'Kategori', 'Lokasi', 'Departemen', 'PIC',
               'Tgl Perolehan', 'Perolehan', 'Akumulasi', 'Nilai Buku', 'Status', 'Kondisi']
    numeric = {8, 9, 10}
    hf = Font(bold=True)
    fill = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hf
        c.fill = fill
    for rnum, r in enumerate(data['rows'], 2):
        vals = [r['kode'], r['nama'], r['kategori'], r['lokasi'], r['departemen'], r['pic'],
                str(r['tanggal_perolehan']), float(r['harga_perolehan']),
                float(r['akumulasi_penyusutan']), float(r['nilai_buku']), r['status'], r['kondisi']]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=rnum, column=col, value=val)
            if col in numeric:
                c.alignment = Alignment(horizontal='right')
                c.number_format = '#,##0.00'
    for i in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 18
    resp = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="asset_register.xlsx"'
    wb.save(resp)
    return resp
```

- [ ] **Step 2: Wire URL**

In `apps/aset_tetap/urls.py`, add to `urlpatterns` (near `laporan-penyusutan/`):

```python
    path('laporan-register/', views.laporan_register, name='laporan_register'),
```

- [ ] **Step 3: Create template**

Create `templates/aset_tetap/laporan_register.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <div class="ni-page__actions">
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=csv">Excel</a>
      <a class="ni-btn ni-btn--secondary" href="?{{ request.GET.urlencode }}&export=pdf" target="_blank">PDF</a>
    </div>
  </div>

  <form method="get" class="ni-filter-bar">
    <label>Kategori
      <select name="kategori" class="ni-input"><option value="">Semua</option>
        {% for k in kategori_list %}<option value="{{ k.pk }}" {% if kategori_filter == k.pk|stringformat:'s' %}selected{% endif %}>{{ k.nama }}</option>{% endfor %}
      </select></label>
    <label>Lokasi
      <select name="lokasi" class="ni-input"><option value="">Semua</option>
        {% for l in lokasi_list %}<option value="{{ l.pk }}" {% if lokasi_filter == l.pk|stringformat:'s' %}selected{% endif %}>{{ l.nama }}</option>{% endfor %}
      </select></label>
    <label>Departemen
      <select name="departemen" class="ni-input"><option value="">Semua</option>
        {% for d in departemen_list %}<option value="{{ d.pk }}" {% if departemen_filter == d.pk|stringformat:'s' %}selected{% endif %}>{{ d.nama }}</option>{% endfor %}
      </select></label>
    <label>Status
      <select name="status" class="ni-input"><option value="">Semua</option>
        {% for code, label in status_choices %}<option value="{{ code }}" {% if status_filter == code %}selected{% endif %}>{{ label }}</option>{% endfor %}
      </select></label>
    <label>Group
      <select name="group_by" class="ni-input">
        {% for code, label in group_choices %}<option value="{{ code }}" {% if group_by == code %}selected{% endif %}>{{ label }}</option>{% endfor %}
      </select></label>
    <label>PIC <input type="text" name="pic" value="{{ pic_filter }}" class="ni-input"></label>
    <button type="submit" class="ni-btn ni-btn--primary">Terapkan</button>
  </form>

  <table class="ni-table">
    <thead>
      <tr><th>Kode</th><th>Nama</th><th>Kategori</th><th>Lokasi</th><th>Departemen</th><th>PIC</th>
          <th>Tgl Perolehan</th><th class="ni-text-right">Perolehan</th>
          <th class="ni-text-right">Akumulasi</th><th class="ni-text-right">Nilai Buku</th>
          <th>Status</th></tr>
    </thead>
    <tbody>
      {% for r in data.rows %}
      <tr>
        <td>{{ r.kode }}</td><td>{{ r.nama }}</td><td>{{ r.kategori }}</td><td>{{ r.lokasi }}</td>
        <td>{{ r.departemen }}</td><td>{{ r.pic }}</td><td>{{ r.tanggal_perolehan|date:"d M Y" }}</td>
        <td class="ni-text-right">{{ r.harga_perolehan|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.akumulasi_penyusutan|floatformat:2 }}</td>
        <td class="ni-text-right">{{ r.nilai_buku|floatformat:2 }}</td>
        <td>{{ r.status }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="11">Tidak ada aset pada filter ini.</td></tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr><td colspan="7" class="ni-text-right"><strong>Grand Total</strong></td>
        <td class="ni-text-right"><strong>{{ data.grand_total.harga_perolehan|floatformat:2 }}</strong></td>
        <td class="ni-text-right"><strong>{{ data.grand_total.akumulasi|floatformat:2 }}</strong></td>
        <td class="ni-text-right"><strong>{{ data.grand_total.nilai_buku|floatformat:2 }}</strong></td>
        <td></td></tr>
    </tfoot>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Verify**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 5: Commit**

```bash
git add apps/aset_tetap/views.py apps/aset_tetap/urls.py templates/aset_tetap/laporan_register.html
git commit -m "feat(aset_tetap): view+url+template asset register + export (Fase 8)"
```

---

## Task 8: Reports hub + menu integration

**Files:**
- Modify: `apps/inventory/views.py` (add `laporan_hub`)
- Create: `templates/inventory/laporan_hub.html`
- Modify: `templates/base.html`

- [ ] **Step 1: Add hub view**

Append to `apps/inventory/views.py`:

```python
@login_required
def laporan_hub(request):
    """Landing page kartu tautan semua laporan Inventory & Aset Tetap."""
    return render(request, 'inventory/laporan_hub.html', {'title': 'Hub Laporan'})
```

- [ ] **Step 2: Create hub template**

Create `templates/inventory/laporan_hub.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header"><h1 class="ni-page__title">{{ title }}</h1></div>

  <h2 class="ni-section-title">Persediaan</h2>
  <div class="ni-card-grid">
    <a class="ni-card" href="{% url 'inventory:laporan_valuasi' %}"><h3>Valuasi Persediaan</h3><p>Nilai stok on-hand dari ledger.</p></a>
    <a class="ni-card" href="{% url 'inventory:laporan_hpp' %}"><h3>Laporan HPP</h3><p>Harga pokok penjualan per periode.</p></a>
    <a class="ni-card" href="{% url 'inventory:laporan_velocity' %}"><h3>Slow / Fast Moving</h3><p>Velocity item + realita gerakan.</p></a>
    <a class="ni-card" href="{% url 'inventory:stock_card' %}"><h3>Kartu Stok</h3><p>Layer & saldo per item.</p></a>
    <a class="ni-card" href="{% url 'inventory:stock_ledger' %}"><h3>Buku Persediaan</h3><p>Semua pergerakan + saldo berjalan.</p></a>
    <a class="ni-card" href="{% url 'inventory:laporan_persediaan' %}"><h3>Laporan Persediaan</h3><p>Ringkasan komprehensif.</p></a>
  </div>

  <h2 class="ni-section-title">Aset Tetap</h2>
  <div class="ni-card-grid">
    <a class="ni-card" href="{% url 'aset_tetap:laporan_register' %}"><h3>Asset Register</h3><p>Daftar aset per kategori/lokasi/departemen.</p></a>
    <a class="ni-card" href="{% url 'aset_tetap:laporan_penyusutan' %}"><h3>Laporan Penyusutan</h3><p>Penyusutan per dimensi.</p></a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Add Inventory menu link**

In `templates/base.html`, in the Inventory submenu (after the `list` link at line ~308-310, before `laporan_persediaan`), add:

```html
          <a href="{% url 'inventory:laporan_hub' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Hub Laporan</span>
          </a>
```

- [ ] **Step 4: Add Aset Tetap menu links**

In `templates/base.html`, in the Aset Tetap submenu (after the `aset_tetap:list` link ~line 376-378), add:

```html
          <a href="{% url 'aset_tetap:laporan_register' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Asset Register</span>
          </a>
          <a href="{% url 'aset_tetap:laporan_penyusutan' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Laporan Penyusutan</span>
          </a>
```

- [ ] **Step 5: Verify**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 6: Commit**

```bash
git add apps/inventory/views.py templates/inventory/laporan_hub.html templates/base.html
git commit -m "feat(inventory): reports hub + integrasi menu Fase 8"
```

---

## Task 9: End-to-end verification

**Files:**
- Create: `apps/inventory/tests_fase8_views.py`

- [ ] **Step 1: Write view smoke tests**

Create `apps/inventory/tests_fase8_views.py`:

```python
"""Smoke tests Fase 8 — halaman laporan merender 200 + export xlsx."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger


class ReportViewSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='u1', password='pw12345', email='u1@example.com')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('5'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)

    def test_hub_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_hub')).status_code, 200)

    def test_valuasi_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_valuasi')).status_code, 200)

    def test_hpp_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_hpp')).status_code, 200)

    def test_velocity_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_velocity')).status_code, 200)

    def test_register_renders(self):
        self.assertEqual(self.client.get(reverse('aset_tetap:laporan_register')).status_code, 200)

    def test_valuasi_xlsx_export(self):
        resp = self.client.get(reverse('inventory:laporan_valuasi'), {'export': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
```

- [ ] **Step 2: Run the full Fase 8 suite**

Run: `python -m pytest apps/inventory/tests_fase8.py apps/inventory/tests_fase8_views.py apps/aset_tetap/tests_fase8_register.py -v`
Expected: all PASS.

- [ ] **Step 3: Run broader regression on touched apps**

Run: `python -m pytest apps/inventory apps/aset_tetap -q`
Expected: all PASS (no regressions from earlier phases).

- [ ] **Step 4: Django system check**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/tests_fase8_views.py
git commit -m "test(inventory): smoke tests view laporan Fase 8"
```

---

## Self-Review Notes (for the executor)

- **Spec coverage:** Valuation (T1), HPP (T2), Slow/Fast Moving (T3), Asset Register (T4), views+export (T5,T7), templates (T6,T7), reports hub + menu (T8), tests throughout + smoke (T9). Existing Stock Card / Inventory Movement / Laporan Penyusutan are surfaced via the hub (T8), matching the "full suite" scope.
- **Data source:** valuation/HPP read `StockMovement`/`StockConsumption` only — no legacy tables (spec §2).
- **No migrations:** confirmed — no model changes anywhere.
- **Known follow-up if EB-tree node key differs:** `_report_eb_ids` and `laporan_register` assume `_get_eb_tree` nodes expose lv1 pk under `'id'`. Task 5 Step 3 verifies this before finalizing; adjust the key if needed (do NOT skip that check).
```
