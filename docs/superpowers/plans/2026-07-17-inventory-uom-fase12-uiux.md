# Perbaikan UI/UX Fase 1 (UOM) & Fase 2 (Stock Ledger + Gudang) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menyelaraskan empat layar Fase 2 (Buku Persediaan, Kartu Stok, Gudang list/form) ke design system aplikasi, memunculkan satuan (UOM) di semua angka stok, menambah filter Entitas Bisnis + valuasi persediaan, dan menghaluskan tiga layar UOM Fase 1.

**Architecture:** Perubahan lapisan presentasi (Django templates) + penambahan context aditif di view `apps/inventory/views.py` dan `apps/uom/views.py`. Tidak ada perubahan model/migrasi/logika stok. Meniru pola matang `templates/inventory/inventory_list.html` dan komponen `components/eb_filter_modal.html`.

**Tech Stack:** Django templates, `django.contrib.humanize` (`intcomma`), ikon lucide (`data-lucide`), pytest + Django TestCase.

**Basis rujukan spec:** `docs/superpowers/specs/2026-07-17-inventory-uom-fase12-uiux-design.md`

---

## Catatan lingkungan (baca dulu)

- **Bukan git repo.** Abaikan langkah `git commit`. Sebagai gantinya, tiap Task diakhiri **Checkpoint**: jalankan test + `manage.py check`, lalu verifikasi manual di browser.
- **Direktori kerja perintah:** semua perintah `pytest`/`manage.py` dijalankan dari `naveda_integra/` (lokasi `manage.py`).
- **Menjalankan satu test:** `pytest apps/inventory/tests.py::NamaClass::nama_test -v`
- **Cek template/URL tanpa error:** `python manage.py check`
- **Menjalankan server manual:** `python manage.py runserver` lalu buka URL layar terkait.
- **Fakta model terverifikasi:** `StockMovement.qty` bertanda (masuk +, keluar −); `movement_type` ∈ {purchase_in, sale_out, production_in, production_out, saldo_awal}; `StockMovement.entitas_bisnis` ada; `ItemMasterPurchase.stock_uom` (FK UOM, nullable) ada; nilai layer = `remaining_qty × unit_cost`.

---

## Struktur file

**Modify (view):**
- `apps/inventory/views.py` — `stock_ledger` (Task 1), `stock_card` (Task 3)
- `apps/uom/views.py` — `unit_list` (Task 7), `unit_create`/`unit_update` (Task 8), `conversion_create`/`conversion_update`/`conversion_delete` (Task 9)

**Modify (template, rewrite penuh):**
- `templates/inventory/stock_ledger.html` (Task 2)
- `templates/inventory/stock_card.html` (Task 4)
- `templates/inventory/warehouse_list.html` (Task 5)
- `templates/inventory/warehouse_form.html` (Task 6)
- `templates/uom/unit_list.html` (Task 7)
- `templates/uom/unit_form.html` (Task 8)
- `templates/uom/item_conversion_form.html` (Task 9)

**Modify (test):**
- `apps/inventory/tests.py` — tes view untuk Task 1 & Task 3

Urutan: Task 1→2 (ledger), 3→4 (kartu stok), 5, 6 (gudang), 7, 8, 9 (UOM). Tiap task berdiri sendiri & bisa diverifikasi terpisah.

---

## Task 1: `stock_ledger` view — filter EB, guard saldo, prefetch UOM

**Files:**
- Modify: `apps/inventory/views.py` (fungsi `stock_ledger`, sekarang di ~`:413-447`)
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan di akhir `apps/inventory/tests.py`:

```python
class StockLedgerViewTests(DjangoTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb_a = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb_b = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb_a, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('10'))
        StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb_b, tanggal='2026-01-02',
            movement_type='purchase_in', qty=Decimal('7'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('7'))

    def test_eb_filter_narrows_rows(self):
        url = reverse('inventory:stock_ledger')
        resp = self.client.get(url, {'entitas_bisnis': f'lv1:{self.eb_a.pk}'})
        self.assertEqual(resp.status_code, 200)
        rows = resp.context['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['mv'].entitas_bisnis_id, self.eb_a.pk)

    def test_saldo_valid_flag(self):
        url = reverse('inventory:stock_ledger')
        # tanpa filter spesifik → saldo tidak valid
        resp = self.client.get(url)
        self.assertFalse(resp.context['saldo_valid'])
        # filter item + gudang → valid (gudang boleh kosong string? butuh keduanya)
        resp2 = self.client.get(url, {'item': self.item.pk, 'warehouse': '999'})
        self.assertTrue(resp2.context['saldo_valid'])

    def test_eb_tree_in_context(self):
        resp = self.client.get(reverse('inventory:stock_ledger'))
        self.assertIn('eb_tree', resp.context)
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `pytest apps/inventory/tests.py::StockLedgerViewTests -v`
Expected: FAIL — `KeyError: 'saldo_valid'` / `eb_tree` tidak ada / jumlah rows salah.

- [ ] **Step 3: Ubah fungsi `stock_ledger`**

Ganti seluruh fungsi `stock_ledger` di `apps/inventory/views.py` dengan:

```python
@login_required
def stock_ledger(request: HttpRequest) -> HttpResponse:
    """Buku persediaan: daftar StockMovement + saldo berjalan (read-only)."""
    from apps.inventory.models import StockMovement
    from apps.purchase.models import ItemMasterPurchase
    item_id = request.GET.get('item', '')
    wh_id = request.GET.get('warehouse', '')
    tgl_dari = request.GET.get('tanggal_dari', '')
    tgl_sampai = request.GET.get('tanggal_sampai', '')
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    qs = StockMovement.objects.select_related(
        'item', 'item__stock_uom', 'entitas_bisnis', 'warehouse')
    if item_id:
        qs = qs.filter(item_id=item_id)
    if wh_id:
        qs = qs.filter(warehouse_id=wh_id)
    if tgl_dari:
        qs = qs.filter(tanggal__gte=tgl_dari)
    if tgl_sampai:
        qs = qs.filter(tanggal__lte=tgl_sampai)
    if eb_filter_list:
        qs = qs.filter(entitas_bisnis_id__in=_resolve_eb_lv1_ids(eb_filter_list, request.user))
    qs = qs.order_by('tanggal', 'created_at')

    rows, saldo = [], Decimal('0')
    for mv in qs:
        saldo += mv.qty
        rows.append({'mv': mv, 'saldo': saldo})

    return render(request, 'inventory/stock_ledger.html', {
        'title': 'Buku Persediaan',
        'rows': rows,
        'items': ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']).order_by('item_id'),
        'warehouses': Warehouse.objects.filter(is_active=True).order_by('kode'),
        'item_filter': item_id, 'wh_filter': wh_id,
        'tanggal_dari': tgl_dari, 'tanggal_sampai': tgl_sampai,
        'eb_tree': _get_eb_tree(request.user),
        'eb_filter_list': eb_filter_list,
        'saldo_valid': bool(item_id) and bool(wh_id),
    })
```

Catatan: `_get_eb_tree` dan `_resolve_eb_lv1_ids` sudah di-import di baris atas file (`from apps.purchase.views import _get_eb_tree, _resolve_eb_lv1_ids`). Tidak perlu import lagi.

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `pytest apps/inventory/tests.py::StockLedgerViewTests -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Checkpoint**

Run: `python manage.py check`
Expected: `System check identified no issues`.
(Verifikasi visual dilakukan di Task 2 setelah template diperbarui.)

---

## Task 2: `stock_ledger.html` — redesign ke design system

**Files:**
- Modify (rewrite): `templates/inventory/stock_ledger.html`

- [ ] **Step 1: Ganti seluruh isi file**

```django
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Buku Persediaan{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Buku Persediaan</h1>
    <p class="ni-page-header__subtitle">Pergerakan stok append-only beserta saldo berjalan</p>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__body" style="padding:16px;">
    <form method="get" id="ledgerFilterForm" style="display:flex;gap:12px;flex-wrap:wrap;align-items:end;">
      <div class="ni-form-group" style="margin:0;flex:1;min-width:180px;">
        <label class="ni-form-label">Item</label>
        <select name="item" class="ni-input">
          <option value="">— Semua Item —</option>
          {% for it in items %}
          <option value="{{ it.pk }}" {% if item_filter == it.pk|stringformat:'s' %}selected{% endif %}>{{ it.item_id }} — {{ it.nama }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="ni-form-group" style="margin:0;flex:1;min-width:140px;">
        <label class="ni-form-label">Gudang</label>
        <select name="warehouse" class="ni-input">
          <option value="">— Semua Gudang —</option>
          {% for w in warehouses %}
          <option value="{{ w.pk }}" {% if wh_filter == w.pk|stringformat:'s' %}selected{% endif %}>{{ w.kode }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="ni-form-group" style="margin:0;flex:1;min-width:140px;">
        <label class="ni-form-label">Dari Tanggal</label>
        <input type="date" name="tanggal_dari" class="ni-input" value="{{ tanggal_dari }}">
      </div>
      <div class="ni-form-group" style="margin:0;flex:1;min-width:140px;">
        <label class="ni-form-label">Sampai Tanggal</label>
        <input type="date" name="tanggal_sampai" class="ni-input" value="{{ tanggal_sampai }}">
      </div>
      {% include 'components/eb_filter_modal.html' with filter_form_id="ledgerFilterForm" %}
      <button type="submit" class="ni-btn ni-btn--primary ni-btn--sm">
        <i data-lucide="search" style="width:14px;height:14px"></i> Filter
      </button>
      <a href="{% url 'inventory:stock_ledger' %}" class="ni-btn ni-btn--secondary ni-btn--sm">Reset</a>
    </form>
  </div>
</div>

{% if not saldo_valid %}
<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;border-left:3px solid var(--ni-warning,#f59e0b);">
  <div class="ni-card__body" style="padding:12px 16px;font-size:0.85em;">
    <i data-lucide="info" style="width:14px;height:14px;vertical-align:text-bottom;"></i>
    Kolom <strong>Saldo</strong> hanya bermakna bila difilter ke <strong>satu item</strong> dan <strong>satu gudang</strong>.
  </div>
</div>
{% endif %}

<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Tanggal</th>
          <th>Item</th>
          <th>Jenis</th>
          <th>Gudang</th>
          <th class="ni-text-right">Qty</th>
          <th class="ni-text-right">Biaya/Unit</th>
          <th class="ni-text-right">Saldo</th>
        </tr>
      </thead>
      <tbody>
        {% for r in rows %}
        <tr>
          <td>{{ r.mv.tanggal }}</td>
          <td>{{ r.mv.item.item_id }}</td>
          <td>
            {% if r.mv.qty > 0 %}
            <span class="ni-badge ni-badge--success">{{ r.mv.get_movement_type_display }}</span>
            {% else %}
            <span class="ni-badge ni-badge--danger">{{ r.mv.get_movement_type_display }}</span>
            {% endif %}
          </td>
          <td>{{ r.mv.warehouse.kode|default:'—' }}</td>
          <td class="ni-text-right" style="color:{% if r.mv.qty < 0 %}var(--ni-danger,#ef4444){% else %}var(--ni-success,#10b981){% endif %};font-weight:500;">
            {{ r.mv.qty|floatformat:'-2' }} {{ r.mv.item.stock_uom.kode|default:'' }}
          </td>
          <td class="ni-text-right">{{ r.mv.unit_cost|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ r.saldo|floatformat:'-2' }} {{ r.mv.item.stock_uom.kode|default:'' }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="7" class="ni-text-center ni-text-muted">Tidak ada pergerakan.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Cek render tanpa error**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 3: Smoke test render**

Run: `pytest apps/inventory/tests.py::StockLedgerViewTests::test_eb_tree_in_context -v`
Expected: PASS (mengonfirmasi template ter-render 200 dengan komponen EB).

- [ ] **Step 4: Checkpoint manual**

`python manage.py runserver`, buka `/inventory/stock-ledger/` (atau path sesuai `inventory:stock_ledger`). Verifikasi:
- Header + subtitle tampil; filter dalam card; tombol "Filter Entitas Bisnis" muncul.
- Banner guard saldo muncul saat filter belum spesifik; hilang saat item+gudang dipilih.
- Qty bertanda + satuan; masuk hijau, keluar merah; jenis sebagai badge; angka rata kanan.

---

## Task 3: `stock_card` view — filter EB + valuasi

**Files:**
- Modify: `apps/inventory/views.py` (fungsi `stock_card`, ~`:450-476`)
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal**

Tambahkan di `apps/inventory/tests.py`:

```python
class StockCardViewTests(DjangoTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u2', password='p')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('4'))
        StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-02',
            movement_type='purchase_in', qty=Decimal('8'), unit_cost=Decimal('6'),
            remaining_qty=Decimal('8'))

    def test_totals_computed(self):
        url = reverse('inventory:stock_card')
        resp = self.client.get(url, {'item': self.item.pk})
        self.assertEqual(resp.status_code, 200)
        # total on hand = saldo semua movement = 10 + 8 = 18
        self.assertEqual(resp.context['total_on_hand'], Decimal('18'))
        # total value = layer aktif: 4*5 + 8*6 = 20 + 48 = 68
        self.assertEqual(resp.context['total_value'], Decimal('68'))

    def test_no_item_no_totals(self):
        resp = self.client.get(reverse('inventory:stock_card'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context['item'])
```

- [ ] **Step 2: Jalankan test, pastikan gagal**

Run: `pytest apps/inventory/tests.py::StockCardViewTests -v`
Expected: FAIL — `KeyError: 'total_on_hand'`.

- [ ] **Step 3: Ubah fungsi `stock_card`**

Ganti seluruh fungsi `stock_card` di `apps/inventory/views.py` dengan:

```python
@login_required
def stock_card(request: HttpRequest) -> HttpResponse:
    """Kartu stok per item: valuasi, layer inflow aktif + saldo per gudang (read-only)."""
    from django.db.models import Sum
    from apps.inventory.models import StockMovement
    from apps.purchase.models import ItemMasterPurchase
    item_id = request.GET.get('item', '')
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    item = None
    layers = []
    saldo_per_wh = []
    total_on_hand = Decimal('0')
    total_value = Decimal('0')
    if item_id:
        item = get_object_or_404(
            ItemMasterPurchase.objects.select_related('stock_uom'), pk=item_id)
        mv_qs = StockMovement.objects.filter(item=item)
        layer_qs = mv_qs.filter(remaining_qty__gt=0)
        if eb_filter_list:
            eb_ids = _resolve_eb_lv1_ids(eb_filter_list, request.user)
            mv_qs = mv_qs.filter(entitas_bisnis_id__in=eb_ids)
            layer_qs = layer_qs.filter(entitas_bisnis_id__in=eb_ids)
        layers = list(
            layer_qs.select_related('entitas_bisnis', 'warehouse')
            .order_by('tanggal', 'created_at'))
        saldo_per_wh = (
            mv_qs.values('warehouse__kode')
            .annotate(saldo=Sum('qty')).order_by('warehouse__kode')
        )
        total_on_hand = mv_qs.aggregate(s=Sum('qty'))['s'] or Decimal('0')
        total_value = sum((l.remaining_qty * l.unit_cost for l in layers), Decimal('0'))
    return render(request, 'inventory/stock_card.html', {
        'title': 'Kartu Stok', 'item': item, 'layers': layers,
        'saldo_per_wh': saldo_per_wh,
        'total_on_hand': total_on_hand, 'total_value': total_value,
        'items': ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']).order_by('item_id'),
        'item_filter': item_id,
        'eb_tree': _get_eb_tree(request.user),
        'eb_filter_list': eb_filter_list,
    })
```

- [ ] **Step 4: Jalankan test, pastikan lulus**

Run: `pytest apps/inventory/tests.py::StockCardViewTests -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Checkpoint**

Run: `python manage.py check`
Expected: no issues.

---

## Task 4: `stock_card.html` — redesign + stat tiles

**Files:**
- Modify (rewrite): `templates/inventory/stock_card.html`

- [ ] **Step 1: Ganti seluruh isi file**

```django
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Kartu Stok{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Kartu Stok</h1>
    <p class="ni-page-header__subtitle">Saldo, valuasi, dan layer FIFO aktif per item</p>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__body" style="padding:16px;">
    <form method="get" id="stockCardForm" style="display:flex;gap:12px;flex-wrap:wrap;align-items:end;">
      <div class="ni-form-group" style="margin:0;flex:1;min-width:220px;">
        <label class="ni-form-label">Item</label>
        <select name="item" class="ni-input" onchange="this.form.submit()">
          <option value="">— Pilih Item —</option>
          {% for it in items %}
          <option value="{{ it.pk }}" {% if item_filter == it.pk|stringformat:'s' %}selected{% endif %}>{{ it.item_id }} — {{ it.nama }}</option>
          {% endfor %}
        </select>
      </div>
      {% include 'components/eb_filter_modal.html' with filter_form_id="stockCardForm" %}
      <button type="submit" class="ni-btn ni-btn--primary ni-btn--sm">
        <i data-lucide="search" style="width:14px;height:14px"></i> Terapkan
      </button>
    </form>
  </div>
</div>

{% if item %}
<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
  <div class="ni-card ni-animate-fade-in" style="flex:1;min-width:220px;">
    <div class="ni-card__body" style="padding:16px;">
      <p class="ni-text-muted" style="margin:0 0 4px;font-size:0.8em;">Total Stok On-Hand</p>
      <p style="margin:0;font-size:1.5em;font-weight:600;">
        {{ total_on_hand|floatformat:'-2' }} <span style="font-size:0.6em;font-weight:400;">{{ item.stock_uom.kode|default:'' }}</span>
      </p>
    </div>
  </div>
  <div class="ni-card ni-animate-fade-in" style="flex:1;min-width:220px;">
    <div class="ni-card__body" style="padding:16px;">
      <p class="ni-text-muted" style="margin:0 0 4px;font-size:0.8em;">Total Nilai Persediaan</p>
      <p style="margin:0;font-size:1.5em;font-weight:600;">
        Rp {{ total_value|floatformat:0|intcomma }}
      </p>
    </div>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__body" style="padding:12px 16px;display:flex;justify-content:space-between;align-items:center;">
    <h2 class="ni-page-header__title" style="font-size:1.05em;margin:0;">Saldo per Gudang</h2>
    <a href="{% url 'inventory:stock_ledger' %}?item={{ item.pk }}" class="ni-btn ni-btn--secondary ni-btn--sm">
      <i data-lucide="book-open" style="width:14px;height:14px"></i> Lihat di Buku Persediaan
    </a>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Gudang</th><th class="ni-text-right">Saldo</th></tr></thead>
      <tbody>
        {% for s in saldo_per_wh %}
        <tr>
          <td>{{ s.warehouse__kode|default:'—' }}</td>
          <td class="ni-text-right">{{ s.saldo|floatformat:'-2' }} {{ item.stock_uom.kode|default:'' }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="2" class="ni-text-center ni-text-muted">—</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body" style="padding:12px 16px;">
    <h2 class="ni-page-header__title" style="font-size:1.05em;margin:0;">Layer Inflow Aktif (FIFO)</h2>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Tanggal</th><th>Entitas</th><th>Gudang</th>
          <th class="ni-text-right">Sisa Qty</th><th class="ni-text-right">Biaya/Unit</th><th class="ni-text-right">Nilai Layer</th>
        </tr>
      </thead>
      <tbody>
        {% for l in layers %}
        <tr>
          <td>{{ l.tanggal }}</td>
          <td>{{ l.entitas_bisnis.nama }}</td>
          <td>{{ l.warehouse.kode|default:'—' }}</td>
          <td class="ni-text-right">{{ l.remaining_qty|floatformat:'-2' }} {{ item.stock_uom.kode|default:'' }}</td>
          <td class="ni-text-right">{{ l.unit_cost|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{% widthratio l.remaining_qty 1 l.unit_cost %}</td>
        </tr>
        {% empty %}
        <tr><td colspan="6" class="ni-text-center ni-text-muted">Tidak ada layer aktif.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% else %}
<div class="ni-card ni-text-center ni-text-muted" style="padding:32px;">
  Pilih item untuk melihat kartu stok, valuasi, dan layer FIFO aktif.
</div>
{% endif %}
{% endblock %}
```

Catatan implementer: `{% widthratio l.remaining_qty 1 l.unit_cost %}` menghitung `remaining_qty × unit_cost` (dibulatkan ke bilangan bulat) tanpa perlu template filter kustom. Jika butuh pemisah ribuan pada Nilai Layer, biarkan apa adanya untuk sekarang (kolom total valuasi utama sudah ber-`intcomma` di stat tile).

- [ ] **Step 2: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 3: Smoke test**

Run: `pytest apps/inventory/tests.py::StockCardViewTests -v`
Expected: PASS.

- [ ] **Step 4: Checkpoint manual**

Buka `/inventory/stock-card/`, pilih item. Verifikasi: dua stat tile (On-Hand dgn satuan, Nilai Rp), tombol "Lihat di Buku Persediaan" pre-filter, satuan tampil di semua qty, kolom rata kanan, empty state saat item belum dipilih.

---

## Task 5: `warehouse_list.html` — redesign + status badge

**Files:**
- Modify (rewrite): `templates/inventory/warehouse_list.html`

- [ ] **Step 1: Ganti seluruh isi file**

```django
{% extends 'base.html' %}
{% block title %}Master Gudang{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">{{ title }}</h1>
    <p class="ni-page-header__subtitle">Lokasi fisik penyimpanan stok per Entitas Bisnis</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'inventory:warehouse_create' %}" class="ni-btn ni-btn--success">
      <i data-lucide="plus" style="width:16px;height:16px"></i> Gudang Baru
    </a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr><th>Bisnis</th><th>Kode</th><th>Nama</th><th>Alamat</th><th>Status</th><th>Aksi</th></tr>
      </thead>
      <tbody>
        {% for w in warehouses %}
        <tr>
          <td>{{ w.entitas_bisnis.nama }}</td>
          <td>{{ w.kode }}</td>
          <td>{{ w.nama }}</td>
          <td>{{ w.alamat|default:'—' }}</td>
          <td>
            {% if w.is_active %}
            <span class="ni-badge ni-badge--success">Aktif</span>
            {% else %}
            <span class="ni-badge ni-badge--secondary">Nonaktif</span>
            {% endif %}
          </td>
          <td>
            <div class="ni-btn-row">
              <a href="{% url 'inventory:warehouse_update' w.pk %}" class="ni-btn ni-btn--warning ni-btn--sm">Edit</a>
              <form method="post" action="{% url 'inventory:warehouse_toggle' w.pk %}" style="display:inline"
                    onsubmit="return confirm('{% if w.is_active %}Nonaktifkan{% else %}Aktifkan{% endif %} gudang {{ w.kode|escapejs }}?')">
                {% csrf_token %}
                <button type="submit" class="ni-btn ni-btn--secondary ni-btn--sm">
                  {% if w.is_active %}Nonaktifkan{% else %}Aktifkan{% endif %}
                </button>
              </form>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="6" class="ni-text-center ni-text-muted">Belum ada gudang.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 3: Checkpoint manual**

Buka `/inventory/warehouse/`. Verifikasi: header+subtitle+action, tabel dalam card, status badge, tombol toggle minta konfirmasi, empty state.

---

## Task 6: `warehouse_form.html` — redesign eksplisit

**Files:**
- Modify (rewrite): `templates/inventory/warehouse_form.html`

- [ ] **Step 1: Ganti seluruh isi file**

```django
{% extends 'base.html' %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">{{ title }}</h1>
    <p class="ni-page-header__subtitle">{% if is_edit %}Edit data gudang{% else %}Tambah gudang baru{% endif %}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'inventory:warehouse_list' %}" class="ni-btn ni-btn--secondary">
      <i data-lucide="arrow-left" style="width:16px;height:16px"></i> Kembali
    </a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <form method="post">
      {% csrf_token %}
      {% if is_edit %}
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">Kode Gudang</label>
          <input type="text" class="ni-input" value="{{ warehouse.kode }}" disabled>
        </div>
      </div>
      {% endif %}
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.entitas_bisnis.label }}</label>
          {{ form.entitas_bisnis }}
          {% if form.entitas_bisnis.errors %}<div class="ni-form-error">{{ form.entitas_bisnis.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.nama.label }}</label>
          {{ form.nama }}
          {% if form.nama.errors %}<div class="ni-form-error">{{ form.nama.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.alamat.label }}</label>
          {{ form.alamat }}
          {% if form.alamat.errors %}<div class="ni-form-error">{{ form.alamat.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group ni-form-group--inline">
          {{ form.is_active }}
          <label class="ni-form-label" style="margin:0;">{{ form.is_active.label }}</label>
          {% if form.is_active.errors %}<div class="ni-form-error">{{ form.is_active.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'inventory:warehouse_list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

Catatan implementer: verifikasi nama field form di `apps/inventory/forms.py` (`WarehouseForm`) benar `entitas_bisnis`, `nama`, `alamat`, `is_active`. Jika `WarehouseForm.Meta.fields` berbeda, sesuaikan blok field agar cocok (jangan tampilkan field yang tak ada di form).

- [ ] **Step 2: Verifikasi field form**

Baca `apps/inventory/forms.py` bagian `WarehouseForm`. Pastikan `fields` = `['entitas_bisnis', 'nama', 'alamat', 'is_active']` (atau sesuaikan template).

- [ ] **Step 3: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 4: Checkpoint manual**

Buka `/inventory/warehouse/create/` dan halaman edit. Verifikasi: layout dua kolom, checkbox Aktif inline, tombol Kembali, simpan/batal berfungsi.

---

## Task 7: `unit_list` — ikon lucide + kolom badge

**Files:**
- Modify: `apps/uom/views.py` (`DIMENSION_ICONS`)
- Modify (rewrite): `templates/uom/unit_list.html`

- [ ] **Step 1: Ganti peta ikon di `apps/uom/views.py`**

Ganti dict `DIMENSION_ICONS` (baris ~10-16) dengan nama ikon lucide:

```python
DIMENSION_ICONS = {
    'count': 'hash',
    'weight': 'scale',
    'volume': 'flask-conical',
    'length': 'ruler',
    'area': 'square',
}
```

(Tidak ada perubahan lain di `unit_list`; `g.icon` kini berisi nama ikon lucide.)

- [ ] **Step 2: Ganti seluruh isi `templates/uom/unit_list.html`**

```django
{% extends 'base.html' %}
{% load uom_extras %}
{% block title %}Master Satuan{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Master Satuan</h1>
    <p class="ni-page-header__subtitle">Daftar satuan unit-of-measure (UOM) beserta faktor konversinya</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'uom:create' %}" class="ni-btn ni-btn--success">
      <i data-lucide="plus" style="width:16px;height:16px"></i> Satuan Baru
    </a>
  </div>
</div>

{% for g in groups %}
<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px">
  <details open>
    <summary style="cursor:pointer;font-weight:600;font-size:1.05em;padding:14px 16px">
      <i data-lucide="{{ g.icon }}" style="width:16px;height:16px;vertical-align:text-bottom;"></i>
      {{ g.dimension_label|upper }} ({{ g.units|length }})
      {% if g.base_unit %}
      <span class="ni-text-muted" style="font-weight:400;font-size:0.85em;float:right">Base: {{ g.base_unit.kode }}</span>
      {% endif %}
    </summary>
    <div class="ni-table-wrapper">
      <table class="ni-table">
        <thead>
          <tr>
            <th>Kode</th>
            <th>Nama</th>
            <th class="ni-text-right">Faktor</th>
            <th class="ni-text-center">Base</th>
            <th class="ni-text-center">Sistem</th>
            <th class="ni-text-center">Aktif</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody>
          {% for u in g.units %}
          <tr>
            <td>{{ u.kode }}</td>
            <td>{{ u.nama }}</td>
            <td class="ni-text-right">{{ u.factor_to_base|trim_decimal }}</td>
            <td class="ni-text-center">
              {% if u.is_base %}<i data-lucide="check" style="width:14px;height:14px;color:var(--ni-success,#10b981)"></i>{% else %}<span class="ni-text-muted">—</span>{% endif %}
            </td>
            <td class="ni-text-center">
              {% if u.is_system %}<i data-lucide="check" style="width:14px;height:14px;color:var(--ni-success,#10b981)"></i>{% else %}<span class="ni-text-muted">—</span>{% endif %}
            </td>
            <td class="ni-text-center">
              {% if u.is_active %}<i data-lucide="check" style="width:14px;height:14px;color:var(--ni-success,#10b981)"></i>{% else %}<span class="ni-text-muted">—</span>{% endif %}
            </td>
            <td>
              <div class="ni-btn-row">
                <a href="{% url 'uom:update' u.pk %}" class="ni-btn ni-btn--warning ni-btn--sm">Edit</a>
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </details>
</div>
{% empty %}
<div class="ni-card ni-text-center ni-text-muted" style="padding:24px">Belum ada data satuan.</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 3: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 4: Checkpoint manual**

Buka `/uom/`. Verifikasi: ikon dimensi lucide di summary; kolom Base/Sistem/Aktif berupa centang hijau / strip; grup masih ter-collapse/expand.

---

## Task 8: `unit_form` — checkbox inline, preview live, kunci factor saat base

**Files:**
- Modify: `apps/uom/views.py` (`unit_create`, `unit_update`)
- Modify (rewrite): `templates/uom/unit_form.html`

- [ ] **Step 1: Kirim peta base-per-dimensi ke template**

Di `apps/uom/views.py`, tambahkan helper dan gunakan di kedua view. Tambah setelah import:

```python
def _base_by_dimension():
    return {
        u.dimension: u.kode
        for u in UnitOfMeasure.objects.filter(is_base=True)
    }
```

Ubah `render` di `unit_create`:

```python
    return render(request, 'uom/unit_form.html',
                  {'form': form, 'is_edit': False, 'title': 'Satuan Baru',
                   'base_by_dimension': _base_by_dimension()})
```

Ubah `render` di `unit_update`:

```python
    return render(request, 'uom/unit_form.html',
                  {'form': form, 'is_edit': True, 'unit': unit, 'title': 'Edit Satuan',
                   'base_by_dimension': _base_by_dimension()})
```

- [ ] **Step 2: Ganti seluruh isi `templates/uom/unit_form.html`**

```django
{% extends 'base.html' %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">{{ title }}</h1>
    <p class="ni-page-header__subtitle">{% if is_edit %}Edit data satuan{% else %}Tambah satuan baru{% endif %}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'uom:list' %}" class="ni-btn ni-btn--secondary">
      <i data-lucide="arrow-left" style="width:16px;height:16px"></i> Kembali
    </a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    {% if is_edit and unit.is_system %}
    <p style="font-size:0.8125rem;color:var(--ni-text-muted);margin:0 0 16px;">
      <em>Satuan bawaan sistem — kode tidak dapat diubah.</em>
    </p>
    {% endif %}
    {{ base_by_dimension|json_script:"baseByDimension" }}
    <form method="post">
      {% csrf_token %}
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.kode.label }}</label>
          {{ form.kode }}
          {% if form.kode.errors %}<div class="ni-form-error">{{ form.kode.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.nama.label }}</label>
          {{ form.nama }}
          {% if form.nama.errors %}<div class="ni-form-error">{{ form.nama.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.dimension.label }}</label>
          {{ form.dimension }}
          {% if form.dimension.errors %}<div class="ni-form-error">{{ form.dimension.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.factor_to_base.label }}</label>
          {{ form.factor_to_base }}
          {% if form.factor_to_base.errors %}<div class="ni-form-error">{{ form.factor_to_base.errors }}</div>{% endif %}
        </div>
      </div>
      <div class="ni-form-row">
        <div class="ni-form-group ni-form-group--inline">
          {{ form.is_base }}
          <label class="ni-form-label" style="margin:0;">{{ form.is_base.label }}</label>
        </div>
        <div class="ni-form-group ni-form-group--inline">
          {{ form.is_active }}
          <label class="ni-form-label" style="margin:0;">{{ form.is_active.label }}</label>
        </div>
      </div>
      <p id="uomPreview" class="ni-text-muted" style="font-size:0.85em;margin:8px 0 0;"></p>
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'uom:list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>

<script>
(function () {
  'use strict';
  var baseMap = JSON.parse(document.getElementById('baseByDimension').textContent || '{}');
  var form = document.querySelector('.ni-card form');
  if (!form) return;
  var kode = form.querySelector('[name="kode"]');
  var dim = form.querySelector('[name="dimension"]');
  var factor = form.querySelector('[name="factor_to_base"]');
  var isBase = form.querySelector('[name="is_base"]');
  var preview = document.getElementById('uomPreview');

  function baseKode() {
    return (dim && baseMap[dim.value]) ? baseMap[dim.value] : '(base)';
  }
  function render() {
    if (isBase && isBase.checked) {
      if (factor) { factor.value = '1'; factor.setAttribute('disabled', 'disabled'); }
    } else if (factor) {
      factor.removeAttribute('disabled');
    }
    var k = (kode && kode.value) ? kode.value : '(kode)';
    var f = (factor && factor.value) ? factor.value : '?';
    preview.textContent = '1 ' + k + ' = ' + f + ' ' + baseKode();
  }
  [kode, dim, factor].forEach(function (el) {
    if (el) { el.addEventListener('input', render); el.addEventListener('change', render); }
  });
  if (isBase) isBase.addEventListener('change', render);
  render();
  // Re-enable factor before submit so disabled value still posts as 1
  form.addEventListener('submit', function () {
    if (factor && factor.hasAttribute('disabled')) {
      factor.removeAttribute('disabled');
      factor.value = '1';
    }
  });
})();
</script>
{% endblock %}
```

Catatan implementer: field disabled tidak ikut ter-POST; handler `submit` di atas mengaktifkan kembali `factor_to_base=1` sebelum kirim agar nilai base tetap tersimpan.

- [ ] **Step 3: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 4: Checkpoint manual**

Buka `/uom/create/`. Verifikasi: checkbox Base/Aktif inline; teks preview "1 <kode> = <factor> <base>" ter-update saat mengetik/ubah dimensi; mencentang Base mengunci factor ke 1; submit satuan base tersimpan `factor_to_base = 1`.

---

## Task 9: `item_conversion_form` — preview live

**Files:**
- Modify: `apps/uom/views.py` (`conversion_create`, `conversion_update`, `conversion_delete`)
- Modify (rewrite): `templates/uom/item_conversion_form.html`

- [ ] **Step 1: Kirim peta stock_uom per item ke template**

Di `apps/uom/views.py`, tambahkan helper:

```python
def _item_stock_uom_map():
    from apps.purchase.models import ItemMasterPurchase
    return {
        str(i.pk): (i.stock_uom.kode if i.stock_uom_id else '')
        for i in ItemMasterPurchase.objects.select_related('stock_uom').filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'])
    }
```

Tambahkan `'item_stock_uom_map': _item_stock_uom_map()` ke context `render` di `conversion_create` dan `conversion_update` (biarkan `conversion_delete` apa adanya — tak butuh preview).

Contoh `conversion_create`:

```python
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Konversi Baru', 'is_edit': False,
                   'item_stock_uom_map': _item_stock_uom_map()})
```

Contoh `conversion_update`:

```python
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Edit Konversi', 'is_edit': True,
                   'item_stock_uom_map': _item_stock_uom_map()})
```

- [ ] **Step 2: Sisipkan preview di `templates/uom/item_conversion_form.html`**

Di blok non-delete (`{% else %}` ... form), tepat sebelum `<div class="ni-btn-row" ...>`, tambahkan peta JSON + baris preview:

```django
      {% if item_stock_uom_map %}{{ item_stock_uom_map|json_script:"itemStockUom" }}{% endif %}
      <p id="convPreview" class="ni-text-muted" style="font-size:0.85em;margin:8px 0 0;"></p>
```

Lalu tambahkan sebelum `{% endblock %}` di akhir file:

```django
<script>
(function () {
  'use strict';
  var mapEl = document.getElementById('itemStockUom');
  if (!mapEl) return;
  var map = JSON.parse(mapEl.textContent || '{}');
  var form = document.querySelector('.ni-card form');
  if (!form) return;
  var itemSel = form.querySelector('[name="item"]');
  var uomSel = form.querySelector('[name="uom"]');
  var qty = form.querySelector('[name="qty_in_stock_uom"]');
  var preview = document.getElementById('convPreview');
  if (!preview) return;
  function uomText(sel) {
    if (!sel) return '?';
    var opt = sel.options[sel.selectedIndex];
    return opt ? opt.text.trim() : '?';
  }
  function render() {
    var stockKode = (itemSel && map[itemSel.value]) ? map[itemSel.value] : '(stock uom)';
    var q = (qty && qty.value) ? qty.value : '?';
    preview.textContent = '1 ' + uomText(uomSel) + ' = ' + q + ' ' + stockKode;
  }
  [itemSel, uomSel, qty].forEach(function (el) {
    if (el) { el.addEventListener('input', render); el.addEventListener('change', render); }
  });
  render();
})();
</script>
```

Catatan implementer: opsi `uom` menampilkan `kode - nama` (dari `__str__`); preview memakai teks opsi apa adanya — cukup untuk sanity-check arah konversi.

- [ ] **Step 3: Cek render**

Run: `python manage.py check`
Expected: no issues.

- [ ] **Step 4: Checkpoint manual**

Buka `/uom/conversion/create/`. Verifikasi: baris preview "1 <uom> = <qty> <stock_uom>" ter-update saat memilih item/uom & mengetik qty. Halaman hapus konversi tetap normal.

---

## Verifikasi akhir (lintas task)

- [ ] Jalankan seluruh test inventory: `pytest apps/inventory/tests.py -v` → semua PASS.
- [ ] `python manage.py check` → no issues.
- [ ] Smoke lintas layar via `runserver`: buka ketujuh layar, konfirmasi tak ada error template & satuan/badge/filter/valuasi tampil sesuai spec §F.
- [ ] Regresi ringan: layar yang menambah import EB (`stock_ledger`, `stock_card`) memuat tanpa `ImportError`/`NameError`.

---

## Self-review (sudah dijalankan penulis plan)

- **Spec coverage:** C1→Task 1-2; C2→Task 3-4; C3→Task 5; C4→Task 6; C5→Task 7; C6→Task 8; C7→Task 9; D (komponen dipakai ulang) tersebar; E (yang tidak dilakukan) dihormati (tak ada export/total ledger, tak ada filter EB di daftar gudang, tak ada perubahan model); F (verifikasi) → bagian Verifikasi akhir. Semua tercakup.
- **Placeholder scan:** tak ada TBD/TODO; semua langkah berisi kode nyata.
- **Type/nama konsisten:** context keys (`saldo_valid`, `eb_tree`, `eb_filter_list`, `total_on_hand`, `total_value`, `base_by_dimension`, `item_stock_uom_map`) dipakai konsisten antara view & template; helper `_resolve_eb_lv1_ids`/`_get_eb_tree` sudah ada di `inventory/views.py`.
- **Asumsi yang harus diverifikasi implementer saat eksekusi:** nama field `WarehouseForm` (Task 6 Step 2); path URL aktual tiap layar (pakai `{% url %}`, sudah aman).
