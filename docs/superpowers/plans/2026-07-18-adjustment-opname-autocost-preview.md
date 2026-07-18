# Adjustment & Opname — Auto-Cost, Entity Picker & Preview — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Beri form `/inventory/adjustment/create/` & `/inventory/opname/create/` harga/unit otomatis (ikut metode costing item), pemilihan entitas hierarkis ala purchase + tanggal default hari ini, dan preview jurnal + mutasi persediaan yang identik dengan posting.

**Architecture:** Tambah helper `current_unit_cost` di ledger; perluas endpoint AJAX `stock_available`; tambah field `eb_hierarki` di dua form (resolve ke FK lv1/lv2/lv3 di `clean()`); dua endpoint preview yang mensimulasikan posting sungguhan via `transaction.atomic()` + rollback; update dua template (dropdown hierarkis, auto-fill JS, modal preview).

**Tech Stack:** Django 5, Python 3, Decimal, django.test.TestCase + Client, vanilla JS + TomSelect-free plain `<select>`.

**Spec:** [docs/superpowers/specs/2026-07-18-adjustment-opname-autocost-preview-design.md](../specs/2026-07-18-adjustment-opname-autocost-preview-design.md)

**Referensi kode kunci:**
- Ledger: [apps/inventory/ledger.py](../../../apps/inventory/ledger.py) — `_candidate_tiers` (baris 60), `get_available_stock` (97), `record_inflow` (106), `consume_stock` set out_movement `unit_cost=avg_cost, qty=-qty` (279).
- Services: [apps/inventory/services.py](../../../apps/inventory/services.py) — `process_adjustment` (70), `process_opname` (151).
- Views: [apps/inventory/views.py](../../../apps/inventory/views.py) — `adjustment_create` (1346), `opname_create` (1396), `stock_available` (1633). Sudah mengimpor `from apps.purchase.views import _get_eb_tree, _resolve_eb_lv1_ids` (baris 21).
- Forms: [apps/inventory/forms.py](../../../apps/inventory/forms.py) — `StockAdjustmentForm` (104), `StockOpnameForm` (156), `_validate_warehouse_scope` (42), `_warehouse_eb_map` (38).
- Purchase EB helper: [apps/purchase/views.py](../../../apps/purchase/views.py) — `_get_eb_dropdown_options(user)` (58) → list `{'value': 'lv1:<pk>'|'lv2:<pk>'|'lv3:<pk>', 'label': ...}`.
- Templates: [templates/inventory/adjustment_form.html](../../../templates/inventory/adjustment_form.html), [templates/inventory/opname_form.html](../../../templates/inventory/opname_form.html), [templates/inventory/_warehouse_scope_js.html](../../../templates/inventory/_warehouse_scope_js.html).
- Test env: `python manage.py test apps.inventory` (Windows PowerShell). Jalankan dari `naveda_integra/`.

**Konvensi commit:** akhiri tiap pesan commit dengan `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Kerja di branch fitur (Task 0).

---

### Task 0: Branch fitur

- [ ] **Step 1: Buat branch**

Run:
```bash
git checkout -b feature/adjustment-opname-autocost-preview
```
Expected: `Switched to a new branch ...`

---

### Task 1: Helper `current_unit_cost` di ledger

Harga acuan per unit dari layer `StockMovement` tersisa, mengikuti metode costing item. FIFO → layer tertua yang akan keluar berikutnya; LIFO → terbaru; average/WMA → rata-rata tertimbang. `None` bila tak ada stok.

**Files:**
- Modify: `apps/inventory/ledger.py` (tambah fungsi baru setelah `get_available_stock`, sekitar baris 104)
- Test: `apps/inventory/tests_autocost_preview.py` (Create)

- [ ] **Step 1: Tulis test yang gagal**

Create `apps/inventory/tests_autocost_preview.py`:
```python
"""Tests: auto unit cost (per metode costing) + preview jurnal & mutasi."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger


class CurrentUnitCostTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.item.coa_account = self.persediaan
        self.item.save()
        # dua layer harga berbeda: 100 (lebih tua), lalu 120 (lebih baru)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('120'), '2026-01-05', 'adjustment_in', warehouse=self.wh)

    def test_fifo_returns_oldest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='fifo')
        self.assertEqual(c, Decimal('100'))

    def test_lifo_returns_newest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='lifo')
        self.assertEqual(c, Decimal('120'))

    def test_average_returns_weighted_average(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='average')
        self.assertEqual(c, Decimal('110'))  # (10*100 + 10*120)/20

    def test_none_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        c = ledger.current_unit_cost(other, self.eb, warehouse=self.wh, metode='fifo')
        self.assertIsNone(c)

    def test_defaults_to_item_method(self):
        self.item.metode_biaya_persediaan = 'lifo'
        self.item.save()
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(c, Decimal('120'))
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `python manage.py test apps.inventory.tests_autocost_preview.CurrentUnitCostTests -v 2`
Expected: FAIL — `AttributeError: module 'apps.inventory.ledger' has no attribute 'current_unit_cost'`.

- [ ] **Step 3: Implementasi `current_unit_cost`**

Di `apps/inventory/ledger.py`, tambahkan tepat setelah `get_available_stock` (setelah baris 103):
```python
def current_unit_cost(item, eb_lv1, eb_lv2=None, eb_lv3=None, *, warehouse=None,
                      metode=None) -> 'Decimal | None':
    """Harga acuan per unit dari layer tersisa, mengikuti metode costing item.

    FIFO  -> unit_cost layer tersisa TERTUA (akan keluar berikutnya).
    LIFO  -> unit_cost layer tersisa TERBARU.
    average / weighted_moving_average -> rata-rata tertimbang layer tersisa.
    Kembalikan None bila tidak ada stok tersisa di scope (item baru / tanpa layer).
    """
    strategy = _normalize_method(metode if metode is not None else item.metode_biaya_persediaan)
    order = 'lifo' if strategy == 'lifo' else 'fifo'
    if strategy == 'average':
        total_qty = Decimal('0')
        total_val = Decimal('0')
        for _lvl, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse):
            for layer in qs:
                total_qty += layer.remaining_qty
                total_val += layer.remaining_qty * layer.unit_cost
        if total_qty <= 0:
            return None
        return (total_val / total_qty).quantize(Decimal('0.0001'))
    # FIFO / LIFO: layer pertama (per urutan) dari tier terdekat yang punya stok
    for _lvl, _name, qs in _candidate_tiers(item, eb_lv1, eb_lv2, eb_lv3, warehouse,
                                            order=order):
        layer = qs.first()
        if layer is not None:
            return layer.unit_cost
    return None
```

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.CurrentUnitCostTests -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/ledger.py apps/inventory/tests_autocost_preview.py
git commit -m "feat(inventory): current_unit_cost helper per metode costing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Perluas endpoint `stock_available` → tambah `unit_cost`

Endpoint sudah mengembalikan `available` (dipakai opname untuk qty_sistem). Tambahkan `unit_cost` (per metode costing) agar form bisa auto-fill harga.

**Files:**
- Modify: `apps/inventory/views.py` — fungsi `stock_available` (baris 1633–1659)
- Test: `apps/inventory/tests_autocost_preview.py` (tambah class)

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `apps/inventory/tests_autocost_preview.py`:
```python
class StockAvailableEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u1', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('4'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def test_returns_available_and_unit_cost(self):
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': self.item.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertEqual(Decimal(data['available']), Decimal('4'))
        self.assertEqual(Decimal(data['unit_cost']), Decimal('100'))

    def test_unit_cost_null_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': other.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertIsNone(data['unit_cost'])
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `python manage.py test apps.inventory.tests_autocost_preview.StockAvailableEndpointTests -v 2`
Expected: FAIL — `KeyError: 'unit_cost'`.

- [ ] **Step 3: Implementasi**

Di `apps/inventory/views.py`, di akhir `stock_available` ganti blok penutup (baris 1658–1659):
```python
    available = ledger.get_available_stock(item, eb, eb_lv2, eb_lv3, warehouse=warehouse)
    return JsonResponse({'available': str(available)})
```
menjadi:
```python
    available = ledger.get_available_stock(item, eb, eb_lv2, eb_lv3, warehouse=warehouse)
    unit_cost = ledger.current_unit_cost(
        item, eb, eb_lv2, eb_lv3, warehouse=warehouse,
        metode=item.metode_biaya_persediaan,
    )
    return JsonResponse({
        'available': str(available),
        'unit_cost': (str(unit_cost) if unit_cost is not None else None),
    })
```

- [ ] **Step 4: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.StockAvailableEndpointTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/views.py apps/inventory/tests_autocost_preview.py
git commit -m "feat(inventory): stock_available juga kembalikan unit_cost per metode

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Field `eb_hierarki` + resolusi FK + tanggal default (kedua form)

Ganti tiga select entitas dengan satu `eb_hierarki`; `clean()` meresolusi ke `entitas_bisnis`/`_lv2`/`_lv3`. Model tidak berubah.

**Files:**
- Modify: `apps/inventory/forms.py` — tambah helper `_eb_hierarki_choices` + `_resolve_eb_hierarki`; ubah `StockAdjustmentForm` (104–129) & `StockOpnameForm` (156–181)
- Test: `apps/inventory/tests_autocost_preview.py` (tambah class)

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `apps/inventory/tests_autocost_preview.py`:
```python
from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3
from apps.inventory.forms import StockAdjustmentForm


class EbHierarkiResolveTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(nama='Divisi A', entitas_bisnis=self.eb)
        self.lv3 = EntitasBisnisLv3.objects.create(nama='Sub A1', parent_lv2=self.lv2)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')

    def _data(self, eb_hierarki):
        return {
            'tanggal': '2026-07-18', 'eb_hierarki': eb_hierarki,
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
        }

    def test_lv3_resolves_all_three_fks(self):
        form = StockAdjustmentForm(data=self._data(f'lv3:{self.lv3.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv2'], self.lv2)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv3'], self.lv3)

    def test_lv1_resolves_only_lv1(self):
        form = StockAdjustmentForm(data=self._data(f'lv1:{self.eb.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv2'])
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv3'])

    def test_default_tanggal_is_today(self):
        from django.utils import timezone
        form = StockAdjustmentForm()
        self.assertEqual(form.fields['tanggal'].initial, timezone.localdate())
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `python manage.py test apps.inventory.tests_autocost_preview.EbHierarkiResolveTests -v 2`
Expected: FAIL — `KeyError: 'eb_hierarki'` / field tidak ada.

- [ ] **Step 3: Tambah helper resolusi di `forms.py`**

Di `apps/inventory/forms.py`, di bawah import (setelah baris 14) tambahkan:
```python
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3


def _eb_hierarki_choices():
    """[(value, label)] semua EntitasBisnis aktif (lv1/lv2/lv3) untuk validasi field.

    Label indentasi untuk fallback; template merender opsi dari eb_options_json
    (scoped user) — choices di sini hanya superset untuk validasi nilai.
    """
    choices = [('', '— Pilih Entitas Bisnis —')]
    lv1s = list(EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'))
    lv2s = list(EntitasBisnisLv2.objects.filter(status_aktif=True)
                .select_related('entitas_bisnis').order_by('nama'))
    lv3s = list(EntitasBisnisLv3.objects.filter(status_aktif=True)
                .select_related('parent_lv2').order_by('nama'))
    lv2_by_lv1 = {}
    for lv2 in lv2s:
        lv2_by_lv1.setdefault(lv2.entitas_bisnis_id, []).append(lv2)
    lv3_by_lv2 = {}
    for lv3 in lv3s:
        lv3_by_lv2.setdefault(lv3.parent_lv2_id, []).append(lv3)
    for eb in lv1s:
        choices.append((f'lv1:{eb.pk}', eb.nama))
        for lv2 in lv2_by_lv1.get(eb.pk, []):
            choices.append((f'lv2:{lv2.pk}', f'  ↳ {lv2.nama}'))
            for lv3 in lv3_by_lv2.get(lv2.pk, []):
                choices.append((f'lv3:{lv3.pk}', f'    ↳ {lv3.nama}'))
    return choices


def _resolve_eb_hierarki(value, cleaned_data, form):
    """Isi entitas_bisnis/_lv2/_lv3 di cleaned_data dari 'lvN:<pk>'. Error → add_error."""
    cleaned_data['entitas_bisnis'] = None
    cleaned_data['entitas_bisnis_lv2'] = None
    cleaned_data['entitas_bisnis_lv3'] = None
    if not value:
        form.add_error('eb_hierarki', 'Entitas bisnis wajib dipilih.')
        return
    try:
        level, pk = value.split(':')
        pk = int(pk)
    except (ValueError, AttributeError):
        form.add_error('eb_hierarki', 'Nilai entitas bisnis tidak valid.')
        return
    if level == 'lv1':
        cleaned_data['entitas_bisnis'] = EntitasBisnis.objects.filter(pk=pk).first()
    elif level == 'lv2':
        lv2 = EntitasBisnisLv2.objects.select_related('entitas_bisnis').filter(pk=pk).first()
        if lv2:
            cleaned_data['entitas_bisnis'] = lv2.entitas_bisnis
            cleaned_data['entitas_bisnis_lv2'] = lv2
    elif level == 'lv3':
        lv3 = (EntitasBisnisLv3.objects
               .select_related('parent_lv2__entitas_bisnis').filter(pk=pk).first())
        if lv3:
            cleaned_data['entitas_bisnis'] = lv3.parent_lv2.entitas_bisnis
            cleaned_data['entitas_bisnis_lv2'] = lv3.parent_lv2
            cleaned_data['entitas_bisnis_lv3'] = lv3
    if cleaned_data['entitas_bisnis'] is None:
        form.add_error('eb_hierarki', 'Entitas bisnis tidak ditemukan.')
```

- [ ] **Step 4: Ubah `StockAdjustmentForm`**

Ganti seluruh class `StockAdjustmentForm` (baris 104–129) dengan:
```python
class StockAdjustmentForm(forms.ModelForm):
    eb_hierarki = forms.ChoiceField(
        label='Entitas Bisnis',
        widget=forms.Select(attrs={'class': 'ni-input', 'id': 'id_eb_hierarki'}),
    )

    class Meta:
        model = StockAdjustment
        fields = ('tanggal', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_eb_hierarki'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['eb_hierarki'].choices = _eb_hierarki_choices()
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()
        if not self.is_bound and not self.fields['tanggal'].initial:
            self.fields['tanggal'].initial = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        _resolve_eb_hierarki(cleaned_data.get('eb_hierarki'), cleaned_data, self)
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.entitas_bisnis = self.cleaned_data['entitas_bisnis']
        obj.entitas_bisnis_lv2 = self.cleaned_data['entitas_bisnis_lv2']
        obj.entitas_bisnis_lv3 = self.cleaned_data['entitas_bisnis_lv3']
        if commit:
            obj.save()
        return obj
```

- [ ] **Step 5: Ubah `StockOpnameForm` dengan pola sama**

Ganti seluruh class `StockOpnameForm` (baris 156–181) dengan:
```python
class StockOpnameForm(forms.ModelForm):
    eb_hierarki = forms.ChoiceField(
        label='Entitas Bisnis',
        widget=forms.Select(attrs={'class': 'ni-input', 'id': 'id_eb_hierarki'}),
    )

    class Meta:
        model = StockOpname
        fields = ('tanggal', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_eb_hierarki'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['eb_hierarki'].choices = _eb_hierarki_choices()
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()
        if not self.is_bound and not self.fields['tanggal'].initial:
            self.fields['tanggal'].initial = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()
        _resolve_eb_hierarki(cleaned_data.get('eb_hierarki'), cleaned_data, self)
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.entitas_bisnis = self.cleaned_data['entitas_bisnis']
        obj.entitas_bisnis_lv2 = self.cleaned_data['entitas_bisnis_lv2']
        obj.entitas_bisnis_lv3 = self.cleaned_data['entitas_bisnis_lv3']
        if commit:
            obj.save()
        return obj
```

- [ ] **Step 6: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.EbHierarkiResolveTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/forms.py apps/inventory/tests_autocost_preview.py
git commit -m "feat(inventory): eb_hierarki tunggal + tanggal default untuk adjustment/opname form

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Endpoint preview `adjustment_preview` & `opname_preview`

Simulasi posting sungguhan di dalam `transaction.atomic()` lalu rollback; kembalikan jurnal + mutasi persediaan sebagai JSON.

**Files:**
- Modify: `apps/inventory/views.py` — tambah 2 view + helper `_build_preview_payload`
- Modify: `apps/inventory/urls.py` — 2 path baru
- Test: `apps/inventory/tests_autocost_preview.py` (tambah class)

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan ke `apps/inventory/tests_autocost_preview.py`:
```python
class AdjustmentPreviewEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u2', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def _post(self, qty):
        return self.client.post('/inventory/adjustment/preview/', {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty': qty, 'items-0-unit_cost': '100',
        })

    def test_preview_increase_returns_balanced_journal_and_mutation(self):
        data = self._post('5')
        self.assertTrue(data.status_code == 200)
        j = data.json()
        self.assertTrue(j['ok'])
        self.assertTrue(j['balance'])
        self.assertEqual(Decimal(j['total_debit']), Decimal(j['total_kredit']))
        self.assertEqual(Decimal(j['total_debit']), Decimal('500'))  # 5 * 100
        mut = j['mutasi'][0]
        self.assertEqual(mut['movement_type'], 'adjustment_in')
        self.assertEqual(Decimal(mut['stok_sebelum']), Decimal('10'))
        self.assertEqual(Decimal(mut['stok_sesudah']), Decimal('15'))

    def test_preview_does_not_persist(self):
        from apps.inventory.models import StockAdjustment, StockMovement
        before_adj = StockAdjustment.objects.count()
        before_mv = StockMovement.objects.count()
        self._post('5')
        self.assertEqual(StockAdjustment.objects.count(), before_adj)
        self.assertEqual(StockMovement.objects.count(), before_mv)

    def test_preview_decrease_fifo_cost_exact(self):
        # tambah layer kedua lebih mahal; turun 12 → 10*100 + 2*120 = 1240
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('120'), '2026-01-05', 'adjustment_in', warehouse=self.wh)
        data = self._post('-12')
        j = data.json()
        self.assertEqual(Decimal(j['total_debit']), Decimal('1240'))
        self.assertEqual(j['mutasi'][0]['movement_type'], 'adjustment_out')
```

- [ ] **Step 2: Jalankan test — pastikan gagal**

Run: `python manage.py test apps.inventory.tests_autocost_preview.AdjustmentPreviewEndpointTests -v 2`
Expected: FAIL — 404 (URL belum ada).

- [ ] **Step 3: Tambah helper + view preview di `views.py`**

Di `apps/inventory/views.py`, tambahkan import service preview di blok `from .services import (...)` (baris 34–39): tambah `process_adjustment, process_opname` sudah ada. Tambahkan fungsi baru setelah `stock_available` (setelah baris 1659):
```python
class _PreviewDone(Exception):
    """Sentinel untuk keluar dari atomic block preview membawa payload."""
    def __init__(self, payload):
        self.payload = payload


def _serialize_journal(header):
    lines, total_d, total_k = [], Decimal('0'), Decimal('0')
    if header is not None:
        for det in header.details.select_related('akun').all():
            lines.append({
                'akun': f'{det.akun.kode_akun} {det.akun.nama}',
                'debit': str(det.debit), 'kredit': str(det.kredit),
            })
            total_d += det.debit
            total_k += det.kredit
    return lines, total_d, total_k


def _mutation_row(item, movement, stok_sebelum, stok_sesudah):
    if movement is None:
        return {'item': item.item_id, 'movement_type': '-', 'delta': '0',
                'stok_sebelum': str(stok_sebelum), 'stok_sesudah': str(stok_sebelum),
                'unit_cost': '0', 'nilai': '0', 'catatan': 'tidak ada mutasi'}
    qty = movement.qty
    # outflow: qty negatif & qty!=0 → nilai = |qty|*unit_cost; bulk outflow qty==0 → unit_cost
    if qty and qty != 0:
        nilai = abs(qty) * movement.unit_cost
    else:
        nilai = movement.unit_cost
    return {'item': item.item_id, 'movement_type': movement.movement_type,
            'delta': str(qty), 'stok_sebelum': str(stok_sebelum),
            'stok_sesudah': str(stok_sesudah), 'unit_cost': str(movement.unit_cost),
            'nilai': str(nilai)}


@login_required
def adjustment_preview(request: HttpRequest) -> JsonResponse:
    """Simulasi posting adjustment (atomic + rollback) → jurnal + mutasi persediaan."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'errors': {'__all__': 'POST diperlukan.'}}, status=405)
    form = StockAdjustmentForm(request.POST)
    formset = StockAdjustmentItemFormSet(request.POST)
    if not (form.is_valid() and formset.is_valid()):
        errors = {**form.errors, 'formset': formset.errors}
        return JsonResponse({'ok': False, 'errors': errors}, status=200)
    try:
        with transaction.atomic():
            adj = form.save()
            formset.instance = adj
            formset.save()
            items = list(adj.items.select_related('item').all())
            before = {d.pk: ledger.get_available_stock(
                d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2,
                adj.entitas_bisnis_lv3, warehouse=adj.warehouse) for d in items}
            header = process_adjustment(adj)
            lines, td, tk = _serialize_journal(header)
            mutasi = []
            for d in adj.items.select_related('item', 'movement').all():
                after = ledger.get_available_stock(
                    d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2,
                    adj.entitas_bisnis_lv3, warehouse=adj.warehouse)
                mutasi.append(_mutation_row(d.item, d.movement, before[d.pk], after))
            raise _PreviewDone({
                'ok': True, 'balance': td == tk,
                'jurnal': lines, 'total_debit': str(td), 'total_kredit': str(tk),
                'mutasi': mutasi,
            })
    except _PreviewDone as done:
        return JsonResponse(done.payload)
    except ValueError as e:
        return JsonResponse({'ok': False, 'errors': {'__all__': str(e)}}, status=200)


@login_required
def opname_preview(request: HttpRequest) -> JsonResponse:
    """Simulasi posting opname (atomic + rollback) → jurnal + mutasi persediaan."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'errors': {'__all__': 'POST diperlukan.'}}, status=405)
    form = StockOpnameForm(request.POST)
    formset = StockOpnameItemFormSet(request.POST)
    if not (form.is_valid() and formset.is_valid()):
        errors = {**form.errors, 'formset': formset.errors}
        return JsonResponse({'ok': False, 'errors': errors}, status=200)
    try:
        with transaction.atomic():
            opn = form.save()
            formset.instance = opn
            formset.save()
            items = list(opn.items.select_related('item').all())
            before = {d.pk: ledger.get_available_stock(
                d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2,
                opn.entitas_bisnis_lv3, warehouse=opn.warehouse) for d in items}
            header = process_opname(opn)
            lines, td, tk = _serialize_journal(header)
            mutasi = []
            for d in opn.items.select_related('item', 'movement').all():
                after = ledger.get_available_stock(
                    d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2,
                    opn.entitas_bisnis_lv3, warehouse=opn.warehouse)
                mutasi.append(_mutation_row(d.item, d.movement, before[d.pk], after))
            raise _PreviewDone({
                'ok': True, 'balance': td == tk,
                'jurnal': lines, 'total_debit': str(td), 'total_kredit': str(tk),
                'mutasi': mutasi,
            })
    except _PreviewDone as done:
        return JsonResponse(done.payload)
    except ValueError as e:
        return JsonResponse({'ok': False, 'errors': {'__all__': str(e)}}, status=200)
```
Pastikan `from . import ledger` tersedia di scope fungsi — `stock_available` sudah `from . import ledger` di dalam fungsi; tambahkan `from . import ledger` di dalam kedua fungsi preview (baris pertama tiap fungsi) untuk konsistensi, atau import modul-level. Gunakan import di dalam fungsi agar aman:
tambahkan sebagai baris pertama di dalam `adjustment_preview` dan `opname_preview`:
```python
    from . import ledger
```

- [ ] **Step 4: Daftarkan URL**

Di `apps/inventory/urls.py`, setelah baris 25 (`adjustment/<int:pk>/delete/`) tambahkan:
```python
    path('adjustment/preview/', views.adjustment_preview, name='adjustment_preview'),
```
dan setelah baris 28 (`opname/<int:pk>/delete/`) tambahkan:
```python
    path('opname/preview/', views.opname_preview, name='opname_preview'),
```

- [ ] **Step 5: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.AdjustmentPreviewEndpointTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/inventory/views.py apps/inventory/urls.py apps/inventory/tests_autocost_preview.py
git commit -m "feat(inventory): endpoint preview jurnal & mutasi (atomic+rollback) adjustment/opname

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Opname preview test + parity preview==posting

Pastikan opname preview bekerja & preview identik dengan angka yang benar-benar diposting.

**Files:**
- Test: `apps/inventory/tests_autocost_preview.py` (tambah class)

- [ ] **Step 1: Tulis test**

Tambahkan:
```python
class PreviewEqualsPostingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u3', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def test_opname_preview_and_real_posting_match(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        payload = {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty_sistem': '20',
            'items-0-qty_fisik': '18', 'items-0-unit_cost': '100',
        }
        prev = self.client.post('/inventory/opname/preview/', payload).json()
        # posting sungguhan
        opn = StockOpname.objects.create(tanggal='2026-07-18', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=opn, item=self.item,
                                       qty_sistem=Decimal('20'), qty_fisik=Decimal('18'),
                                       unit_cost=Decimal('100'))
        header = process_opname(opn)
        real_debit = sum(d.debit for d in header.details.all())
        self.assertEqual(Decimal(prev['total_debit']), real_debit)
        self.assertEqual(Decimal(prev['total_debit']), Decimal('200'))  # 2 * 100
        self.assertEqual(prev['mutasi'][0]['movement_type'], 'opname_out')
        self.assertEqual(Decimal(prev['mutasi'][0]['stok_sesudah']), Decimal('18'))
```

- [ ] **Step 2: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.PreviewEqualsPostingTests -v 2`
Expected: PASS (1 test).

- [ ] **Step 3: Commit**

```bash
git add apps/inventory/tests_autocost_preview.py
git commit -m "test(inventory): opname preview == posting (jurnal & mutasi)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Template adjustment — dropdown hierarkis, auto-cost, warehouse scope, modal preview

**Files:**
- Modify: `apps/inventory/views.py` — `adjustment_create` (1346–1366) tambah `eb_options_json` ke context
- Create: `templates/inventory/_eb_hierarki_scope_js.html` (warehouse filter via lv1 hasil parse eb_hierarki)
- Modify: `templates/inventory/adjustment_form.html`

- [ ] **Step 1: Tambah context `eb_options_json` di `adjustment_create`**

Di `apps/inventory/views.py`, di `adjustment_create`, ubah kedua `render(...)` (GET & POST-invalid) agar mengirim eb_options. Ganti isi fungsi `adjustment_create` (baris 1346–1366) menjadi:
```python
@login_required
def adjustment_create(request: HttpRequest) -> HttpResponse:
    """Create a stock adjustment (header + items) and post it immediately."""
    from apps.purchase.views import _get_eb_dropdown_options
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    adj = form.save()
                    formset.instance = adj
                    formset.save()
                    header = process_adjustment(adj)
            except ValueError as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f'Adjustment {adj.nomor} diposting. Jurnal {header.nomor_transaksi}.')
                return redirect('inventory:adjustment_list')
    else:
        form = StockAdjustmentForm()
        formset = StockAdjustmentItemFormSet()
    return render(request, 'inventory/adjustment_form.html', {
        'form': form, 'formset': formset,
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
    })
```

- [ ] **Step 2: Buat partial warehouse-scope berbasis eb_hierarki**

Create `templates/inventory/_eb_hierarki_scope_js.html`:
```html
{% comment %}
Filter opsi gudang mengikuti lv1 pemilik dari eb_hierarki terpilih.
eb_hierarki bernilai lv1:<pk>/lv2:<pk>/lv3:<pk>; lv1 diturunkan dengan menelusuri
EB_OPTIONS (lv1 selalu muncul sebelum anak lv2/lv3-nya) — sama seperti purchase.
{% endcomment %}
<script>
(function () {
  var EB_OPTIONS = {{ eb_options_json|default:"[]"|safe }};
  function getEBLv1Id(ebValue) {
    if (!ebValue) return '';
    if (ebValue.indexOf('lv1:') === 0) return ebValue.split(':')[1];
    var lastLv1 = '';
    for (var i = 0; i < EB_OPTIONS.length; i++) {
      if (EB_OPTIONS[i].value.indexOf('lv1:') === 0) lastLv1 = EB_OPTIONS[i].value.split(':')[1];
      if (EB_OPTIONS[i].value === ebValue) return lastLv1;
    }
    return '';
  }
  function applyFilter(whSelect, ebSelect) {
    var lv1 = getEBLv1Id(ebSelect.value);
    Array.prototype.forEach.call(whSelect.options, function (opt) {
      var show = !opt.value || !lv1 || opt.getAttribute('data-eb') === lv1;
      opt.hidden = !show; opt.disabled = !show;
    });
    var cur = whSelect.selectedOptions[0];
    if (cur && cur.hidden) whSelect.value = '';
  }
  document.querySelectorAll('select[data-eb-filter]').forEach(function (whSelect) {
    var ebSelect = document.getElementById(whSelect.getAttribute('data-eb-filter'));
    if (!ebSelect) return;
    ebSelect.addEventListener('change', function () { applyFilter(whSelect, ebSelect); });
    applyFilter(whSelect, ebSelect);
  });
  window.__getEBLv1Id = getEBLv1Id;  // dipakai auto-cost JS
})();
</script>
```

- [ ] **Step 3: Update `adjustment_form.html` — dropdown hierarkis + modal + auto-cost**

Di `templates/inventory/adjustment_form.html`:

(a) Ganti blok entitas (baris 26–53: dua `ni-form-row` yang memuat entitas_bisnis, entitas_bisnis_lv2/lv3) menjadi satu baris — ganti dari baris 20–53 (`<div class="ni-form-row">` pertama sampai penutup row kedua) dengan:
```html
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.tanggal.label }}</label>
          {{ form.tanggal }}
          {% if form.tanggal.errors %}<div class="ni-form-error">{{ form.tanggal.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.eb_hierarki.label }}</label>
          {{ form.eb_hierarki }}
          {% if form.eb_hierarki.errors %}<div class="ni-form-error">{{ form.eb_hierarki.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.warehouse.label }}</label>
          {{ form.warehouse }}
          {% if form.warehouse.errors %}<div class="ni-form-error">{{ form.warehouse.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.akun_selisih.label }}</label>
          {{ form.akun_selisih }}
          {% if form.akun_selisih.errors %}<div class="ni-form-error">{{ form.akun_selisih.errors }}</div>{% endif %}
        </div>
      </div>
```

(b) Pada tombol aksi (baris 108–114 `ni-btn-row`), sisipkan tombol preview sebelum submit:
```html
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="button" class="ni-btn ni-btn--secondary" onclick="openInvPreview()">
          <i data-lucide="eye" style="width:14px;height:14px"></i> Preview Jurnal &amp; Mutasi
        </button>
        <button type="submit" class="ni-btn ni-btn--primary"
                onclick="return confirm('Proses & posting adjustment ini?')">
          <i data-lucide="check" style="width:14px;height:14px"></i> Proses & Posting
        </button>
        <a href="{% url 'inventory:adjustment_list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
```

(c) Sebelum `{% include 'inventory/_item_formset_js.html' %}` (baris 118), sisipkan markup modal + partial scope + auto-cost. Tambahkan:
```html
{% include 'inventory/_inv_preview_modal.html' %}
{% include 'inventory/_eb_hierarki_scope_js.html' %}
{% include 'inventory/_autocost_js.html' with preview_url='inventory:adjustment_preview' cost_field='unit_cost' %}
```
dan hapus baris `{% include 'inventory/_warehouse_scope_js.html' %}` (baris 119) — diganti `_eb_hierarki_scope_js.html`.

- [ ] **Step 4: Buat modal preview partial**

Create `templates/inventory/_inv_preview_modal.html`:
```html
<div class="ni-modal-backdrop" id="invPreviewModal" style="display:none;">
  <div class="ni-modal ni-modal--xl">
    <div class="ni-modal__header">
      <h3 class="ni-modal__title" style="display:flex;align-items:center;gap:8px;">
        <i data-lucide="book-open" style="width:18px;height:18px;"></i> Preview Jurnal &amp; Mutasi Persediaan
      </h3>
      <button type="button" class="ni-modal__close" onclick="closeInvPreview()" aria-label="Tutup">
        <i data-lucide="x" style="width:20px;height:20px"></i>
      </button>
    </div>
    <div class="ni-modal__body" style="overflow-x:auto;">
      <div id="invPreviewError" class="ni-form-error" style="display:none;margin-bottom:12px;"></div>
      <h4 style="margin:0 0 8px;font-size:0.9rem;color:var(--ni-primary);">Jurnal</h4>
      <table class="ni-table" style="margin-bottom:20px;">
        <thead><tr><th>Akun</th><th style="text-align:right">Debit</th><th style="text-align:right">Kredit</th></tr></thead>
        <tbody id="invPreviewJurnalBody"></tbody>
        <tfoot><tr>
          <td style="text-align:right"><strong>Total</strong></td>
          <td style="text-align:right"><strong id="invPreviewTotalD">0</strong></td>
          <td style="text-align:right"><strong id="invPreviewTotalK">0</strong></td>
        </tr>
        <tr><td colspan="3" id="invPreviewBalance" style="text-align:right;font-size:0.8rem;"></td></tr>
        </tfoot>
      </table>
      <h4 style="margin:0 0 8px;font-size:0.9rem;color:var(--ni-primary);">Mutasi Persediaan</h4>
      <table class="ni-table">
        <thead><tr><th>Item</th><th>Tipe</th><th style="text-align:right">Stok Sebelum</th>
          <th style="text-align:right">Delta</th><th style="text-align:right">Stok Sesudah</th>
          <th style="text-align:right">Nilai (Rp)</th></tr></thead>
        <tbody id="invPreviewMutasiBody"></tbody>
      </table>
    </div>
    <div class="ni-modal__footer">
      <button type="button" class="ni-btn ni-btn--secondary" onclick="closeInvPreview()">Tutup</button>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Buat auto-cost + preview JS partial**

Create `templates/inventory/_autocost_js.html`:
```html
{% comment %}
Auto-fill harga/unit dari sistem (per metode costing) saat item/entitas/gudang berubah,
+ badge peringatan bila belum ada stok, + fetch endpoint preview untuk modal.
Param: preview_url (nama url), cost_field (nama field unit_cost di baris formset).
{% endcomment %}
<script>
(function () {
  var STOCK_URL   = '{% url "inventory:stock_available" %}';
  var PREVIEW_URL = '{% url preview_url %}';
  var COST_FIELD  = '{{ cost_field }}';
  var ebSel = document.getElementById('id_eb_hierarki');
  var whSel = document.getElementById('id_warehouse');

  function ebParams() {
    var v = ebSel ? ebSel.value : '';
    var p = {};
    if (!v) return p;
    var parts = v.split(':'), lvl = parts[0], pk = parts[1];
    var lv1 = window.__getEBLv1Id ? window.__getEBLv1Id(v) : (lvl === 'lv1' ? pk : '');
    if (lv1) p.eb = lv1;
    if (lvl === 'lv2') p.eb_lv2 = pk;
    if (lvl === 'lv3') p.eb_lv3 = pk;
    return p;
  }

  function costInput(row) { return row.querySelector('input[name$="-' + COST_FIELD + '"]'); }
  function itemSelect(row) { return row.querySelector('select[name$="-item"]'); }

  function badge(row, show) {
    var cell = costInput(row) ? costInput(row).parentNode : null;
    if (!cell) return;
    var b = cell.querySelector('.ni-nostock-badge');
    if (show && !b) {
      b = document.createElement('div');
      b.className = 'ni-nostock-badge';
      b.style.cssText = 'font-size:0.7rem;color:var(--ni-warning,#f59e0b);margin-top:2px;';
      b.textContent = 'Belum ada stok di entitas/gudang ini — isi harga manual.';
      cell.appendChild(b);
    } else if (!show && b) { b.remove(); }
  }

  function fillCost(row) {
    var itSel = itemSelect(row), costEl = costInput(row);
    if (!itSel || !costEl || !itSel.value || !whSel || !whSel.value) return;
    var params = ebParams();
    params.item = itSel.value; params.warehouse = whSel.value;
    var qs = Object.keys(params).map(function (k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
    }).join('&');
    fetch(STOCK_URL + '?' + qs).then(function (r) { return r.json(); }).then(function (d) {
      // qty_sistem auto-fill (opname): isi bila field ada di baris ini
      var qsysEl = row.querySelector('input[name$="-qty_sistem"]');
      if (qsysEl && d.available !== null && d.available !== undefined) qsysEl.value = d.available;
      if (d.unit_cost === null || d.unit_cost === undefined) {
        badge(row, true);
      } else {
        costEl.value = d.unit_cost; badge(row, false);
      }
    }).catch(function () {});
  }

  function bindRow(row) {
    var itSel = itemSelect(row);
    if (itSel && !itSel.dataset.autocostBound) {
      itSel.dataset.autocostBound = '1';
      itSel.addEventListener('change', function () { fillCost(row); });
    }
  }
  function bindAll() {
    document.querySelectorAll('.item-row').forEach(bindRow);
  }
  if (ebSel) ebSel.addEventListener('change', bindAll);
  if (whSel) whSel.addEventListener('change', function () {
    document.querySelectorAll('.item-row').forEach(fillCost);
  });
  document.addEventListener('DOMContentLoaded', bindAll);
  bindAll();

  // ── Preview modal ──────────────────────────────────────────────
  function fmt(n) { return parseFloat(n || 0).toLocaleString('id-ID'); }
  window.openInvPreview = function () {
    var form = document.querySelector('form');
    var modal = document.getElementById('invPreviewModal');
    var err = document.getElementById('invPreviewError');
    err.style.display = 'none';
    modal.style.display = 'flex';
    fetch(PREVIEW_URL, { method: 'POST', body: new FormData(form),
      headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var jb = document.getElementById('invPreviewJurnalBody');
        var mb = document.getElementById('invPreviewMutasiBody');
        jb.innerHTML = ''; mb.innerHTML = '';
        if (!j.ok) {
          err.style.display = 'block';
          err.textContent = 'Tidak bisa membuat preview. Lengkapi/validasi form terlebih dulu.';
          return;
        }
        j.jurnal.forEach(function (l) {
          jb.innerHTML += '<tr><td>' + l.akun + '</td><td style="text-align:right">' +
            fmt(l.debit) + '</td><td style="text-align:right">' + fmt(l.kredit) + '</td></tr>';
        });
        document.getElementById('invPreviewTotalD').textContent = fmt(j.total_debit);
        document.getElementById('invPreviewTotalK').textContent = fmt(j.total_kredit);
        var bal = document.getElementById('invPreviewBalance');
        bal.textContent = j.balance ? '✓ Balance' : '✗ Tidak balance';
        bal.style.color = j.balance ? 'var(--ni-success,#16a34a)' : 'var(--ni-danger)';
        j.mutasi.forEach(function (m) {
          var note = m.catatan ? ' <em style="color:var(--ni-text-muted)">(' + m.catatan + ')</em>' : '';
          mb.innerHTML += '<tr><td>' + m.item + '</td><td>' + m.movement_type + note +
            '</td><td style="text-align:right">' + fmt(m.stok_sebelum) +
            '</td><td style="text-align:right">' + fmt(m.delta) +
            '</td><td style="text-align:right">' + fmt(m.stok_sesudah) +
            '</td><td style="text-align:right">' + fmt(m.nilai) + '</td></tr>';
        });
        if (window.lucide) lucide.createIcons();
      }).catch(function () {
        err.style.display = 'block'; err.textContent = 'Gagal memuat preview.';
      });
  };
  window.closeInvPreview = function () {
    document.getElementById('invPreviewModal').style.display = 'none';
  };
})();
</script>
```

- [ ] **Step 6: Verifikasi manual (server dev)**

Run: `python manage.py runserver` lalu buka `/inventory/adjustment/create/`.
Expected:
- Tanggal terisi hari ini.
- Dropdown entitas satu, indentasi lv1/lv2/lv3.
- Pilih entitas → opsi gudang menyempit ke gudang milik lv1 tsb.
- Pilih item + gudang → Harga/Unit terisi otomatis; bila item tanpa stok, muncul badge peringatan.
- Klik "Preview Jurnal & Mutasi" → modal menampilkan jurnal balance + tabel mutasi.

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/views.py templates/inventory/adjustment_form.html templates/inventory/_eb_hierarki_scope_js.html templates/inventory/_inv_preview_modal.html templates/inventory/_autocost_js.html
git commit -m "feat(inventory): adjustment form hierarkis + auto-cost + preview modal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Template opname — pola sama (reuse partial)

**Files:**
- Modify: `apps/inventory/views.py` — `opname_create` (1396–1419) tambah `eb_options_json`
- Modify: `templates/inventory/opname_form.html`

- [ ] **Step 1: Tambah context `eb_options_json` di `opname_create`**

Di `apps/inventory/views.py`, ganti isi `opname_create` (baris 1396–1419) menjadi:
```python
@login_required
def opname_create(request: HttpRequest) -> HttpResponse:
    """Create a stock opname (header + items) and post it immediately."""
    from apps.purchase.views import _get_eb_dropdown_options
    if request.method == 'POST':
        form = StockOpnameForm(request.POST)
        formset = StockOpnameItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    opn = form.save()
                    formset.instance = opn
                    formset.save()
                    header = process_opname(opn)
            except ValueError as e:
                messages.error(request, str(e))
            else:
                msg = f'Opname {opn.nomor} diposting.'
                if header:
                    msg += f' Jurnal {header.nomor_transaksi}.'
                messages.success(request, msg)
                return redirect('inventory:opname_list')
    else:
        form = StockOpnameForm()
        formset = StockOpnameItemFormSet()
    return render(request, 'inventory/opname_form.html', {
        'form': form, 'formset': formset,
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
    })
```

- [ ] **Step 2: Inspeksi `opname_form.html`**

Run: `python -c "print(open(r'templates/inventory/opname_form.html', encoding='utf-8').read())"`
Expected: struktur mirip adjustment_form (header entitas 3-select + formset items dengan kolom item/qty_sistem/qty_fisik/unit_cost). Catat nomor baris blok entitas & btn-row & include JS.

- [ ] **Step 3: Terapkan perubahan setara Task 6 pada `opname_form.html`**

Lakukan perubahan yang sama seperti Task 6 Step 3 pada `opname_form.html`:
- Ganti blok tiga select entitas dengan satu baris berisi `{{ form.tanggal }}`, `{{ form.eb_hierarki }}`, `{{ form.warehouse }}`, lalu baris kedua `{{ form.akun_selisih }}` (markup identik Task 6 Step 3(a)).
- Sisipkan tombol "Preview Jurnal & Mutasi" di `ni-btn-row` (identik Task 6 Step 3(b), teks tombol submit biarkan sesuai opname existing).
- Ganti `{% include 'inventory/_warehouse_scope_js.html' %}` dengan tiga include berikut, dan hapus include warehouse_scope lama:
```html
{% include 'inventory/_inv_preview_modal.html' %}
{% include 'inventory/_eb_hierarki_scope_js.html' %}
{% include 'inventory/_autocost_js.html' with preview_url='inventory:opname_preview' cost_field='unit_cost' %}
```
Catatan: `_autocost_js.html` sudah menangani auto-fill `qty_sistem` (kolom khusus opname) via selector `input[name$="-qty_sistem"]`, jadi tombol/skrip "Ambil qty sistem" lama—jika ada—boleh dibiarkan atau dihapus; auto-fill baru berjalan saat item/gudang dipilih.

- [ ] **Step 4: Verifikasi manual**

Run: `python manage.py runserver`, buka `/inventory/opname/create/`.
Expected: tanggal hari ini; entitas hierarkis; pilih item+gudang → `qty_sistem` dan `unit_cost` terisi otomatis; badge bila tanpa stok; preview modal menampilkan mutasi `opname_in/out` dan jurnal balance (atau "tidak ada mutasi" bila selisih 0).

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/views.py templates/inventory/opname_form.html
git commit -m "feat(inventory): opname form hierarkis + auto-cost + preview (reuse partial)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Regresi & verifikasi ledger terupdate

**Files:**
- Test: `apps/inventory/tests_autocost_preview.py` (tambah class ledger-updated)

- [ ] **Step 1: Tulis test ledger terupdate lewat view create sungguhan**

Tambahkan:
```python
class LedgerUpdatedAfterPostTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u4', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()

    def test_adjustment_create_updates_ledger(self):
        before = ledger.get_available_stock(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(before, Decimal('0'))
        resp = self.client.post('/inventory/adjustment/create/', {
            'tanggal': '2026-07-18', 'eb_hierarki': f'lv1:{self.eb.pk}',
            'warehouse': self.wh.pk, 'akun_selisih': self.selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': self.item.pk, 'items-0-qty': '7', 'items-0-unit_cost': '100',
        })
        self.assertEqual(resp.status_code, 302)  # redirect ke list
        after = ledger.get_available_stock(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(after, Decimal('7'))
```

- [ ] **Step 2: Jalankan test — pastikan lulus**

Run: `python manage.py test apps.inventory.tests_autocost_preview.LedgerUpdatedAfterPostTests -v 2`
Expected: PASS.

- [ ] **Step 3: Jalankan seluruh test inventory (regresi)**

Run: `python manage.py test apps.inventory -v 1`
Expected: semua PASS (termasuk `tests_fase6`, `tests`).

- [ ] **Step 4: Jalankan regresi purchase (helper EB dipakai bersama)**

Run: `python manage.py test apps.purchase -v 1`
Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/tests_autocost_preview.py
git commit -m "test(inventory): ledger terupdate setelah posting adjustment via view

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Finalisasi

- [ ] **Step 1: Verifikasi akhir end-to-end (verify skill bila tersedia)**

Jalankan `python manage.py runserver`, uji kedua form: auto-cost, badge no-stock, preview jurnal & mutasi, submit → cek list & kartu stok mencerminkan saldo baru.

- [ ] **Step 2: Gunakan skill finishing-a-development-branch**

Setelah semua test hijau & verifikasi lolos, gunakan `superpowers:finishing-a-development-branch` untuk memutuskan merge/PR.

---

## Catatan Implementasi

- **Import `_get_eb_dropdown_options`**: diimpor lokal di dalam view (`from apps.purchase.views import _get_eb_dropdown_options`) — inventory→purchase sudah ada precedent (baris 21 views.py), jadi tidak perlu refactor pindah modul (menghindari scope creep).
- **`safe_json`** sudah diimpor di `views.py` (baris 5).
- **Bulk item (RMB/FGB/ITMB)**: `_mutation_row` menangani outflow bulk (qty==0 → nilai = unit_cost/total_cost) & inflow bulk (qty=1). Delta tampil apa adanya; ini konsisten dengan konvensi value-based sistem.
- **Formset `unit_cost` opname untuk penurunan**: nilainya diabaikan saat posting (biaya dari konsumsi), tetapi tetap di-auto-fill sebagai info; ini tidak mengubah jurnal.
- **CSRF**: form `openInvPreview` mengirim `FormData` dari `<form>` yang sudah memuat `{% csrf_token %}`, jadi token ikut terkirim; view `@login_required` biasa (bukan `@csrf_exempt`).
```
