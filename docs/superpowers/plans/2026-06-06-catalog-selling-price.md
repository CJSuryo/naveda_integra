# Catalog & Harga Jual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Catalog management page to `pos_catalog` app — selling prices, display config, and catalog logs per EntitasBisnis — plus rename `unit_price` label to `unit_cost` in inventory.

**Architecture:** `CatalogItem` and `CatalogItemLog` models in `apps/pos_catalog/`. Catalog list page uses AJAX category filter + inline row editing (one row at a time, confirm-on-discard). Catalog logs page is paginated. Entry points on EB list page and setup wizard. `unit_price` → `unit_cost` is a verbose_name change only — no DB column rename.

**Tech Stack:** Django 6.x, Django TestCase, `FormData`-based AJAX, `ni-*` CSS classes, `pos_config_manage` permission gate.

---

## File Map

| File | Change |
|---|---|
| `apps/inventory/models.py` | `unit_price` verbose_name `'Unit Price'` → `'Unit Cost'` |
| `apps/inventory/forms.py` | label override for `unit_price` → `'Unit Cost'` |
| `apps/inventory/admin.py` | no change needed (uses verbose_name automatically) |
| `apps/pos_catalog/models.py` | Add `CatalogItem`, `CatalogItemLog` |
| `apps/pos_catalog/views.py` | Add `catalog_list`, `catalog_items_ajax`, `catalog_upsert`, `catalog_logs` |
| `apps/pos_catalog/urls.py` | Add 4 URL patterns |
| `apps/pos_catalog/admin.py` | Register `CatalogItem`, `CatalogItemLog` |
| `apps/pos_catalog/tests/test_catalog.py` | New — model + view tests |
| `templates/pos_catalog/catalog_list.html` | New — main catalog page with JS |
| `templates/pos_catalog/_catalog_rows.html` | New — AJAX partial table rows |
| `templates/pos_catalog/catalog_logs.html` | New — catalog logs page |
| `apps/entitas_bisnis/views.py` | Add `catalog_ok` to `_compute_wizard_checks` |
| `templates/entitas_bisnis/list.html` | Add Catalog button to lv1 row |
| `templates/entitas_bisnis/setup_wizard.html` | Add catalog_ok check (item 7) |

---

### Task 1: unit_price → unit_cost label rename

**Files:**
- Modify: `apps/inventory/models.py`
- Modify: `apps/inventory/forms.py`

- [ ] **Step 1: Update verbose_name in model**

In `apps/inventory/models.py`, line 100, change:
```python
unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Unit Price')
```
to:
```python
unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Unit Cost')
```

- [ ] **Step 2: Override label in form**

In `apps/inventory/forms.py`, in `InventoryRecordForm.__init__`, add after `super().__init__(*args, **kwargs)`:
```python
        self.fields['unit_price'].label = 'Unit Cost'
```

- [ ] **Step 3: Make and run migration**

```
python manage.py makemigrations inventory --name="alter_inventoryrecord_unit_price_verbose_name"
python manage.py migrate
```
Expected: `Applying inventory.0002_alter_inventoryrecord_unit_price_verbose_name... OK`

- [ ] **Step 4: Verify**

```
python manage.py check
```
Expected: 0 issues.

- [ ] **Step 5: Commit**

```bash
git add apps/inventory/models.py apps/inventory/forms.py apps/inventory/migrations/0002_alter_inventoryrecord_unit_price_verbose_name.py
git commit -m "feat(inventory): rename unit_price label to Unit Cost"
```

---

### Task 2: CatalogItem + CatalogItemLog models

**Files:**
- Modify: `apps/pos_catalog/models.py`
- Modify: `apps/pos_catalog/admin.py`
- Create: `apps/pos_catalog/tests/test_catalog.py`

- [ ] **Step 1: Write failing tests**

Create `apps/pos_catalog/tests/test_catalog.py`:
```python
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import KategoriItem, ItemMasterPurchase
from pos_catalog.models import CatalogItem, CatalogItemLog
from apps.accounts.models import User


def make_eb(nama='Kafe Test'):
    tipe = TipeEntitas.objects.create(nama=f'FnB-{nama}')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe, relasi='pelanggan')


def make_item(nama='Kopi', tipe='FG'):
    kat, _ = KategoriItem.objects.get_or_create(nama=f'Kat-{tipe}', defaults={'tipe_item': tipe})
    return ItemMasterPurchase.objects.create(nama=nama, tipe_item=tipe, kategori=kat)


class CatalogItemModelTest(TestCase):
    def setUp(self):
        self.eb = make_eb()
        self.item = make_item()

    def test_create_catalog_item(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb,
            item=self.item,
            selling_price=Decimal('15000'),
        )
        self.assertEqual(ci.is_active, True)
        self.assertEqual(ci.display_order, 1)

    def test_str_uses_display_name_if_set(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item,
            selling_price=Decimal('10000'), display_name='Kopi Susu',
        )
        self.assertIn('Kopi Susu', str(ci))

    def test_str_falls_back_to_item_nama(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item,
            selling_price=Decimal('10000'),
        )
        self.assertIn(self.item.nama, str(ci))

    def test_unique_together_eb_item(self):
        CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('10000'),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CatalogItem.objects.create(
                entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('20000'),
            )

    def test_display_order_auto_increments(self):
        item2 = make_item('Teh', 'FG')
        ci1 = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('10000'),
        )
        ci2 = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=item2, selling_price=Decimal('8000'),
        )
        self.assertEqual(ci1.display_order, 1)
        self.assertEqual(ci2.display_order, 2)


class CatalogItemLogTest(TestCase):
    def setUp(self):
        self.eb = make_eb('LogEB')
        self.item = make_item('LogItem')
        self.ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('5000'),
        )

    def test_create_log(self):
        log = CatalogItemLog.objects.create(
            catalog_item=self.ci,
            field_name='selling_price',
            old_value='5000',
            new_value='6000',
        )
        self.assertEqual(log.catalog_item, self.ci)
        self.assertIsNone(log.changed_by)

    def test_log_cascade_delete(self):
        CatalogItemLog.objects.create(
            catalog_item=self.ci, field_name='is_active',
            old_value='True', new_value='False',
        )
        self.ci.delete()
        self.assertEqual(CatalogItemLog.objects.count(), 0)
```

- [ ] **Step 2: Run tests (expect ImportError — models not defined)**

```
python manage.py test pos_catalog.tests.test_catalog -v 2 --keepdb
```
Expected: `ImportError: cannot import name 'CatalogItem' from 'pos_catalog.models'`

- [ ] **Step 3: Add models to `apps/pos_catalog/models.py`**

Append to `apps/pos_catalog/models.py`:
```python
from decimal import Decimal as _Decimal
from django.conf import settings
from django.db.models import Max


class CatalogItem(models.Model):
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        related_name='catalog_items',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='catalog_entries',
    )
    selling_price = models.DecimalField(max_digits=15, decimal_places=4)
    display_name = models.CharField(max_length=200, blank=True)
    display_order = models.IntegerField(default=0)
    product_image = models.ImageField(upload_to='catalog/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('entitas_bisnis', 'item')
        ordering = ['display_order', 'item__nama']
        verbose_name = 'Catalog Item'
        verbose_name_plural = 'Catalog Items'

    def __str__(self):
        name = self.display_name or self.item.nama
        return f'{name} — {self.entitas_bisnis.nama}'

    def save(self, *args, **kwargs):
        if not self.pk and self.display_order == 0:
            max_order = CatalogItem.objects.filter(
                entitas_bisnis=self.entitas_bisnis
            ).aggregate(m=Max('display_order'))['m']
            self.display_order = (max_order or 0) + 1
        super().save(*args, **kwargs)


class CatalogItemLog(models.Model):
    catalog_item = models.ForeignKey(
        CatalogItem, on_delete=models.CASCADE, related_name='logs'
    )
    field_name = models.CharField(max_length=50)
    old_value = models.TextField()
    new_value = models.TextField()
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='catalog_logs',
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Catalog Item Log'
        verbose_name_plural = 'Catalog Item Logs'

    def __str__(self):
        return f'{self.catalog_item} · {self.field_name} @ {self.changed_at}'
```

- [ ] **Step 4: Make and apply migration**

```
python manage.py makemigrations pos_catalog --name="add_catalogitem_catalogitemlog"
python manage.py migrate
```
Expected: `Applying pos_catalog.0003_add_catalogitem_catalogitemlog... OK`

- [ ] **Step 5: Register in admin**

Replace `apps/pos_catalog/admin.py` entirely:
```python
from django.contrib import admin
from .models import ModifierGroup, ModifierOption, ProductModifierGroup, CatalogItem, CatalogItemLog


admin.site.register(ModifierGroup)
admin.site.register(ModifierOption)
admin.site.register(ProductModifierGroup)


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ('item', 'entitas_bisnis', 'selling_price', 'is_active', 'display_order')
    list_select_related = ('item', 'entitas_bisnis')
    list_filter = ('is_active', 'entitas_bisnis')
    search_fields = ('item__nama', 'display_name')
    extra = 0


@admin.register(CatalogItemLog)
class CatalogItemLogAdmin(admin.ModelAdmin):
    list_display = ('catalog_item', 'field_name', 'old_value', 'new_value', 'changed_at', 'changed_by')
    list_select_related = ('catalog_item__item', 'changed_by')
    list_filter = ('field_name',)
    search_fields = ('catalog_item__item__nama',)
    readonly_fields = ('catalog_item', 'field_name', 'old_value', 'new_value', 'changed_at', 'changed_by')
```

- [ ] **Step 6: Run tests (expect pass)**

```
python manage.py test pos_catalog.tests.test_catalog.CatalogItemModelTest pos_catalog.tests.test_catalog.CatalogItemLogTest -v 2 --keepdb
```
Expected: 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/pos_catalog/models.py apps/pos_catalog/admin.py apps/pos_catalog/migrations/0003_add_catalogitem_catalogitemlog.py apps/pos_catalog/tests/test_catalog.py
git commit -m "feat(pos_catalog): add CatalogItem and CatalogItemLog models"
```

---

### Task 3: Catalog URL patterns + view stubs + view tests

**Files:**
- Modify: `apps/pos_catalog/urls.py`
- Modify: `apps/pos_catalog/views.py`
- Modify: `apps/pos_catalog/tests/test_catalog.py`

- [ ] **Step 1: Add view tests to `apps/pos_catalog/tests/test_catalog.py`**

Append to the file:
```python
from django.test import Client
from django.urls import reverse


class CatalogListViewTest(TestCase):
    def setUp(self):
        self.eb = make_eb('ViewEB')
        self.user = User.objects.create_user(email='cat@test.com', password='pass', name='Cat')
        self.client = Client()
        self.client.force_login(self.user)

    def test_catalog_list_returns_200(self):
        url = reverse('pos_catalog:catalog_list', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_catalog_list_404_unknown_eb(self):
        url = reverse('pos_catalog:catalog_list', args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_catalog_list_requires_login(self):
        self.client.logout()
        url = reverse('pos_catalog:catalog_list', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_catalog_items_ajax_returns_html(self):
        item = make_item('AjaxItem', 'FG')
        from apps.inventory.models import InventoryRecord
        import datetime
        InventoryRecord.objects.create(
            item=item, entitas_bisnis=self.eb,
            quantity=10, unit_price=5000,
            tanggal=datetime.date.today(),
        )
        url = reverse('pos_catalog:catalog_items_ajax', args=[self.eb.pk])
        resp = self.client.get(url, {'tipe_item': 'FG'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('html', data)
        self.assertIn('AjaxItem', data['html'])

    def test_catalog_items_ajax_empty_without_inventory(self):
        url = reverse('pos_catalog:catalog_items_ajax', args=[self.eb.pk])
        resp = self.client.get(url, {'tipe_item': 'FG'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('html', data)

    def test_catalog_upsert_creates_catalog_item(self):
        item = make_item('UpsertItem', 'RM')
        url = reverse('pos_catalog:catalog_upsert', args=[self.eb.pk])
        resp = self.client.post(url, {
            'item_id': item.pk,
            'selling_price': '12000',
            'display_name': 'Upsert Name',
            'display_order': '1',
            'is_active': 'true',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(CatalogItem.objects.filter(entitas_bisnis=self.eb, item=item).count(), 1)

    def test_catalog_upsert_writes_log_on_update(self):
        item = make_item('LogUpsertItem', 'FG')
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=item, selling_price=Decimal('5000'),
        )
        url = reverse('pos_catalog:catalog_upsert', args=[self.eb.pk])
        self.client.post(url, {
            'item_id': item.pk,
            'selling_price': '9000',
            'display_name': '',
            'display_order': str(ci.display_order),
            'is_active': 'true',
        })
        self.assertTrue(
            CatalogItemLog.objects.filter(
                catalog_item=ci, field_name='selling_price',
                old_value='5000', new_value='9000',
            ).exists()
        )

    def test_catalog_logs_returns_200(self):
        url = reverse('pos_catalog:catalog_logs', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 2: Run tests (expect fail — URLs not defined)**

```
python manage.py test pos_catalog.tests.test_catalog.CatalogListViewTest -v 2 --keepdb
```
Expected: `NoReverseMatch: Reverse for 'catalog_list' not found`

- [ ] **Step 3: Add URL patterns to `apps/pos_catalog/urls.py`**

```python
from django.urls import path
from . import views

app_name = 'pos_catalog'

urlpatterns = [
    path('<int:merchant_pk>/modifiers/', views.modifier_group_list, name='modifier_group_list'),
    path('<int:merchant_pk>/modifiers/create/', views.modifier_group_form, name='modifier_group_create'),
    path('<int:merchant_pk>/modifiers/<int:pk>/edit/', views.modifier_group_form, name='modifier_group_edit'),
    path('<int:merchant_pk>/modifiers/<int:group_pk>/options/', views.modifier_option_create, name='modifier_option_create'),
    # Catalog
    path('<int:eb_pk>/catalog/', views.catalog_list, name='catalog_list'),
    path('<int:eb_pk>/catalog/items/', views.catalog_items_ajax, name='catalog_items_ajax'),
    path('<int:eb_pk>/catalog/items/upsert/', views.catalog_upsert, name='catalog_upsert'),
    path('<int:eb_pk>/catalog/logs/', views.catalog_logs, name='catalog_logs'),
]
```

- [ ] **Step 4: Add the 4 catalog views to `apps/pos_catalog/views.py`**

Append to `apps/pos_catalog/views.py`:
```python
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import InventoryRecord
from .models import CatalogItem, CatalogItemLog


@login_required
def catalog_list(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    return render(request, 'pos_catalog/catalog_list.html', {'eb': eb})


@login_required
def catalog_items_ajax(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return JsonResponse({'error': 'forbidden'}, status=403)
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    tipe_item = request.GET.get('tipe_item', '')
    if not tipe_item:
        return JsonResponse({'html': ''})

    items = (
        ItemMasterPurchase.objects
        .filter(tipe_item=tipe_item, inventory_records__entitas_bisnis=eb)
        .distinct()
        .order_by('nama')
    )
    catalog_map = {
        ci.item_id: ci
        for ci in CatalogItem.objects.filter(entitas_bisnis=eb, item__in=items)
        .select_related('item')
    }
    rows = [{'item': item, 'catalog_item': catalog_map.get(item.pk)} for item in items]
    html = render_to_string(
        'pos_catalog/_catalog_rows.html',
        {'rows': rows, 'eb': eb},
        request=request,
    )
    return JsonResponse({'html': html})


@login_required
def catalog_upsert(request, eb_pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return JsonResponse({'error': 'forbidden'}, status=403)
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    item_id = request.POST.get('item_id')
    item = get_object_or_404(ItemMasterPurchase, pk=item_id)

    catalog_item, created = CatalogItem.objects.get_or_create(
        entitas_bisnis=eb, item=item,
        defaults={'selling_price': Decimal('0')},
    )

    TRACKED = ['selling_price', 'display_name', 'display_order', 'is_active']
    old_values = {f: str(getattr(catalog_item, f)) for f in TRACKED}

    try:
        catalog_item.selling_price = Decimal(request.POST.get('selling_price', '0'))
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid selling_price'}, status=400)

    catalog_item.display_name = request.POST.get('display_name', '')

    try:
        catalog_item.display_order = int(request.POST.get('display_order', catalog_item.display_order))
    except (ValueError, TypeError):
        pass

    catalog_item.is_active = request.POST.get('is_active', 'true').lower() == 'true'

    if 'product_image' in request.FILES:
        catalog_item.product_image = request.FILES['product_image']

    # Write logs for changed fields (skip on create — no prior state to diff)
    logs = []
    if not created:
        for field in TRACKED:
            new_val = str(getattr(catalog_item, field))
            if old_values[field] != new_val:
                logs.append(CatalogItemLog(
                    catalog_item=catalog_item,
                    field_name=field,
                    old_value=old_values[field],
                    new_value=new_val,
                    changed_by=request.user,
                ))
        if 'product_image' in request.FILES:
            logs.append(CatalogItemLog(
                catalog_item=catalog_item,
                field_name='product_image',
                old_value='(previous)',
                new_value=request.FILES['product_image'].name,
                changed_by=request.user,
            ))

    catalog_item.save()
    if logs:
        CatalogItemLog.objects.bulk_create(logs)

    return JsonResponse({
        'success': True,
        'item': {
            'id': catalog_item.pk,
            'display_name': catalog_item.display_name or catalog_item.item.nama,
            'selling_price': str(catalog_item.selling_price),
            'is_active': catalog_item.is_active,
            'display_order': catalog_item.display_order,
            'image_url': catalog_item.product_image.url if catalog_item.product_image else '',
        },
    })


@login_required
def catalog_logs(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    q = request.GET.get('q', '').strip()
    logs_qs = (
        CatalogItemLog.objects
        .filter(catalog_item__entitas_bisnis=eb)
        .select_related('catalog_item__item', 'changed_by')
        .order_by('-changed_at')
    )
    if q:
        logs_qs = logs_qs.filter(catalog_item__item__nama__icontains=q)
    paginator = Paginator(logs_qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'pos_catalog/catalog_logs.html', {
        'eb': eb, 'page': page, 'q': q,
    })
```

- [ ] **Step 5: Create placeholder templates so tests can render**

Create `templates/pos_catalog/catalog_list.html`:
```html
{% extends 'base.html' %}
{% block title %}Catalog — {{ eb.nama }}{% endblock %}
{% block content %}CATALOG PLACEHOLDER{% endblock %}
```

Create `templates/pos_catalog/_catalog_rows.html`:
```html
{% for row in rows %}
<tr data-item-id="{{ row.item.pk }}"
    data-catalog-id="{{ row.catalog_item.pk|default:'' }}">
  <td>{{ row.item.nama }}</td>
</tr>
{% empty %}
<tr><td colspan="8">Tidak ada item.</td></tr>
{% endfor %}
```

Create `templates/pos_catalog/catalog_logs.html`:
```html
{% extends 'base.html' %}
{% block title %}Catalog Logs — {{ eb.nama }}{% endblock %}
{% block content %}LOGS PLACEHOLDER{% endblock %}
```

- [ ] **Step 6: Run tests (expect pass)**

```
python manage.py test pos_catalog.tests.test_catalog -v 2 --keepdb
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/pos_catalog/urls.py apps/pos_catalog/views.py apps/pos_catalog/tests/test_catalog.py templates/pos_catalog/catalog_list.html templates/pos_catalog/_catalog_rows.html templates/pos_catalog/catalog_logs.html
git commit -m "feat(pos_catalog): add catalog views, URLs, and tests"
```

---

### Task 4: Full catalog_list.html template with inline edit JS

**Files:**
- Replace: `templates/pos_catalog/catalog_list.html`

- [ ] **Step 1: Write the full catalog list template**

Replace `templates/pos_catalog/catalog_list.html`:
```html
{% extends 'base.html' %}
{% block title %}Catalog — {{ eb.nama }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Catalog</h1>
    <p class="ni-page-header__subtitle">{{ eb.nama }}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'pos_catalog:catalog_logs' eb.pk %}" class="ni-btn ni-btn--secondary">
      <i data-lucide="history"></i> Catalog Logs
    </a>
  </div>
</div>

{% for msg in messages %}
<div class="ni-alert ni-alert--{{ msg.tags }}">{{ msg }}</div>
{% endfor %}

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <div class="ni-d-flex ni-items-center ni-gap-3 ni-mb-3">
      <button type="button" class="ni-btn ni-btn--primary" id="btnTambah">
        <i data-lucide="plus"></i> Tambah Harga Jual
      </button>
    </div>
    <div id="categoryButtons" class="ni-d-flex ni-gap-2 ni-flex-wrap ni-mb-4 ni-d-none">
      {% for tipe in tipe_choices %}
      <button type="button"
              class="ni-btn ni-btn--secondary ni-btn--sm ni-category-btn"
              data-tipe="{{ tipe.0 }}">
        {{ tipe.1 }}
      </button>
      {% endfor %}
    </div>
    <div class="ni-table-wrapper">
      <table class="ni-table" id="catalogTable">
        <thead>
          <tr>
            <th>Item</th>
            <th>Tipe</th>
            <th>Display Name</th>
            <th>Harga Jual</th>
            <th>Active</th>
            <th>Order</th>
            <th>Gambar</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody id="catalogTbody">
          <tr id="emptyRow">
            <td colspan="8" class="ni-text-center ni-text-muted">
              Pilih kategori untuk menampilkan item.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

{# Hidden CSRF for JS #}
{% csrf_token %}

{% endblock %}
{% block extra_js %}
<script>
(function () {
  'use strict';

  var UPSERT_URL = '{% url "pos_catalog:catalog_upsert" eb.pk %}';
  var ITEMS_URL  = '{% url "pos_catalog:catalog_items_ajax" eb.pk %}';
  var csrfToken  = document.querySelector('[name=csrfmiddlewaretoken]').value;
  var activeRow  = null;

  // Show category buttons on "Tambah Harga Jual" click
  document.getElementById('btnTambah').addEventListener('click', function () {
    document.getElementById('categoryButtons').classList.remove('ni-d-none');
  });

  // Load items when a category button is clicked
  document.querySelectorAll('.ni-category-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (activeRow && isDirty(activeRow)) {
        if (!confirm('Ada perubahan belum disimpan. Discard?')) return;
        cancelRow(activeRow);
      }
      document.querySelectorAll('.ni-category-btn').forEach(function (b) {
        b.classList.remove('ni-btn--primary');
        b.classList.add('ni-btn--secondary');
      });
      btn.classList.remove('ni-btn--secondary');
      btn.classList.add('ni-btn--primary');
      loadItems(btn.getAttribute('data-tipe'));
    });
  });

  function loadItems(tipeItem) {
    fetch(ITEMS_URL + '?tipe_item=' + encodeURIComponent(tipeItem), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var tbody = document.getElementById('catalogTbody');
        tbody.innerHTML = data.html;
        lucide.createIcons();
        attachEditHandlers();
        activeRow = null;
      })
      .catch(function () {
        alert('Gagal memuat item. Coba lagi.');
      });
  }

  function attachEditHandlers() {
    document.querySelectorAll('.ni-catalog-edit-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = btn.closest('tr');
        if (activeRow && activeRow !== row) {
          if (isDirty(activeRow)) {
            if (!confirm('Ada perubahan belum disimpan. Discard?')) return;
          }
          cancelRow(activeRow);
        }
        editRow(row);
      });
    });
    document.querySelectorAll('.ni-catalog-save-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var row = btn.closest('tr');
        saveRow(row);
      });
    });
    document.querySelectorAll('.ni-catalog-cancel-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        cancelRow(btn.closest('tr'));
      });
    });
  }

  function editRow(row) {
    activeRow = row;
    row.querySelectorAll('[data-read]').forEach(function (el) { el.classList.add('ni-d-none'); });
    row.querySelectorAll('[data-edit]').forEach(function (el) { el.classList.remove('ni-d-none'); });
    row.querySelector('.ni-catalog-edit-btn').classList.add('ni-d-none');
    row.querySelector('.ni-catalog-save-btn').classList.remove('ni-d-none');
    row.querySelector('.ni-catalog-cancel-btn').classList.remove('ni-d-none');
    setAllEditBtns(true);
    row.querySelector('.ni-catalog-edit-btn').disabled = false;
  }

  function cancelRow(row) {
    row.querySelectorAll('[data-edit]').forEach(function (el) { el.classList.add('ni-d-none'); });
    row.querySelectorAll('[data-read]').forEach(function (el) { el.classList.remove('ni-d-none'); });
    row.querySelector('.ni-catalog-edit-btn').classList.remove('ni-d-none');
    row.querySelector('.ni-catalog-save-btn').classList.add('ni-d-none');
    row.querySelector('.ni-catalog-cancel-btn').classList.add('ni-d-none');
    // Restore original input values
    row.querySelectorAll('[data-edit] input, [data-edit] textarea').forEach(function (inp) {
      inp.value = inp.getAttribute('data-original') || '';
    });
    setAllEditBtns(false);
    activeRow = null;
  }

  function saveRow(row) {
    var fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken);
    fd.append('item_id', row.getAttribute('data-item-id'));
    fd.append('selling_price', row.querySelector('[name=selling_price]').value);
    fd.append('display_name', row.querySelector('[name=display_name]').value);
    fd.append('display_order', row.querySelector('[name=display_order]').value);
    fd.append('is_active', row.querySelector('[name=is_active]').checked ? 'true' : 'false');
    var imgInput = row.querySelector('[name=product_image]');
    if (imgInput && imgInput.files.length > 0) {
      fd.append('product_image', imgInput.files[0]);
    }

    fetch(UPSERT_URL, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: fd,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          var item = data.item;
          row.querySelector('[data-read="display_name"]').textContent = item.display_name;
          row.querySelector('[data-read="selling_price"]').textContent = 'Rp ' + Number(item.selling_price).toLocaleString('id-ID');
          row.querySelector('[data-read="is_active"]').textContent = item.is_active ? '✓' : '—';
          row.querySelector('[data-read="display_order"]').textContent = item.display_order;
          if (item.image_url) {
            var imgEl = row.querySelector('[data-read="product_image"]');
            if (imgEl) imgEl.src = item.image_url;
          }
          row.setAttribute('data-catalog-id', item.id);
          cancelRow(row);
        } else {
          alert('Gagal menyimpan: ' + (data.error || 'Unknown error'));
        }
      })
      .catch(function () {
        alert('Terjadi kesalahan. Coba lagi.');
      });
  }

  function isDirty(row) {
    var dirty = false;
    row.querySelectorAll('[data-edit] input[type!=file], [data-edit] input[type!=checkbox]').forEach(function (inp) {
      if (inp.type !== 'file' && inp.type !== 'checkbox') {
        if (inp.value !== (inp.getAttribute('data-original') || '')) dirty = true;
      }
    });
    var cb = row.querySelector('[name=is_active]');
    if (cb) {
      var orig = cb.getAttribute('data-original') === 'true';
      if (cb.checked !== orig) dirty = true;
    }
    return dirty;
  }

  function setAllEditBtns(disabled) {
    document.querySelectorAll('.ni-catalog-edit-btn').forEach(function (b) {
      b.disabled = disabled;
    });
  }

  // Click-outside handler
  document.addEventListener('click', function (e) {
    if (!activeRow) return;
    if (activeRow.contains(e.target)) return;
    if (isDirty(activeRow)) {
      if (confirm('Ada perubahan belum disimpan. Discard?')) {
        cancelRow(activeRow);
      }
    } else {
      cancelRow(activeRow);
    }
  });

})();
</script>
{% endblock %}
```

- [ ] **Step 2: Update `catalog_list` view to pass tipe_choices**

In `apps/pos_catalog/views.py`, update the `catalog_list` view:
```python
@login_required
def catalog_list(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    tipe_choices = ItemMasterPurchase.ITEM_TYPE_CHOICES
    return render(request, 'pos_catalog/catalog_list.html', {
        'eb': eb,
        'tipe_choices': tipe_choices,
    })
```

- [ ] **Step 3: Write the full `_catalog_rows.html` partial**

Replace `templates/pos_catalog/_catalog_rows.html`:
```html
{% load humanize %}
{% for row in rows %}
{% with ci=row.catalog_item item=row.item %}
<tr data-item-id="{{ item.pk }}"
    data-catalog-id="{{ ci.pk|default:'' }}">
  <td>{{ item.nama }}</td>
  <td><span class="ni-badge ni-badge--secondary">{{ item.get_tipe_item_display }}</span></td>

  {# Display Name #}
  <td>
    <span data-read="display_name">{{ ci.display_name|default:'—' }}</span>
    <span data-edit class="ni-d-none">
      <input type="text" name="display_name" class="ni-input"
             value="{{ ci.display_name|default:'' }}"
             data-original="{{ ci.display_name|default:'' }}">
    </span>
  </td>

  {# Selling Price #}
  <td>
    <span data-read="selling_price">
      {% if ci %}Rp {{ ci.selling_price|floatformat:0|intcomma }}{% else %}—{% endif %}
    </span>
    <span data-edit class="ni-d-none">
      <input type="number" name="selling_price" class="ni-input"
             step="1" min="0"
             value="{{ ci.selling_price|default:'' }}"
             data-original="{{ ci.selling_price|default:'' }}">
    </span>
  </td>

  {# Is Active #}
  <td>
    <span data-read="is_active">{% if ci and ci.is_active %}✓{% else %}—{% endif %}</span>
    <span data-edit class="ni-d-none">
      <input type="checkbox" name="is_active" class="ni-checkbox"
             {% if not ci or ci.is_active %}checked{% endif %}
             data-original="{% if not ci or ci.is_active %}true{% else %}false{% endif %}">
    </span>
  </td>

  {# Display Order #}
  <td>
    <span data-read="display_order">{{ ci.display_order|default:'—' }}</span>
    <span data-edit class="ni-d-none">
      <input type="number" name="display_order" class="ni-input"
             style="width:70px" min="1"
             value="{{ ci.display_order|default:'' }}"
             data-original="{{ ci.display_order|default:'' }}">
    </span>
  </td>

  {# Product Image #}
  <td>
    <span data-read="product_image">
      {% if ci and ci.product_image %}
      <img src="{{ ci.product_image.url }}" alt="" class="ni-catalog-thumb">
      {% else %}—{% endif %}
    </span>
    <span data-edit class="ni-d-none">
      <input type="file" name="product_image" accept="image/*">
    </span>
  </td>

  {# Actions #}
  <td>
    <div class="ni-btn-row">
      <button type="button" class="ni-btn ni-btn--warning ni-btn--sm ni-catalog-edit-btn">
        <i data-lucide="pencil"></i> Edit
      </button>
      <button type="button" class="ni-btn ni-btn--primary ni-btn--sm ni-catalog-save-btn ni-d-none">
        <i data-lucide="save"></i> Save
      </button>
      <button type="button" class="ni-btn ni-btn--secondary ni-btn--sm ni-catalog-cancel-btn ni-d-none">
        Batal
      </button>
    </div>
  </td>
</tr>
{% endwith %}
{% empty %}
<tr>
  <td colspan="8" class="ni-text-center ni-text-muted">Tidak ada item untuk kategori ini.</td>
</tr>
{% endfor %}
```

- [ ] **Step 4: Add `.ni-catalog-thumb` to `wizard.css` (small image in table)**

Append to `static/css/wizard.css`:
```css
.ni-catalog-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: var(--ni-radius-sm);
}
```

- [ ] **Step 5: Verify template renders**

```
python manage.py check
```
Expected: 0 issues.

- [ ] **Step 6: Commit**

```bash
git add templates/pos_catalog/catalog_list.html templates/pos_catalog/_catalog_rows.html static/css/wizard.css
git commit -m "feat(pos_catalog): add catalog list template with inline edit JS"
```

---

### Task 5: Catalog Logs template

**Files:**
- Replace: `templates/pos_catalog/catalog_logs.html`

- [ ] **Step 1: Write the full catalog logs template**

Replace `templates/pos_catalog/catalog_logs.html`:
```html
{% extends 'base.html' %}
{% block title %}Catalog Logs — {{ eb.nama }}{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Catalog Logs</h1>
    <p class="ni-page-header__subtitle">{{ eb.nama }}</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'pos_catalog:catalog_list' eb.pk %}" class="ni-btn ni-btn--secondary">
      <i data-lucide="arrow-left"></i> Kembali ke Catalog
    </a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <form method="get" class="ni-d-flex ni-gap-2 ni-mb-3">
      <input type="text" name="q" value="{{ q }}" placeholder="Cari nama item..." class="ni-input">
      <button type="submit" class="ni-btn ni-btn--primary">Cari</button>
      {% if q %}<a href="?" class="ni-btn ni-btn--secondary">Reset</a>{% endif %}
    </form>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Tanggal</th>
          <th>Item</th>
          <th>Field</th>
          <th>Dari</th>
          <th>Ke</th>
          <th>Oleh</th>
        </tr>
      </thead>
      <tbody>
        {% for log in page %}
        <tr>
          <td class="ni-whitespace-nowrap">{{ log.changed_at|date:"d M Y H:i" }}</td>
          <td>{{ log.catalog_item.item.nama }}</td>
          <td><span class="ni-badge ni-badge--secondary">{{ log.field_name }}</span></td>
          <td class="ni-text-muted">{{ log.old_value }}</td>
          <td>{{ log.new_value }}</td>
          <td class="ni-text-muted">{{ log.changed_by.email|default:'—' }}</td>
        </tr>
        {% empty %}
        <tr>
          <td colspan="6" class="ni-text-center ni-text-muted">Belum ada log.</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% if page.has_other_pages %}
  <div class="ni-card__body">
    <div class="ni-paginator">
      {% if page.has_previous %}
      <a href="?page={{ page.previous_page_number }}{% if q %}&q={{ q }}{% endif %}" class="ni-btn ni-btn--secondary ni-btn--sm">← Prev</a>
      {% endif %}
      <span class="ni-text-muted">Halaman {{ page.number }} dari {{ page.paginator.num_pages }}</span>
      {% if page.has_next %}
      <a href="?page={{ page.next_page_number }}{% if q %}&q={{ q }}{% endif %}" class="ni-btn ni-btn--secondary ni-btn--sm">Next →</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Run all catalog tests**

```
python manage.py test pos_catalog.tests.test_catalog -v 2 --keepdb
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/pos_catalog/catalog_logs.html
git commit -m "feat(pos_catalog): add catalog logs template"
```

---

### Task 6: Entry points — EB list Catalog button + Setup Wizard catalog_ok

**Files:**
- Modify: `apps/entitas_bisnis/views.py`
- Modify: `templates/entitas_bisnis/list.html`
- Modify: `templates/entitas_bisnis/setup_wizard.html`

- [ ] **Step 1: Add `catalog_ok` to `_compute_wizard_checks`**

In `apps/entitas_bisnis/views.py`, inside `_compute_wizard_checks`, add the import and check. Find the existing `return {` block and add before it:

```python
    from apps.pos_catalog.models import CatalogItem
    catalog_ok = CatalogItem.objects.filter(
        entitas_bisnis=eb, is_active=True
    ).exists()
```

Then add to the return dict:
```python
        'catalog_ok': catalog_ok,
```

- [ ] **Step 2: Add catalog item to setup_wizard.html**

In `templates/entitas_bisnis/setup_wizard.html`, after the QRIS item (item 6), add before the `<!-- ── AJAX Modals ──` comment:

```html
<!-- 7. Catalog & Harga Jual -->
<div class="ni-card ni-mb-3 ni-animate-fade-in">
  <div class="ni-card__body">
    <div class="ni-checklist-item">
      <div class="ni-checklist-item__icon">
        {% if checks.catalog_ok %}
        <i data-lucide="check-circle-2" class="ni-icon-md ni-text-success"></i>
        {% else %}
        <i data-lucide="circle" class="ni-icon-md ni-text-muted"></i>
        {% endif %}
      </div>
      <div class="ni-checklist-item__body">
        <div class="ni-checklist-item__header">
          <span class="ni-checklist-item__title">Catalog &amp; Harga Jual</span>
          {% if checks.catalog_ok %}
          <span class="ni-badge ni-badge--success">Done</span>
          {% else %}
          <span class="ni-badge ni-badge--secondary">Opsional</span>
          {% endif %}
        </div>
        <p class="ni-checklist-item__desc">
          {% if checks.catalog_ok %}Item katalog sudah dikonfigurasi.{% else %}Tambahkan item dan harga jual untuk kasir.{% endif %}
        </p>
        <a href="{% url 'pos_catalog:catalog_list' eb.pk %}" class="ni-btn ni-btn--secondary ni-btn--sm">
          <i data-lucide="tag"></i>
          {% if checks.catalog_ok %}Edit Catalog{% else %}Setup Catalog{% endif %}
        </a>
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add Catalog button to EB list page lv1 row**

In `templates/entitas_bisnis/list.html`, find the lv1 row actions div and add the Catalog button between Detail and Hapus:

Find:
```html
        <a href="{% url 'entitas_bisnis:setup_wizard' lv1.pk %}" class="ni-btn ni-btn--primary">
          <i data-lucide="layout-dashboard"></i> Detail
        </a>
        <button type="button" class="ni-btn ni-btn--outline-danger"
```
Replace with:
```html
        <a href="{% url 'entitas_bisnis:setup_wizard' lv1.pk %}" class="ni-btn ni-btn--primary">
          <i data-lucide="layout-dashboard"></i> Detail
        </a>
        <a href="{% url 'pos_catalog:catalog_list' lv1.pk %}" class="ni-btn ni-btn--secondary">
          <i data-lucide="tag"></i> Catalog
        </a>
        <button type="button" class="ni-btn ni-btn--outline-danger"
```

- [ ] **Step 4: Verify and run wizard tests**

```
python manage.py check
python manage.py test apps.entitas_bisnis.tests.SetupWizardViewTests apps.entitas_bisnis.tests.ComputeWizardChecksTests -v 2 --keepdb
```
Expected: 0 issues, all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/entitas_bisnis/views.py templates/entitas_bisnis/list.html templates/entitas_bisnis/setup_wizard.html
git commit -m "feat(pos_catalog): add catalog entry points to EB list and setup wizard"
```

---

## Self-Review

**Spec coverage:**
- ✅ unit_price → unit_cost rename — Task 1
- ✅ CatalogItem model (all fields inc. display_order auto-assign) — Task 2
- ✅ CatalogItemLog model — Task 2
- ✅ catalog_list, catalog_items_ajax, catalog_upsert, catalog_logs views — Task 3
- ✅ Inline edit: one row at a time, confirm-on-discard — Task 4 JS
- ✅ Save without page refresh (AJAX upsert) — Task 4 JS
- ✅ Image upload support — Task 4 (FormData + enctype multipart)
- ✅ Catalog Logs page with search + pagination — Task 5
- ✅ Entry point on EB list page — Task 6
- ✅ Entry point on setup wizard (item 7, Recommended) — Task 6
- ✅ Log writing on update (not on create) — Task 3 upsert view
- ✅ tipe_choices passed to template — Task 4 view update

**Placeholders:** None found.

**Type consistency:**
- `catalog_list` view uses `ItemMasterPurchase.ITEM_TYPE_CHOICES` — this attribute exists on the model (verified in purchase/models.py line 55-60)
- `_catalog_rows.html` uses `{% load humanize %}` for `intcomma` — ensure `django.contrib.humanize` is in `INSTALLED_APPS` (standard Django project inclusion)
- `catalog_items_ajax` returns `{'html': ...}`, JS reads `data.html` — consistent
- `catalog_upsert` returns `{'success': True, 'item': {...}}`, JS reads `data.success` and `data.item` — consistent
