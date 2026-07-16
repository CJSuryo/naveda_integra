# Integrasi UI Fase 1 (UOM) & Fase 2 (Stock Ledger) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Melengkapi lapisan UI untuk fondasi UOM & Stock Ledger yang backend-nya sudah ada: menu Master Satuan, CRUD Gudang, CRUD Konversi Satuan Item, konversi UOM aktif di form Purchase/Sales/Manufacturing, dan viewer Stock Ledger/Kartu Stok.

**Architecture:** Django (apps: `uom`, `inventory`, `purchase`, `sales`, `manufacturing`). Prinsip: ledger & costing selalu dalam base/stock_uom; konversi hanya di batas input. Tiap transaksi menyimpan field base otoritatif (tak berubah) + `input_uom`/`input_qty` (audit). Semua view `@login_required`, gaya `ni-*`, akses EB via `_resolve_eb_lv1_ids`.

**Tech Stack:** Django 6.x, Django ORM/ModelForm, template DTL, `django.test.TestCase`.

> **PENTING — cara menjalankan test:** selalu pakai settings test (SQLite in-memory, per-proses, aman untuk 2 sesi paralel):
> `python manage.py test <label> --settings=naveda_integra.settings.test`
> Tanpa flag ini, test memakai DB Neon cloud bersama (`test_neondb`) dan akan bentrok antar-sesi. Semua perintah `python manage.py test ...` di bawah harus ditambah `--settings=naveda_integra.settings.test`.

**Spec:** [../specs/2026-07-16-uom-warehouse-ui-integration-design.md](../specs/2026-07-16-uom-warehouse-ui-integration-design.md)

---

## File Structure

**Baru:**
- `templates/inventory/warehouse_list.html`, `warehouse_form.html`
- `templates/inventory/stock_ledger.html`, `stock_card.html`
- `templates/uom/item_conversion_list.html`, `item_conversion_form.html`
- `apps/inventory/forms.py` (baru — belum ada)

**Diubah:**
- `apps/uom/conversion.py` (+`convert_input_to_base`)
- `apps/uom/forms.py`, `apps/uom/views.py`, `apps/uom/urls.py` (+ItemUOM CRUD)
- `apps/inventory/views.py`, `apps/inventory/urls.py` (+warehouse CRUD, +ledger, +stock card)
- `apps/purchase/models.py`, `apps/purchase/views.py`, `templates/purchase/purchase_form.html`
- `apps/sales/models.py`, `apps/sales/views.py`, `templates/sales/sales_form.html`
- `apps/manufacturing/models.py`, `apps/manufacturing/forms.py`, `apps/manufacturing/services.py` (bila perlu), templates BOM & production
- `templates/base.html` (4 entri menu)

---

## Task 1: Menu "Master Satuan" (C1)

**Files:**
- Modify: `templates/base.html` (submenu Inventory, sekitar baris 291-297)
- Test: `apps/uom/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/uom/tests.py`:

```python
class MasterSatuanMenuTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='menu@example.com', password='pw123456', name='M')
        self.client.force_login(self.user)

    def test_sidebar_links_master_satuan(self):
        # Halaman inventory memuat base.html dengan submenu Inventory
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('uom:list'))
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.uom.tests.MasterSatuanMenuTests -v 2`
Expected: FAIL — `uom:list` URL tidak ada di HTML.

- [ ] **Step 3: Tambah link menu** di `templates/base.html`, di dalam `<div class="ni-nav-submenu">` submenu Inventory (setelah link `inventory:laporan_persediaan`, sebelum `</div>` penutup submenu):

```html
          <a href="{% url 'uom:list' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Master Satuan</span>
          </a>
```

- [ ] **Step 4: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.uom.tests.MasterSatuanMenuTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/base.html apps/uom/tests.py
git commit -m "feat(uom): link Master Satuan di sidebar Inventory"
```

---

## Task 2: CRUD Gudang (Warehouse) — form & view (C2)

**Files:**
- Create: `apps/inventory/forms.py`
- Modify: `apps/inventory/views.py`, `apps/inventory/urls.py`
- Create: `templates/inventory/warehouse_list.html`, `templates/inventory/warehouse_form.html`
- Modify: `templates/base.html`
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/inventory/tests.py` (buat file/kelas bila belum ada; imports di atas file):

```python
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.entitas_bisnis.models import EntitasBisnis
from apps.inventory.models import Warehouse

User = get_user_model()


class WarehouseCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='wh@example.com', password='pw123456', name='W')
        self.client.force_login(self.user)
        self.eb = EntitasBisnis.objects.create(nama='Bisnis A', status_aktif=True)

    def test_list_renders(self):
        Warehouse.objects.create(entitas_bisnis=self.eb, kode='WH1', nama='Gudang Utama')
        resp = self.client.get(reverse('inventory:warehouse_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Gudang Utama')

    def test_create(self):
        resp = self.client.post(reverse('inventory:warehouse_create'), {
            'entitas_bisnis': self.eb.pk, 'kode': 'WH2',
            'nama': 'Gudang Cabang', 'alamat': 'Jl. X', 'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Warehouse.objects.filter(kode='WH2').exists())

    def test_toggle_active_soft(self):
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, kode='WH3', nama='G3')
        resp = self.client.post(reverse('inventory:warehouse_toggle', args=[wh.pk]))
        self.assertEqual(resp.status_code, 302)
        wh.refresh_from_db()
        self.assertFalse(wh.is_active)
```

> Cek `EntitasBisnis` field wajib: bila `create(nama=..., status_aktif=...)` gagal karena field wajib lain, sesuaikan setUp mengikuti pola di `apps/entitas_bisnis/tests.py`.

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.inventory.tests.WarehouseCrudTests -v 2`
Expected: FAIL — `NoReverseMatch` untuk `inventory:warehouse_list`.

- [ ] **Step 3: Buat `apps/inventory/forms.py`:**

```python
"""Inventory forms."""
from django import forms

from .models import Warehouse


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ('entitas_bisnis', 'kode', 'nama', 'alamat', 'is_active')
        widgets = {
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'kode': forms.TextInput(attrs={'class': 'ni-input'}),
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'is_active': forms.CheckboxInput(),
        }
```

- [ ] **Step 4: Tambah view** di `apps/inventory/views.py` (import di atas: `from .forms import WarehouseForm`, `from .models import Warehouse`, dan `from apps.purchase.views import _resolve_eb_lv1_ids` sudah ada):

```python
@login_required
def warehouse_list(request: HttpRequest) -> HttpResponse:
    from apps.entitas_bisnis.models import EntitasBisnis
    allowed = _resolve_eb_lv1_ids([], request.user)  # semua EB lv1 yang boleh diakses user
    qs = Warehouse.objects.select_related('entitas_bisnis').filter(
        entitas_bisnis_id__in=allowed).order_by('entitas_bisnis', 'kode')
    return render(request, 'inventory/warehouse_list.html', {
        'warehouses': qs, 'title': 'Master Gudang',
    })


@login_required
def warehouse_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gudang berhasil dibuat.')
            return redirect('inventory:warehouse_list')
    else:
        form = WarehouseForm()
    return render(request, 'inventory/warehouse_form.html',
                  {'form': form, 'title': 'Gudang Baru', 'is_edit': False})


@login_required
def warehouse_update(request: HttpRequest, pk: int) -> HttpResponse:
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=wh)
        if form.is_valid():
            form.save()
            messages.success(request, 'Gudang berhasil diperbarui.')
            return redirect('inventory:warehouse_list')
    else:
        form = WarehouseForm(instance=wh)
    return render(request, 'inventory/warehouse_form.html',
                  {'form': form, 'title': 'Edit Gudang', 'is_edit': True, 'warehouse': wh})


@login_required
def warehouse_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        wh.is_active = not wh.is_active
        wh.save(update_fields=['is_active'])
        messages.success(request, f'Gudang {wh.kode} {"diaktifkan" if wh.is_active else "dinonaktifkan"}.')
    return redirect('inventory:warehouse_list')
```

> `_resolve_eb_lv1_ids([], user)` mengembalikan seluruh id lv1 yang boleh diakses user saat list filter kosong — perilaku ini dipakai di `inventory_list`. Verifikasi return-nya berupa iterable id; bila `[]` berarti "tak terbatas", ganti filter jadi tanpa `.filter(entitas_bisnis_id__in=...)` saat allowed kosong.

- [ ] **Step 5: Tambah url** di `apps/inventory/urls.py` (dalam `urlpatterns`):

```python
    path('warehouse/', views.warehouse_list, name='warehouse_list'),
    path('warehouse/create/', views.warehouse_create, name='warehouse_create'),
    path('warehouse/<int:pk>/edit/', views.warehouse_update, name='warehouse_update'),
    path('warehouse/<int:pk>/toggle/', views.warehouse_toggle, name='warehouse_toggle'),
```

- [ ] **Step 6: Buat template** `templates/inventory/warehouse_list.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <a href="{% url 'inventory:warehouse_create' %}" class="ni-btn ni-btn--primary">+ Gudang</a>
  </div>
  <table class="ni-table">
    <thead><tr><th>Bisnis</th><th>Kode</th><th>Nama</th><th>Alamat</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {% for w in warehouses %}
      <tr>
        <td>{{ w.entitas_bisnis.nama }}</td>
        <td>{{ w.kode }}</td>
        <td>{{ w.nama }}</td>
        <td>{{ w.alamat|default:'—' }}</td>
        <td>{% if w.is_active %}Aktif{% else %}Nonaktif{% endif %}</td>
        <td>
          <a href="{% url 'inventory:warehouse_update' w.pk %}" class="ni-link">Edit</a>
          <form method="post" action="{% url 'inventory:warehouse_toggle' w.pk %}" style="display:inline">
            {% csrf_token %}
            <button type="submit" class="ni-link">{% if w.is_active %}Nonaktifkan{% else %}Aktifkan{% endif %}</button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6">Belum ada gudang.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 7: Buat template** `templates/inventory/warehouse_form.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <h1 class="ni-page__title">{{ title }}</h1>
  <form method="post" class="ni-form">
    {% csrf_token %}
    {% for field in form %}
      <div class="ni-form-group">
        <label class="ni-form-label">{{ field.label }}</label>
        {{ field }}
        {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
      </div>
    {% endfor %}
    <div class="ni-form-actions">
      <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
      <a href="{% url 'inventory:warehouse_list' %}" class="ni-btn">Batal</a>
    </div>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 8: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.inventory.tests.WarehouseCrudTests -v 2`
Expected: PASS (3 test)

- [ ] **Step 9: Tambah menu** di `templates/base.html` submenu Inventory (setelah link Master Satuan):

```html
          <a href="{% url 'inventory:warehouse_list' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Gudang</span>
          </a>
```

- [ ] **Step 10: Commit**

```bash
git add apps/inventory/forms.py apps/inventory/views.py apps/inventory/urls.py \
        templates/inventory/warehouse_list.html templates/inventory/warehouse_form.html \
        templates/base.html apps/inventory/tests.py
git commit -m "feat(inventory): CRUD Gudang (Warehouse) + menu"
```

---

## Task 3: CRUD Konversi Satuan Item (ItemUOM) (C3)

**Files:**
- Modify: `apps/uom/forms.py`, `apps/uom/views.py`, `apps/uom/urls.py`
- Create: `templates/uom/item_conversion_list.html`, `templates/uom/item_conversion_form.html`
- Modify: `templates/base.html`
- Test: `apps/uom/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/uom/tests.py`:

```python
class ItemUOMCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='iu@example.com', password='pw123456', name='I')
        self.client.force_login(self.user)
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.carton = UnitOfMeasure.objects.create(
            kode='ctn-t', nama='Carton Test', dimension='count', factor_to_base=None)
        self.item = ItemMasterPurchase.objects.create(
            nama='Item A', tipe_item='ITM', stock_uom=self.pcs)

    def test_list_renders(self):
        ItemUOM.objects.create(item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'))
        resp = self.client.get(reverse('uom:conversion_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '24')

    def test_create(self):
        resp = self.client.post(reverse('uom:conversion_create'), {
            'item': self.item.pk, 'uom': self.carton.pk, 'qty_in_stock_uom': '24',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ItemUOM.objects.filter(item=self.item, uom=self.carton).exists())

    def test_reject_uom_equal_stock_uom(self):
        resp = self.client.post(reverse('uom:conversion_create'), {
            'item': self.item.pk, 'uom': self.pcs.pk, 'qty_in_stock_uom': '1',
        })
        self.assertEqual(resp.status_code, 200)  # form invalid, re-render
        self.assertFalse(ItemUOM.objects.filter(item=self.item, uom=self.pcs).exists())
```

> `ItemMasterPurchase.objects.create(...)` mungkin butuh field wajib lain (mis. `item_id` auto?). Ikuti pola pembuatan item di `apps/uom/tests.py` yang sudah ada (kelas `ItemUOMModelTests`).

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.uom.tests.ItemUOMCrudTests -v 2`
Expected: FAIL — `NoReverseMatch` untuk `uom:conversion_list`.

- [ ] **Step 3: Tambah `ItemUOMForm`** di `apps/uom/forms.py`:

```python
from decimal import Decimal
from django import forms

from .models import ItemUOM


class ItemUOMForm(forms.ModelForm):
    class Meta:
        model = ItemUOM
        fields = ('item', 'uom', 'qty_in_stock_uom')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'uom': forms.Select(attrs={'class': 'ni-input'}),
            'qty_in_stock_uom': forms.NumberInput(attrs={'class': 'ni-input', 'step': 'any'}),
        }

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get('item')
        uom = cleaned.get('uom')
        qty = cleaned.get('qty_in_stock_uom')
        if item and uom and item.stock_uom_id == uom.pk:
            self.add_error('uom', 'Satuan konversi tidak boleh sama dengan satuan stok item.')
        if qty is not None and qty <= 0:
            self.add_error('qty_in_stock_uom', 'Harus lebih dari 0.')
        return cleaned
```

> Bila `apps/uom/forms.py` belum ada, buat file baru dengan isi di atas. Bila sudah ada `UnitOfMeasureForm`, tambahkan class ini di bawahnya (import digabung).

- [ ] **Step 4: Tambah view** di `apps/uom/views.py`:

```python
from .forms import ItemUOMForm  # gabung dengan import yang ada
from .models import ItemUOM     # gabung


@login_required
def conversion_list(request):
    item_filter = request.GET.get('item', '')
    qs = ItemUOM.objects.select_related('item', 'uom').order_by('item__nama', 'uom__kode')
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    from apps.purchase.models import ItemMasterPurchase
    items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']).order_by('item_id')
    return render(request, 'uom/item_conversion_list.html', {
        'conversions': qs, 'items': items, 'item_filter': item_filter,
        'title': 'Konversi Satuan Item',
    })


@login_required
def conversion_create(request):
    if request.method == 'POST':
        form = ItemUOMForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('uom:conversion_list')
    else:
        form = ItemUOMForm()
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Konversi Baru', 'is_edit': False})


@login_required
def conversion_update(request, pk):
    obj = get_object_or_404(ItemUOM, pk=pk)
    if request.method == 'POST':
        form = ItemUOMForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect('uom:conversion_list')
    else:
        form = ItemUOMForm(instance=obj)
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Edit Konversi', 'is_edit': True})


@login_required
def conversion_delete(request, pk):
    obj = get_object_or_404(ItemUOM, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('uom:conversion_list')
    return render(request, 'uom/item_conversion_form.html',
                  {'delete_obj': obj, 'title': 'Hapus Konversi'})
```

> Pastikan `get_object_or_404` diimport di `apps/uom/views.py` (`from django.shortcuts import get_object_or_404, redirect, render`).

- [ ] **Step 5: Tambah url** di `apps/uom/urls.py`:

```python
    path('konversi/', views.conversion_list, name='conversion_list'),
    path('konversi/create/', views.conversion_create, name='conversion_create'),
    path('konversi/<int:pk>/edit/', views.conversion_update, name='conversion_update'),
    path('konversi/<int:pk>/delete/', views.conversion_delete, name='conversion_delete'),
```

- [ ] **Step 6: Buat template** `templates/uom/item_conversion_list.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <div class="ni-page__header">
    <h1 class="ni-page__title">{{ title }}</h1>
    <a href="{% url 'uom:conversion_create' %}" class="ni-btn ni-btn--primary">+ Konversi</a>
  </div>
  <form method="get" class="ni-filter">
    <select name="item" class="ni-input" onchange="this.form.submit()">
      <option value="">— Semua Item —</option>
      {% for it in items %}
        <option value="{{ it.pk }}" {% if item_filter == it.pk|stringformat:'s' %}selected{% endif %}>{{ it.item_id }} — {{ it.nama }}</option>
      {% endfor %}
    </select>
  </form>
  <table class="ni-table">
    <thead><tr><th>Item</th><th>Satuan</th><th>= Qty Stok</th><th></th></tr></thead>
    <tbody>
      {% for c in conversions %}
      <tr>
        <td>{{ c.item.item_id }} — {{ c.item.nama }}</td>
        <td>{{ c.uom.kode }}</td>
        <td>1 {{ c.uom.kode }} = {{ c.qty_in_stock_uom }} {{ c.item.stock_uom.kode }}</td>
        <td>
          <a href="{% url 'uom:conversion_update' c.pk %}" class="ni-link">Edit</a>
          <form method="post" action="{% url 'uom:conversion_delete' c.pk %}" style="display:inline" onsubmit="return confirm('Hapus konversi ini?')">
            {% csrf_token %}<button type="submit" class="ni-link">Hapus</button>
          </form>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="4">Belum ada konversi.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 7: Buat template** `templates/uom/item_conversion_form.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <h1 class="ni-page__title">{{ title }}</h1>
  <form method="post" class="ni-form">
    {% csrf_token %}
    {% if delete_obj %}
      <p>Yakin hapus konversi <strong>{{ delete_obj }}</strong>?</p>
      <button type="submit" class="ni-btn ni-btn--danger">Hapus</button>
      <a href="{% url 'uom:conversion_list' %}" class="ni-btn">Batal</a>
    {% else %}
      {% for field in form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
      {% endfor %}
      <div class="ni-form-actions">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'uom:conversion_list' %}" class="ni-btn">Batal</a>
      </div>
    {% endif %}
  </form>
</div>
{% endblock %}
```

- [ ] **Step 8: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.uom.tests.ItemUOMCrudTests -v 2`
Expected: PASS

- [ ] **Step 9: Tambah menu** di `templates/base.html` submenu Inventory (setelah Master Satuan):

```html
          <a href="{% url 'uom:conversion_list' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Konversi Satuan Item</span>
          </a>
```

- [ ] **Step 10: Commit**

```bash
git add apps/uom/forms.py apps/uom/views.py apps/uom/urls.py \
        templates/uom/item_conversion_list.html templates/uom/item_conversion_form.html \
        templates/base.html apps/uom/tests.py
git commit -m "feat(uom): CRUD Konversi Satuan Item (ItemUOM) + menu"
```

---

## Task 4: Helper konversi input→base (fondasi C4)

**Files:**
- Modify: `apps/uom/conversion.py`
- Test: `apps/uom/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/uom/tests.py`:

```python
from apps.uom.conversion import convert_input_to_base


class ConvertInputToBaseTests(TestCase):
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.carton = UnitOfMeasure.objects.create(
            kode='ctn-x', nama='Carton', dimension='count', factor_to_base=None)
        self.item = ItemMasterPurchase.objects.create(
            nama='Konv', tipe_item='ITM', stock_uom=self.pcs)
        ItemUOM.objects.create(item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'))

    def test_none_uom_passthrough(self):
        qty, price = convert_input_to_base(self.item, None, Decimal('5'), Decimal('1000'))
        self.assertEqual(qty, Decimal('5'))
        self.assertEqual(price, Decimal('1000'))

    def test_stock_uom_passthrough(self):
        qty, price = convert_input_to_base(self.item, self.pcs, Decimal('5'), Decimal('1000'))
        self.assertEqual(qty, Decimal('5'))
        self.assertEqual(price, Decimal('1000'))

    def test_carton_to_pcs_converts_qty_and_price(self):
        # 10 carton @ Rp 24.000/carton, 1 carton = 24 pcs
        qty, price = convert_input_to_base(self.item, self.carton, Decimal('10'), Decimal('24000'))
        self.assertEqual(qty, Decimal('240'))          # 10 * 24
        self.assertEqual(price, Decimal('1000'))        # total 240.000 / 240 pcs
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.uom.tests.ConvertInputToBaseTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'convert_input_to_base'`.

- [ ] **Step 3: Implementasi** — tambahkan ke akhir `apps/uom/conversion.py`:

```python
def convert_input_to_base(item, input_uom, input_qty, input_price):
    """Konversi (qty, harga) dalam input_uom ke base/stock_uom item.

    Return (qty_base, unit_price_base). Bila input_uom None → passthrough.
    total_value (input_qty * input_price) dipertahankan sebagai sumber kebenaran;
    unit_price_base diturunkan dari total / qty_base.
    """
    input_qty = Decimal(str(input_qty))
    input_price = Decimal(str(input_price))
    if input_uom is None:
        return input_qty, input_price
    qty_base = to_stock_uom(input_qty, input_uom, item)
    total = input_qty * input_price
    unit_price_base = (total / qty_base) if qty_base else Decimal('0')
    return qty_base, unit_price_base
```

- [ ] **Step 4: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.uom.tests.ConvertInputToBaseTests -v 2`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/uom/conversion.py apps/uom/tests.py
git commit -m "feat(uom): convert_input_to_base helper untuk konversi di batas input"
```

---

## Task 5: Konversi UOM di Purchase (model + migrasi + view + template)

**Files:**
- Modify: `apps/purchase/models.py` (class `PurchaseItem`)
- Create: migrasi `apps/purchase/migrations/XXXX_purchaseitem_input_uom.py` (via makemigrations)
- Modify: `apps/purchase/views.py` (dua blok `PurchaseItem.objects.create`, sekitar 1438 & 1486; +helper data satuan)
- Modify: `templates/purchase/purchase_form.html`
- Test: `apps/purchase/tests.py`

- [ ] **Step 1: Tambah field model** di `apps/purchase/models.py`, class `PurchaseItem` (setelah field `warehouse`, sekitar baris 551):

```python
    input_uom = models.ForeignKey(
        'uom.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='purchase_items_input',
        verbose_name='Satuan Input',
    )
    input_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Qty Input (satuan asli)',
    )
```

- [ ] **Step 2: Buat migrasi**

Run: `python manage.py makemigrations purchase`
Expected: file migrasi baru `XXXX_purchaseitem_input_uom.py` (2 field ditambahkan).

- [ ] **Step 3: Tulis test yang gagal** — tambahkan ke `apps/purchase/tests.py` (ikuti pola setup transaksi yang sudah ada di file tsb; gunakan util pembuatan purchase via view POST atau service):

```python
from decimal import Decimal
from apps.uom.conversion import convert_input_to_base
from apps.uom.models import UnitOfMeasure, ItemUOM


class PurchaseUomConversionTests(TestCase):
    """Konversi diterapkan lewat helper; ledger tetap dalam base."""
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        from apps.purchase.models import ItemMasterPurchase
        self.item = ItemMasterPurchase.objects.create(
            nama='Beli', tipe_item='ITM', stock_uom=self.pcs)
        self.ctn = UnitOfMeasure.objects.create(
            kode='ctn-p', nama='Carton', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.item, uom=self.ctn, qty_in_stock_uom=Decimal('24'))

    def test_helper_carton_purchase(self):
        qty, price = convert_input_to_base(self.item, self.ctn, Decimal('10'), Decimal('24000'))
        self.assertEqual(qty, Decimal('240'))
        self.assertEqual(price, Decimal('1000'))
```

> Test regresi end-to-end (POST form purchase menghasilkan `quantity` base) ditulis mengikuti helper pembuatan purchase yang sudah ada di `apps/purchase/tests.py`. Bila belum ada, verifikasi via helper `convert_input_to_base` (unit-level) sudah cukup untuk mengunci logika konversi; integrasi view diverifikasi di Step 7 (manual/regresi).

- [ ] **Step 4: Jalankan test, pastikan LULUS** (field + migrasi + helper)

Run: `python manage.py test apps.purchase.tests.PurchaseUomConversionTests -v 2`
Expected: PASS

- [ ] **Step 5: Tambah helper data satuan** di `apps/purchase/views.py` (dekat `_get_warehouses_data`, sekitar baris 93):

```python
def _get_item_uoms_data(kind: str = 'purchase') -> dict:
    """Map item_id -> daftar satuan valid untuk selector di form transaksi.

    kind='purchase' → default purchase_uom; kind='sales' → default sales_uom.
    Tiap item: stock_uom + (purchase/sales)_uom + semua ItemUOM.uom.
    """
    from apps.purchase.models import ItemMasterPurchase
    from apps.uom.models import ItemUOM
    result: dict = {}
    items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']
    ).select_related('stock_uom', 'purchase_uom', 'sales_uom')
    iu_map: dict = {}
    for iu in ItemUOM.objects.select_related('uom'):
        iu_map.setdefault(iu.item_id, []).append(iu.uom)
    for it in items:
        seen, opts = set(), []
        default = it.purchase_uom if kind == 'purchase' else it.sales_uom
        for u in [it.stock_uom, default, *iu_map.get(it.pk, [])]:
            if u is not None and u.pk not in seen:
                seen.add(u.pk)
                opts.append({'id': u.pk, 'kode': u.kode, 'nama': u.nama})
        default_id = default.pk if default else (it.stock_uom_id or '')
        result[it.pk] = {'options': opts, 'default_id': default_id}
    return result
```

- [ ] **Step 6: Terapkan konversi di kedua blok create** `PurchaseItem` (baris ~1438 dan ~1486). Di setiap blok, sebelum `PurchaseItem.objects.create(...)`, sisipkan:

```python
                    from apps.uom.conversion import convert_input_to_base
                    from apps.uom.models import UnitOfMeasure
                    input_uom_id = item_data.get('input_uom_id') or None
                    input_uom = UnitOfMeasure.objects.filter(pk=input_uom_id).first() if input_uom_id else None
                    input_qty_raw = Decimal(str(item_data['quantity']))
                    qty_base, unit_price_base = convert_input_to_base(
                        pi_item_obj := __import__('apps.purchase.models', fromlist=['ItemMasterPurchase']).ItemMasterPurchase.objects.get(pk=item_data['item_id']),
                        input_uom, input_qty_raw, Decimal(str(item_data['unit_price'])),
                    )
```

> **Catatan implementasi (bersihkan saat coding):** jangan pakai `__import__`/walrus seperti di atas — itu hanya penanda. Yang benar: import `ItemMasterPurchase` di atas file (sudah ada), ambil objek item sekali, panggil `convert_input_to_base(item_obj, input_uom, input_qty_raw, unit_price_input)`. Lalu pada `PurchaseItem.objects.create(...)` ganti:
> - `quantity=Decimal(str(item_data['quantity']))` → `quantity=qty_base`
> - `unit_price=Decimal(str(item_data['unit_price']))` → `unit_price=unit_price_base`
> - tambah: `input_uom=input_uom,` dan `input_qty=input_qty_raw,`

Bentuk final tiap blok:

```python
                    input_uom_id = item_data.get('input_uom_id') or None
                    input_uom = UnitOfMeasure.objects.filter(pk=input_uom_id).first() if input_uom_id else None
                    item_obj = ItemMasterPurchase.objects.get(pk=item_data['item_id'])
                    input_qty_raw = Decimal(str(item_data['quantity']))
                    qty_base, unit_price_base = convert_input_to_base(
                        item_obj, input_uom, input_qty_raw, Decimal(str(item_data['unit_price'])))
                    PurchaseItem.objects.create(
                        purchase_eb=eb_group,
                        item_id=item_data['item_id'],
                        sub_transaction_type_id=item_data['sub_transaction_type_id'],
                        coa_account_id=item_data['coa_account_id'],
                        offset_coa_account_id=item_data['offset_coa_account_id'],
                        quantity=qty_base,
                        unit_price=unit_price_base,
                        input_uom=input_uom,
                        input_qty=input_qty_raw,
                        metode_alokasi_biaya=item_data.get('metode_alokasi_biaya', ''),
                        lead_time_days=item_data.get('lead_time_days') or None,
                        ordering_cost=Decimal(str(item_data['ordering_cost'])) if item_data.get('ordering_cost') else None,
                        holding_cost_pct=Decimal(str(item_data['holding_cost_pct'])) if item_data.get('holding_cost_pct') else None,
                        moq=Decimal(str(item_data['moq'])) if item_data.get('moq') else None,
                        target_turnover=Decimal(str(item_data['target_turnover'])) if item_data.get('target_turnover') else None,
                        warehouse_id=wh_id,
                    )
```

Tambahkan import di atas file `apps/purchase/views.py`: `from apps.uom.conversion import convert_input_to_base` dan `from apps.uom.models import UnitOfMeasure` (pastikan `ItemMasterPurchase` sudah terimport).

- [ ] **Step 7: Kirim data satuan ke context** — di ketiga tempat context purchase form dibangun (baris ~560, ~638, ~1352), tambahkan key:

```python
        'item_uoms_json': safe_json(_get_item_uoms_data('purchase')),
```

- [ ] **Step 8: Tambah kolom Satuan di template** `templates/purchase/purchase_form.html`:
  1. Baca data: dekat baris 467 (`var WAREHOUSES = ...`), tambah:
     ```javascript
     var ITEM_UOMS = {{ item_uoms_json|default:"{}"|safe }};
     ```
  2. Helper opsi satuan (dekat `warehouseOptions`, baris ~506):
     ```javascript
     function uomOptions(itemId, selected) {
       var info = ITEM_UOMS[itemId]; if (!info) return '';
       var sel = selected || info.default_id;
       return info.options.map(function (o) {
         return '<option value="' + o.id + '"' + (String(o.id) === String(sel) ? ' selected' : '') + '>' + o.kode + '</option>';
       }).join('');
     }
     ```
  3. Header kolom: dekat baris 735 (`'<th style="width:18%">Harga Satuan</th>'`), tambahkan sebelum/di sisi kolom Qty:
     ```javascript
     '<th style="width:8%">Satuan</th>' +
     ```
  4. Sel per baris (dekat pembuatan input Gudang, baris ~866), tambahkan sel:
     ```javascript
     '<div><label style="color:var(--ni-text-muted);font-size:0.75rem;">Satuan</label><select id="' + rid + '_uom" class="ni-purchase-input uom-select">' + uomOptions(rowItemId, prefill ? (prefill.input_uom_id || '') : '') + '</select></div>' +
     ```
     `rowItemId` = id item baris tsb (ikuti variabel yang sudah dipakai untuk `warehouseOptions(rowLv1Id, ...)`; jika perlu, isi ulang `#rid_uom` saat item baris berubah, di handler yang sama yang mengisi ulang warehouse).
  5. Kumpulkan saat submit (dekat baris 1464, tempat `warehouse_id` dikumpulkan):
     ```javascript
     input_uom_id: (document.getElementById(rid + '_uom') || {}).value || '',
     ```
  6. Prefill saat edit: di view (baris ~619 tempat `warehouse_id` di-serialize untuk prefill), tambahkan `'input_uom_id': pi.input_uom_id or ''`.

- [ ] **Step 9: Verifikasi regresi manual** — jalankan seluruh test purchase:

Run: `python manage.py test apps.purchase -v 1`
Expected: PASS semua (transaksi lama tanpa `input_uom` tetap hijau).

- [ ] **Step 10: Commit**

```bash
git add apps/purchase/models.py apps/purchase/migrations/ apps/purchase/views.py \
        templates/purchase/purchase_form.html apps/purchase/tests.py
git commit -m "feat(purchase): konversi UOM per baris (input_uom/input_qty), ledger tetap base"
```

---

## Task 6: Konversi UOM di Sales

**Files:**
- Modify: `apps/sales/models.py` (class `SalesItem`)
- Create: migrasi via makemigrations
- Modify: `apps/sales/views.py` (blok `SalesItem.objects.create`, sekitar 1050; context ~363, ~447, ~1007, ~1136; prefill ~414)
- Modify: `templates/sales/sales_form.html`
- Test: `apps/sales/tests.py`

- [ ] **Step 1: Tambah field model** di `apps/sales/models.py`, class `SalesItem` (setelah field `warehouse`, sekitar baris 267):

```python
    input_uom = models.ForeignKey(
        'uom.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='sales_items_input',
        verbose_name='Satuan Input',
    )
    input_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Qty Input (satuan asli)',
    )
```

- [ ] **Step 2: Buat migrasi**

Run: `python manage.py makemigrations sales`
Expected: migrasi baru dengan 2 field.

- [ ] **Step 3: Tulis test yang gagal** — tambahkan ke `apps/sales/tests.py`:

```python
from decimal import Decimal
from apps.uom.conversion import convert_input_to_base
from apps.uom.models import UnitOfMeasure, ItemUOM


class SalesUomConversionTests(TestCase):
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        from apps.purchase.models import ItemMasterPurchase
        self.item = ItemMasterPurchase.objects.create(
            nama='Jual', tipe_item='FG', stock_uom=self.pcs)
        self.box = UnitOfMeasure.objects.create(
            kode='box-s', nama='Box', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.item, uom=self.box, qty_in_stock_uom=Decimal('12'))

    def test_helper_box_sale(self):
        qty, price = convert_input_to_base(self.item, self.box, Decimal('3'), Decimal('120000'))
        self.assertEqual(qty, Decimal('36'))     # 3 * 12
        self.assertEqual(price, Decimal('10000'))  # 360.000 / 36
```

- [ ] **Step 4: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.sales.tests.SalesUomConversionTests -v 2`
Expected: PASS

- [ ] **Step 5: Terapkan konversi di view** `apps/sales/views.py`, blok `SalesItem.objects.create` (baris ~1050). **Hanya untuk item satuan (non-bulk)** — item bulk tetap `quantity=Decimal('0')` (value-based, tak dikonversi). Sisipkan sebelum create:

```python
                    from apps.uom.conversion import convert_input_to_base
                    from apps.uom.models import UnitOfMeasure
                    from apps.purchase.models import ItemMasterPurchase
                    input_uom_id = item_data.get('input_uom_id') or None
                    input_uom = UnitOfMeasure.objects.filter(pk=input_uom_id).first() if input_uom_id else None
                    if is_bulk:
                        qty_base = Decimal('0')
                        input_qty_raw = None
                    else:
                        item_obj = ItemMasterPurchase.objects.get(pk=item_data['item_id'])
                        input_qty_raw = Decimal(str(item_data['quantity']))
                        qty_base, _price_base = convert_input_to_base(
                            item_obj, input_uom, input_qty_raw,
                            Decimal(str(item_data.get('selling_price') or '0')))
```

Lalu pada `SalesItem.objects.create(...)`:
- ganti `quantity=Decimal('0') if is_bulk else Decimal(str(item_data['quantity']))` → `quantity=qty_base`
- tambah `input_uom=input_uom,` dan `input_qty=input_qty_raw,`

> Catatan: `selling_price` di Sales adalah harga jual per satuan input; untuk penjualan HPP dihitung dari FIFO (`process_sales_fifo`) berdasarkan `quantity` base, jadi cukup konversi `quantity`. `selling_price` yang ditampilkan tetap per satuan input (revenue = selling_price × input_qty). Verifikasi jurnal pendapatan memakai `selling_price × quantity_base`? Bila revenue saat ini `selling_price * quantity`, dan quantity kini base, maka `selling_price` juga harus per-base. Untuk konsistensi: simpan `selling_price` = harga per base = `(selling_price_input * input_qty) / qty_base`. Terapkan konversi harga jual analog `convert_input_to_base` (nilai kedua = unit_price_base) dan simpan sebagai `selling_price`.

Bentuk final (harga jual dikonversi ke per-base):

```python
                    if is_bulk:
                        qty_base = Decimal('0'); input_qty_raw = None
                        selling_base = Decimal(str(item_data.get('selling_price') or '0'))
                    else:
                        item_obj = ItemMasterPurchase.objects.get(pk=item_data['item_id'])
                        input_qty_raw = Decimal(str(item_data['quantity']))
                        qty_base, selling_base = convert_input_to_base(
                            item_obj, input_uom, input_qty_raw,
                            Decimal(str(item_data.get('selling_price') or '0')))
```
dan `selling_price=selling_base,` pada create.

- [ ] **Step 6: Helper data satuan + context** — pakai `_get_item_uoms_data('sales')` (diimport dari `apps.purchase.views`, sudah ada di sales views). Tambahkan ke keempat context (baris ~363, ~447, ~1007, ~1136):

```python
        'item_uoms_json': safe_json(_get_item_uoms_data('sales')),
```

Import di atas file: `from apps.purchase.views import ..., _get_item_uoms_data`.

- [ ] **Step 7: Kolom Satuan di template** `templates/sales/sales_form.html` — sama pola dengan Task 5 Step 8:
  1. `var ITEM_UOMS = {{ item_uoms_json|default:"{}"|safe }};` (dekat baris 307)
  2. `uomOptions(itemId, selected)` (dekat baris 356)
  3. Header `'<th class="col-satuan" style="width:6%">Satuan</th>'` (dekat baris 432)
  4. Sel per baris (dekat baris 570, kolom Gudang): `'<td class="item-field-td"><select id="' + rid + '_uom" class="ni-sales-input uom-select">' + uomOptions(ebItemId, prefill ? (prefill.input_uom_id || '') : '') + '</select></td>'`
  5. Submit (dekat baris 1085): `input_uom_id: document.getElementById(rid + '_uom') ? document.getElementById(rid + '_uom').value : '',`
  6. Prefill (view ~414): `'input_uom_id': si.input_uom_id or ''`

- [ ] **Step 8: Verifikasi regresi**

Run: `python manage.py test apps.sales -v 1`
Expected: PASS semua.

- [ ] **Step 9: Commit**

```bash
git add apps/sales/models.py apps/sales/migrations/ apps/sales/views.py \
        templates/sales/sales_form.html apps/sales/tests.py
git commit -m "feat(sales): konversi UOM per baris item satuan (harga & qty ke base)"
```

---

## Task 7: Konversi UOM di Manufacturing (BOM + Production)

**Files:**
- Modify: `apps/manufacturing/models.py` (class `BOMLine`, class `ProductionOrder`)
- Create: migrasi via makemigrations
- Modify: `apps/manufacturing/forms.py` (BOM line + production order)
- Modify: template BOM form & production form
- Test: `apps/manufacturing/tests.py`

Prinsip: `BOMLine.qty_required` dan `ProductionOrder.qty_produced` tetap **base** (otoritatif). Konversi hanya saat simpan form. `get_bom_preview`/`_simulate_fifo_cost`/`process_production` **tidak diubah**.

- [ ] **Step 1: Tambah field model** di `apps/manufacturing/models.py`:

`BOMLine` (setelah `qty_required`, ~baris 76):
```python
    input_uom = models.ForeignKey(
        'uom.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='bom_lines_input',
        verbose_name='Satuan Input RM',
    )
    input_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Qty Input per Unit FG',
    )
```

`ProductionOrder` (setelah `qty_produced`, ~baris 141):
```python
    input_uom = models.ForeignKey(
        'uom.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='production_orders_input',
        verbose_name='Satuan Input FG',
    )
    input_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Qty Input (satuan asli)',
    )
```

- [ ] **Step 2: Buat migrasi**

Run: `python manage.py makemigrations manufacturing`
Expected: migrasi baru dengan field di kedua model.

- [ ] **Step 3: Tulis test yang gagal** — tambahkan ke `apps/manufacturing/tests.py`:

```python
from decimal import Decimal
from apps.uom.conversion import convert_input_to_base
from apps.uom.models import UnitOfMeasure, ItemUOM


class ManufacturingUomTests(TestCase):
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        from apps.purchase.models import ItemMasterPurchase
        self.rm = ItemMasterPurchase.objects.create(
            nama='RM-A', tipe_item='RM', stock_uom=self.pcs)
        self.ctn = UnitOfMeasure.objects.create(
            kode='ctn-m', nama='Carton', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.rm, uom=self.ctn, qty_in_stock_uom=Decimal('24'))

    def test_bom_qty_converts_to_base(self):
        # 1 unit FG butuh 2 carton RM → 48 pcs base
        qty_base, _ = convert_input_to_base(self.rm, self.ctn, Decimal('2'), Decimal('0'))
        self.assertEqual(qty_base, Decimal('48'))
```

- [ ] **Step 4: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.manufacturing.tests.ManufacturingUomTests -v 2`
Expected: PASS

- [ ] **Step 5: Terapkan konversi di form BOM** `apps/manufacturing/forms.py`. Pada form/formset yang menyimpan `BOMLine`, di `save`/`clean` konversi `input_qty` (dalam `input_uom`) ke `qty_required` base:

```python
# dalam metode save BOMLine form (atau di view yang membuat BOMLine):
from apps.uom.conversion import convert_input_to_base
input_uom = self.cleaned_data.get('input_uom')
input_qty = self.cleaned_data.get('input_qty') or self.cleaned_data.get('qty_required')
qty_base, _ = convert_input_to_base(
    self.cleaned_data['raw_material'], input_uom, input_qty, Decimal('0'))
instance.qty_required = qty_base
instance.input_uom = input_uom
instance.input_qty = input_qty
```

> Sesuaikan dengan cara BOMLine dibuat saat ini (ModelForm/formset atau parsing manual di view). Bila lewat view (mirip purchase), sisipkan konversi sebelum `BOMLine.objects.create(...)` dan set `qty_required=qty_base`, `input_uom=...`, `input_qty=...`.

- [ ] **Step 6: Terapkan konversi di Production Order** — di form/view yang membuat `ProductionOrder`, konversi `qty_produced`:

```python
from apps.uom.conversion import convert_input_to_base
fg_item = production_order.bom.finished_good   # nama FK FG pada BillOfMaterials — verifikasi
input_uom = cleaned.get('input_uom')
input_qty = cleaned.get('input_qty') or cleaned.get('qty_produced')
qty_base, _ = convert_input_to_base(fg_item, input_uom, input_qty, Decimal('0'))
# simpan: qty_produced = qty_base; input_uom; input_qty
```

> Verifikasi nama FK finished good di `BillOfMaterials` (buka `apps/manufacturing/models.py` bagian `BillOfMaterials`). Ganti `finished_good` bila berbeda.

- [ ] **Step 7: Tambah pilih Satuan di template BOM & production form** (default `raw_material.purchase_uom`/`stock_uom` untuk RM; `fg.stock_uom` untuk FG). Ikuti pola select yang sudah dipakai form manufacturing (`forms.py:76` widget Select `ni-input`).

- [ ] **Step 8: Verifikasi regresi produksi**

Run: `python manage.py test apps.manufacturing -v 1`
Expected: PASS semua (BOM/produksi lama tanpa `input_uom` menghasilkan biaya identik karena `qty_required`/`qty_produced` tetap base).

- [ ] **Step 9: Commit**

```bash
git add apps/manufacturing/models.py apps/manufacturing/migrations/ apps/manufacturing/forms.py \
        apps/manufacturing/tests.py apps/manufacturing/templates/
git commit -m "feat(manufacturing): satuan input di BOM & production order (qty tetap base)"
```

---

## Task 8: Stock Ledger viewer (C5)

**Files:**
- Modify: `apps/inventory/views.py`, `apps/inventory/urls.py`
- Create: `templates/inventory/stock_ledger.html`
- Modify: `templates/base.html`
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/inventory/tests.py`:

```python
from apps.inventory.ledger import record_inflow


class StockLedgerViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='sl@example.com', password='pw123456', name='S')
        self.client.force_login(self.user)
        self.eb = EntitasBisnis.objects.create(nama='Biz L', status_aktif=True)
        from apps.uom.models import UnitOfMeasure
        from apps.purchase.models import ItemMasterPurchase
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(nama='Led', tipe_item='ITM', stock_uom=pcs)
        from datetime import date
        record_inflow(self.item, self.eb, None, None,
                      Decimal('100'), Decimal('500'), date.today(), 'purchase_in')

    def test_ledger_renders_movement_and_balance(self):
        resp = self.client.get(reverse('inventory:stock_ledger'), {'item': self.item.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '100')   # qty masuk terlihat
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.inventory.tests.StockLedgerViewTests -v 2`
Expected: FAIL — `NoReverseMatch` `inventory:stock_ledger`.

- [ ] **Step 3: Tambah view** di `apps/inventory/views.py`:

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

    qs = StockMovement.objects.select_related('item', 'entitas_bisnis', 'warehouse')
    if item_id:
        qs = qs.filter(item_id=item_id)
    if wh_id:
        qs = qs.filter(warehouse_id=wh_id)
    if tgl_dari:
        qs = qs.filter(tanggal__gte=tgl_dari)
    if tgl_sampai:
        qs = qs.filter(tanggal__lte=tgl_sampai)
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
    })
```

- [ ] **Step 4: Tambah url**

```python
    path('ledger/', views.stock_ledger, name='stock_ledger'),
```

- [ ] **Step 5: Buat template** `templates/inventory/stock_ledger.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <h1 class="ni-page__title">{{ title }}</h1>
  <form method="get" class="ni-filter">
    <select name="item" class="ni-input">
      <option value="">— Semua Item —</option>
      {% for it in items %}<option value="{{ it.pk }}" {% if item_filter == it.pk|stringformat:'s' %}selected{% endif %}>{{ it.item_id }} — {{ it.nama }}</option>{% endfor %}
    </select>
    <select name="warehouse" class="ni-input">
      <option value="">— Semua Gudang —</option>
      {% for w in warehouses %}<option value="{{ w.pk }}" {% if wh_filter == w.pk|stringformat:'s' %}selected{% endif %}>{{ w.kode }}</option>{% endfor %}
    </select>
    <input type="date" name="tanggal_dari" value="{{ tanggal_dari }}" class="ni-input">
    <input type="date" name="tanggal_sampai" value="{{ tanggal_sampai }}" class="ni-input">
    <button type="submit" class="ni-btn ni-btn--primary">Filter</button>
  </form>
  <table class="ni-table">
    <thead><tr><th>Tanggal</th><th>Item</th><th>Jenis</th><th>Gudang</th><th>Qty</th><th>Biaya/Unit</th><th>Saldo</th></tr></thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>{{ r.mv.tanggal }}</td>
        <td>{{ r.mv.item.item_id }}</td>
        <td>{{ r.mv.get_movement_type_display }}</td>
        <td>{{ r.mv.warehouse.kode|default:'—' }}</td>
        <td>{{ r.mv.qty }}</td>
        <td>{{ r.mv.unit_cost }}</td>
        <td>{{ r.saldo }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="7">Tidak ada pergerakan.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

- [ ] **Step 6: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.inventory.tests.StockLedgerViewTests -v 2`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add apps/inventory/views.py apps/inventory/urls.py \
        templates/inventory/stock_ledger.html apps/inventory/tests.py
git commit -m "feat(inventory): Buku Persediaan (Stock Ledger) read-only dari StockMovement"
```

---

## Task 9: Kartu Stok per item (C5) + menu

**Files:**
- Modify: `apps/inventory/views.py`, `apps/inventory/urls.py`
- Create: `templates/inventory/stock_card.html`
- Modify: `templates/base.html`
- Test: `apps/inventory/tests.py`

- [ ] **Step 1: Tulis test yang gagal** — tambahkan ke `apps/inventory/tests.py`:

```python
class StockCardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='sc@example.com', password='pw123456', name='C')
        self.client.force_login(self.user)
        self.eb = EntitasBisnis.objects.create(nama='Biz C', status_aktif=True)
        from apps.uom.models import UnitOfMeasure
        from apps.purchase.models import ItemMasterPurchase
        from apps.inventory.ledger import record_inflow
        from datetime import date
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(nama='Card', tipe_item='ITM', stock_uom=pcs)
        record_inflow(self.item, self.eb, None, None,
                      Decimal('50'), Decimal('200'), date.today(), 'purchase_in')

    def test_card_shows_active_layers(self):
        resp = self.client.get(reverse('inventory:stock_card'), {'item': self.item.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '50')  # layer remaining_qty
```

- [ ] **Step 2: Jalankan test, pastikan GAGAL**

Run: `python manage.py test apps.inventory.tests.StockCardViewTests -v 2`
Expected: FAIL — `NoReverseMatch`.

- [ ] **Step 3: Tambah view** di `apps/inventory/views.py`:

```python
@login_required
def stock_card(request: HttpRequest) -> HttpResponse:
    """Kartu stok per item: layer inflow aktif + saldo per gudang (read-only)."""
    from django.db.models import Sum
    from apps.inventory.models import StockMovement
    from apps.purchase.models import ItemMasterPurchase
    item_id = request.GET.get('item', '')
    item = None
    layers = []
    saldo_per_wh = []
    if item_id:
        item = get_object_or_404(ItemMasterPurchase, pk=item_id)
        layers = StockMovement.objects.filter(
            item=item, remaining_qty__gt=0).select_related(
            'entitas_bisnis', 'warehouse').order_by('tanggal', 'created_at')
        saldo_per_wh = (
            StockMovement.objects.filter(item=item)
            .values('warehouse__kode')
            .annotate(saldo=Sum('qty')).order_by('warehouse__kode')
        )
    return render(request, 'inventory/stock_card.html', {
        'title': 'Kartu Stok', 'item': item, 'layers': layers,
        'saldo_per_wh': saldo_per_wh,
        'items': ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']).order_by('item_id'),
        'item_filter': item_id,
    })
```

- [ ] **Step 4: Tambah url**

```python
    path('kartu-stok/', views.stock_card, name='stock_card'),
```

- [ ] **Step 5: Buat template** `templates/inventory/stock_card.html`:

```html
{% extends 'base.html' %}
{% block content %}
<div class="ni-page">
  <h1 class="ni-page__title">{{ title }}</h1>
  <form method="get" class="ni-filter">
    <select name="item" class="ni-input" onchange="this.form.submit()">
      <option value="">— Pilih Item —</option>
      {% for it in items %}<option value="{{ it.pk }}" {% if item_filter == it.pk|stringformat:'s' %}selected{% endif %}>{{ it.item_id }} — {{ it.nama }}</option>{% endfor %}
    </select>
  </form>
  {% if item %}
  <h2 class="ni-section-title">Saldo per Gudang</h2>
  <table class="ni-table">
    <thead><tr><th>Gudang</th><th>Saldo</th></tr></thead>
    <tbody>
      {% for s in saldo_per_wh %}<tr><td>{{ s.warehouse__kode|default:'—' }}</td><td>{{ s.saldo }}</td></tr>{% empty %}<tr><td colspan="2">—</td></tr>{% endfor %}
    </tbody>
  </table>
  <h2 class="ni-section-title">Layer Inflow Aktif (FIFO)</h2>
  <table class="ni-table">
    <thead><tr><th>Tanggal</th><th>Entitas</th><th>Gudang</th><th>Sisa Qty</th><th>Biaya/Unit</th></tr></thead>
    <tbody>
      {% for l in layers %}
      <tr><td>{{ l.tanggal }}</td><td>{{ l.entitas_bisnis.nama }}</td><td>{{ l.warehouse.kode|default:'—' }}</td><td>{{ l.remaining_qty }}</td><td>{{ l.unit_cost }}</td></tr>
      {% empty %}
      <tr><td colspan="5">Tidak ada layer aktif.</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 6: Jalankan test, pastikan LULUS**

Run: `python manage.py test apps.inventory.tests.StockCardViewTests -v 2`
Expected: PASS

- [ ] **Step 7: Tambah menu** di `templates/base.html` submenu Inventory:

```html
          <a href="{% url 'inventory:stock_ledger' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Buku Persediaan</span>
          </a>
          <a href="{% url 'inventory:stock_card' %}" class="ni-nav-link">
            <span class="ni-nav-link__text">Kartu Stok</span>
          </a>
```

- [ ] **Step 8: Commit**

```bash
git add apps/inventory/views.py apps/inventory/urls.py \
        templates/inventory/stock_card.html templates/base.html apps/inventory/tests.py
git commit -m "feat(inventory): Kartu Stok per item + menu Buku Persediaan/Kartu Stok"
```

---

## Task 10: Verifikasi menyeluruh & regresi

**Files:** —

- [ ] **Step 1: Jalankan seluruh test suite**

Run: `python manage.py test -v 1`
Expected: PASS semua. Bila ada regresi di purchase/sales/manufacturing, periksa jalur `input_uom` kosong harus identik dengan sebelum perubahan.

- [ ] **Step 2: Cek migrasi konsisten**

Run: `python manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 3: Smoke test manual (opsional, via `/run` atau runserver)** — buat 1 gudang, 1 konversi (carton=24pcs), buat pembelian 10 carton, cek Kartu Stok menunjukkan 240 pcs, jual sebagian, cek Buku Persediaan saldo berjalan turun benar.

- [ ] **Step 4: Commit akhir bila ada penyesuaian**

```bash
git add -A
git commit -m "test: verifikasi menyeluruh integrasi UOM & Stock Ledger"
```

---

## Catatan Implementasi Penting

1. **Regresi adalah gerbang utama.** Setiap task transaksi (5/6/7) harus menjaga jalur `input_uom=None` menghasilkan angka identik. Jangan lanjut bila test lama merah.
2. **Konversi harga.** Selalu turunkan `unit_price_base`/`selling_base` dari `total / qty_base` (via `convert_input_to_base`) agar total yang dilihat user tetap sumber kebenaran; hindari pembulatan ganda.
3. **Item bulk (RMB/FGB/ITMB)** memakai konvensi value-based (qty=0/1). Konversi UOM tidak diterapkan ke item bulk — biarkan jalur bulk apa adanya.
4. **`_resolve_eb_lv1_ids([], user)`** — verifikasi semantik return saat argumen kosong sebelum dipakai untuk filter gudang (Task 2 Step 4).
5. **Nama FK finished good** di `BillOfMaterials` (Task 7 Step 6) wajib diverifikasi dari model sebelum coding.
6. **Template transaksi** dibangun via JS row-builder; sisipkan kolom Satuan mengikuti anchor baris yang disebut, dan pastikan `#rid_uom` diisi ulang saat item baris berubah (handler yang sama yang mengisi ulang warehouse per baris).
