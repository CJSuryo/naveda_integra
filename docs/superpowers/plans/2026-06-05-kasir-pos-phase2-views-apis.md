# Kasir POS — Phase 2: Kasir Views, APIs, URL Wiring, Event Log

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the four `/kasir/` API views, register URLs, add Kasir sidebar link, write event log entries in sales views/services, and add the event log timeline to `sales_detail.html`.

**Prereq:** Phase 1 complete (models migrated).

**Architecture:** New `apps/sales/kasir_views.py`; event log writes added to existing `views.py` and `services.py`. No new app.

**Tech Stack:** Django, `@login_required`, `JsonResponse`, Django TestCase

---

### Task 5: kasir_views.py

**Files:**
- Create: `apps/sales/kasir_views.py`

- [ ] **Step 1: Create kasir_views.py**

Create `apps/sales/kasir_views.py`:
```python
"""Kasir POS views — full-screen cashier screen and its JSON APIs."""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnisLv3
from apps.pos_catalog.models import ProductModifierGroup
from apps.inventory.models import InventoryRecord
from apps.purchase.models import ItemMasterPurchase, SubTransactionType

from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesEventLog
from .services import process_sales_fifo, create_sales_automated_journals


@login_required
def kasir_pos(request: HttpRequest) -> HttpResponse:
    """Full-screen standalone POS page at /kasir/."""
    stores = (
        EntitasBisnisLv3.objects
        .filter(status_aktif=True)
        .select_related('parent_lv2__entitas_bisnis')
        .order_by('nama')
    )
    return render(request, 'kasir/pos.html', {'stores': stores})


@login_required
def api_kasir_config(request: HttpRequest, lv3_pk: int) -> JsonResponse:
    """Return resolved POS config for a lv3 outlet."""
    try:
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=lv3_pk, status_aktif=True)
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Store not found'}, status=404)

    from apps.pos_config.utils import resolve_pos_config
    cfg = resolve_pos_config(lv3)

    merchant = getattr(
        getattr(lv3.parent_lv2, 'entitas_bisnis', None),
        'pos_config',
        None,
    )
    brand_name = lv3.parent_lv2.entitas_bisnis.nama if lv3.parent_lv2 else 'Naveda'

    return JsonResponse({
        'ok': True,
        'lv3_pk': lv3.pk,
        'store_name': lv3.parent_lv2.nama if lv3.parent_lv2 else '',
        'outlet_name': lv3.nama,
        'brand_name': brand_name,
        'tax_pct': str(cfg['tax_pct']),
        'sub_transaction_type_id': cfg['sub_transaction_type_id'],
        'revenue_account_id': cfg['revenue_account_id'],
        'offset_coa_account_id': cfg['offset_coa_account_id'],
        'payment_account_id': cfg['payment_account_id'],
        'qris_image_url': cfg['qris_image_url'],
        'cashier_name': request.user.get_full_name() or request.user.username,
    })


@login_required
def api_kasir_catalog(request: HttpRequest) -> JsonResponse:
    """Return inventory items + modifier groups for a lv3 store."""
    try:
        lv3_pk = int(request.GET.get('lv3_pk', ''))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'items': []})

    try:
        lv3 = EntitasBisnisLv3.objects.select_related('parent_lv2__entitas_bisnis').get(
            pk=lv3_pk, status_aktif=True,
        )
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'items': []})

    inv_qs = (
        InventoryRecord.objects
        .filter(entitas_bisnis_lv3_id=lv3_pk, quantity__gt=0)
        .exclude(item__tipe_item__in=['RMB', 'FGB', 'ITMB'])
        .select_related('item__kategori')
        .order_by('item__kategori__nama', 'item__nama')
    )
    if not inv_qs.exists():
        lv1_id = lv3.parent_lv2.entitas_bisnis_id
        inv_qs = (
            InventoryRecord.objects
            .filter(entitas_bisnis_id=lv1_id, quantity__gt=0)
            .exclude(item__tipe_item__in=['RMB', 'FGB', 'ITMB'])
            .select_related('item__kategori')
            .order_by('item__kategori__nama', 'item__nama')
        )

    item_ids = list(inv_qs.values_list('item_id', flat=True).distinct())
    modifier_map: dict[int, list] = {}
    for pmg in (
        ProductModifierGroup.objects
        .filter(item_id__in=item_ids)
        .select_related('modifier_group')
        .prefetch_related('modifier_group__options')
    ):
        modifier_map.setdefault(pmg.item_id, []).append({
            'pk': pmg.modifier_group_id,
            'nama': pmg.modifier_group.name,
            'is_required': pmg.modifier_group.is_required,
            'min_selections': pmg.modifier_group.min_selections,
            'max_selections': pmg.modifier_group.max_selections,
            'options': [
                {
                    'pk': opt.pk,
                    'name': opt.name,
                    'additional_price': str(opt.additional_price),
                    'is_default': opt.is_default,
                }
                for opt in pmg.modifier_group.options.all()
                if opt.is_available
            ],
        })

    seen: set[int] = set()
    items_data = []
    for inv in inv_qs:
        if inv.item_id in seen:
            continue
        seen.add(inv.item_id)
        items_data.append({
            'item_pk': inv.item_id,
            'name': inv.item.nama,
            'kode_item': inv.item.item_id,
            'selling_price': str(inv.selling_price) if inv.selling_price is not None else '0',
            'category': inv.item.kategori.nama.lower().replace(' ', '') if inv.item.kategori else 'other',
            'category_label': inv.item.kategori.nama if inv.item.kategori else 'Lainnya',
            'modifier_groups': modifier_map.get(inv.item_id, []),
        })

    categories = []
    seen_cats: list[str] = []
    for it in items_data:
        if it['category'] not in seen_cats:
            seen_cats.append(it['category'])
            categories.append({'id': it['category'], 'label': it['category_label']})

    return JsonResponse({'ok': True, 'items': items_data, 'categories': categories})


@login_required
@require_POST
def api_kasir_submit(request: HttpRequest) -> JsonResponse:
    """Submit a POS sale. Creates SalesHeader + SalesItems, runs FIFO + journals."""
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    lv3_pk = body.get('lv3_pk')
    cart = body.get('cart', [])
    tender = body.get('tender', 'cash')
    tendered_amount = body.get('tendered_amount', 0)
    discount_data = body.get('discount')  # None | {type, val}

    if not lv3_pk or not cart:
        return JsonResponse({'ok': False, 'error': 'lv3_pk and cart required'}, status=400)

    try:
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=int(lv3_pk), status_aktif=True)
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Store not found'}, status=404)

    from apps.pos_config.utils import resolve_pos_config
    cfg = resolve_pos_config(lv3)

    stt_id = cfg['sub_transaction_type_id']
    revenue_id = cfg['revenue_account_id']
    offset_id = cfg['offset_coa_account_id']
    payment_id = cfg['payment_account_id']
    tax_pct = cfg['tax_pct']

    if not stt_id:
        return JsonResponse({'ok': False, 'error': 'Sub-Transaction Type belum dikonfigurasi untuk outlet ini.'}, status=400)
    if not revenue_id or not offset_id:
        return JsonResponse({'ok': False, 'error': 'Revenue atau HPP account belum dikonfigurasi.'}, status=400)

    # Server-side totals (never trust client)
    subtotal = Decimal('0')
    for line in cart:
        try:
            unit_price = Decimal(str(line.get('unit_price', 0)))
            qty = Decimal(str(line.get('qty', 1)))
            subtotal += unit_price * qty
        except (InvalidOperation, ValueError):
            return JsonResponse({'ok': False, 'error': f'Invalid price in cart line'}, status=400)

    if discount_data:
        disc_type = discount_data.get('type')
        disc_val = Decimal(str(discount_data.get('val', 0)))
        if disc_type == 'pct':
            disc_amt = round(subtotal * disc_val / 100)
        else:
            disc_amt = min(disc_val, subtotal)
    else:
        disc_amt = Decimal('0')

    taxed_base = max(Decimal('0'), subtotal - disc_amt)
    tax_amount = round(taxed_base * tax_pct / 100)
    grand_total = taxed_base + tax_amount
    change = Decimal(str(tendered_amount)) - grand_total if tender == 'cash' else Decimal('0')

    tanggal = timezone.now().date()

    try:
        with transaction.atomic():
            sales = SalesHeader.objects.create(
                tanggal=tanggal,
                deskripsi=f'POS — {lv3.nama} — {tender.upper()}',
                created_by=request.user,
            )

            lv1_id = lv3.parent_lv2.entitas_bisnis_id
            lv2_id = lv3.parent_lv2_id
            eb_group = SalesEntitasBisnis.objects.create(
                sales_header=sales,
                entitas_bisnis_id=lv1_id,
                entitas_bisnis_lv2_id=lv2_id,
                entitas_bisnis_lv3_id=lv3.pk,
                payment_account_id=None,
            )

            for line in cart:
                item_pk = line.get('item_pk')
                qty = Decimal(str(line.get('qty', 1)))
                unit_price = Decimal(str(line.get('unit_price', 0)))
                mod_labels = line.get('modifier_labels', '')

                try:
                    item_obj = ItemMasterPurchase.objects.only('tipe_item', 'coa_account_id').get(pk=int(item_pk))
                except (ItemMasterPurchase.DoesNotExist, ValueError, TypeError):
                    raise ValueError(f'Item {item_pk} not found')

                SalesItem.objects.create(
                    sales_eb=eb_group,
                    item_id=int(item_pk),
                    sub_transaction_type_id=stt_id,
                    quantity=qty,
                    selling_price=unit_price,
                    offset_coa_account_id=offset_id,
                    revenue_account_id=revenue_id,
                    payment_account_id=payment_id,
                    inventory_account_id=item_obj.coa_account_id,
                    tax=tax_amount if tax_amount else None,
                    tax_type='ppn_keluaran' if tax_amount else '',
                )

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='CREATED',
                description=f'POS sale via {tender.upper()}',
                actor=request.user,
            )

            process_sales_fifo(sales)

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='FIFO_PROCESSED',
                actor=None,
            )

            create_sales_automated_journals(sales)

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='JOURNAL_CREATED',
                actor=None,
            )

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='PAYMENT_PROCESSED',
                description=f'Metode: {tender.upper()}, Bayar: {tendered_amount}, Kembalian: {change}',
                actor=request.user,
            )

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'Server error: {str(e)}'}, status=500)

    return JsonResponse({
        'ok': True,
        'trx_id': sales.transaction_id,
        'grand_total': str(grand_total),
        'change': str(change),
    })
```

- [ ] **Step 2: Commit**

```bash
git add apps/sales/kasir_views.py
git commit -m "feat(sales): add kasir_views.py with POS page + 3 JSON APIs"
```

---

### Task 6: URL registration + sidebar link

**Files:**
- Modify: `apps/sales/urls.py`
- Modify: `templates/base.html`

- [ ] **Step 1: Register kasir URLs in sales/urls.py**

In `apps/sales/urls.py`, add import and new paths:
```python
from . import views, kasir_views

urlpatterns = [
    # existing patterns...
    path('', views.sales_list, name='list'),
    path('export/', views.sales_export, name='export'),
    path('export/pdf/', views.sales_export_pdf, name='export_pdf'),
    path('create/', views.sales_create, name='create'),
    path('<int:pk>/', views.sales_detail, name='detail'),
    path('<int:pk>/invoice/', views.sales_invoice, name='invoice'),
    path('<int:pk>/edit/', views.sales_update, name='update'),
    path('<int:pk>/delete/', views.sales_delete, name='delete'),
    path('pos/', views.pos_cashier, name='pos_cashier'),
    path('api/stock-check/', views.api_stock_check, name='api_stock_check'),
    path('api/stt-offset/', views.api_stt_offset, name='api_stt_offset'),
    path('api/stt-defaults/', views.api_stt_defaults, name='api_stt_defaults'),
    path('api/pos-items/', views.api_pos_items, name='api_pos_items'),
    # Kasir POS
    path('kasir/', kasir_views.kasir_pos, name='kasir_pos'),
    path('kasir/api/catalog/', kasir_views.api_kasir_catalog, name='api_kasir_catalog'),
    path('kasir/api/config/<int:lv3_pk>/', kasir_views.api_kasir_config, name='api_kasir_config'),
    path('kasir/api/submit/', kasir_views.api_kasir_submit, name='api_kasir_submit'),
]
```

- [ ] **Step 2: Add Kasir link to sidebar in base.html**

In `templates/base.html`, find the Dashboard nav item block:
```html
      <div class="ni-nav-item">
        <a href="{% url 'home' %}" class="ni-nav-link {% if request.resolver_match.url_name == 'home' %}ni-nav-link--active{% endif %}">
          <i data-lucide="layout-dashboard" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">Dashboard</span>
        </a>
      </div>
```

Insert immediately after it:
```html
      <div class="ni-nav-item">
        <a href="{% url 'sales:kasir_pos' %}" class="ni-nav-link {% if 'kasir' in request.path %}ni-nav-link--active{% endif %}">
          <i data-lucide="monitor-check" class="ni-nav-link__icon"></i>
          <span class="ni-nav-link__text">Kasir</span>
        </a>
      </div>
```

- [ ] **Step 3: Create placeholder template so the view loads**

Create `templates/kasir/pos.html` (minimal — full template added in Phase 3):
```html
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><title>Kasir POS</title></head>
<body style="background:#15110d;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;">
  <h1>Kasir POS — placeholder</h1>
  <p>Stores: {{ stores|length }}</p>
</body>
</html>
```

- [ ] **Step 4: Verify URLs resolve**

```
python manage.py runserver
```
- Visit `/sales/kasir/` → see placeholder page with store count
- Check sidebar shows "Kasir" link below Dashboard

- [ ] **Step 5: Commit**

```bash
git add apps/sales/urls.py templates/base.html templates/kasir/pos.html
git commit -m "feat(sales): register kasir URLs and add sidebar link"
```

---

### Task 7: Event log writes in views.py + services.py + sales_detail timeline

**Files:**
- Modify: `apps/sales/views.py`
- Modify: `apps/sales/services.py`
- Modify: `templates/sales/sales_detail.html`

- [ ] **Step 1: Add event log writes to _handle_sales_save and sales_delete in views.py**

In `apps/sales/views.py`, update imports:
```python
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesItemFIFOAllocation, SalesEventLog
```

In `_handle_sales_save`, after the `with transaction.atomic():` block completes (after `create_sales_automated_journals`), add:
```python
        # Write event log
        event_type = 'EDITED' if existing else 'CREATED'
        SalesEventLog.objects.create(
            sales_header=sales,
            event_type=event_type,
            description=f'Transaksi {sales.transaction_id} {"diperbarui" if existing else "dibuat"} via form.',
            actor=request.user,
        )
        SalesEventLog.objects.create(
            sales_header=sales,
            event_type='FIFO_PROCESSED',
            actor=None,
        )
        SalesEventLog.objects.create(
            sales_header=sales,
            event_type='JOURNAL_CREATED',
            actor=None,
        )
```

Also set `created_by` when creating new sales — in `_handle_sales_save`, find:
```python
            sales = SalesHeader.objects.create(
                tanggal=tanggal,
                deskripsi=deskripsi,
            )
```
Change to:
```python
            sales = SalesHeader.objects.create(
                tanggal=tanggal,
                deskripsi=deskripsi,
                created_by=request.user,
            )
```

In `sales_delete`, before `sales.delete()`, add:
```python
        SalesEventLog.objects.create(
            sales_header=sales,
            event_type='VOIDED',
            description=f'Transaksi {tid} dihapus.',
            actor=request.user,
        )
```

- [ ] **Step 2: Update sales_detail view to prefetch event logs**

In `sales_detail` view, change the return render call to include event logs:
```python
    event_logs = sales.event_logs.select_related('actor').order_by('timestamp')

    return render(request, 'sales/sales_detail.html', {
        'sales': sales,
        'eb_groups': eb_groups,
        'inventory_mutations': inventory_mutations,
        'event_logs': event_logs,
    })
```

- [ ] **Step 3: Add event log timeline to sales_detail.html**

At end of `templates/sales/sales_detail.html`, before `{% endblock %}`, add:
```html
<div class="ni-section-header" style="margin: 32px 0 16px;">
  <h2 class="ni-section-header__title">Riwayat Aktivitas</h2>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    {% if event_logs %}
    <div style="display:flex;flex-direction:column;gap:0;">
      {% for log in event_logs %}
      <div style="display:flex;gap:14px;padding:12px 0;border-bottom:1px solid var(--ni-border);">
        <div style="flex:none;padding-top:2px;">
          {% if log.event_type in 'CREATED,PAYMENT_PROCESSED' %}
            <span class="ni-badge ni-badge--success">{{ log.get_event_type_display }}</span>
          {% elif log.event_type == 'EDITED' %}
            <span class="ni-badge ni-badge--warning">{{ log.get_event_type_display }}</span>
          {% elif log.event_type == 'VOIDED' %}
            <span class="ni-badge ni-badge--danger">{{ log.get_event_type_display }}</span>
          {% elif log.event_type == 'LOCKED' %}
            <span class="ni-badge ni-badge--secondary">{{ log.get_event_type_display }}</span>
          {% else %}
            <span class="ni-badge ni-badge--info">{{ log.get_event_type_display }}</span>
          {% endif %}
        </div>
        <div style="flex:1;min-width:0;">
          {% if log.description %}
          <div style="font-size:0.875rem;color:var(--ni-text-secondary);margin-top:2px;">{{ log.description }}</div>
          {% endif %}
        </div>
        <div style="flex:none;text-align:right;font-size:0.8125rem;color:var(--ni-text-secondary);">
          <div>{{ log.actor.get_full_name|default:log.actor.username|default:"System" }}</div>
          <div>{{ log.timestamp|date:"d M Y H:i:s" }}</div>
        </div>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <p style="color:var(--ni-text-secondary);font-size:0.875rem;">Belum ada riwayat aktivitas.</p>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 4: Run sales tests to verify no regressions**

```
python manage.py test apps.sales -v 2
```
Expected: all existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sales/views.py apps/sales/services.py templates/sales/sales_detail.html
git commit -m "feat(sales): write event log entries in views/services, add timeline to sales_detail"
```
