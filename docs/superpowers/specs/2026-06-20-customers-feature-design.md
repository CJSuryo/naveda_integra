# Customers Feature Design

**Date:** 2026-06-20  
**Status:** Approved

## Overview

New `apps/customers/` Django app. Canonical source of truth for all customer data across the system. Separate from `apps/pos_crm/` (Member is a POS loyalty entity; Customer is a general CRM entity).

---

## Model: `Customer`

```python
class Customer(models.Model):
    GENDER_CHOICES = [('L', 'Laki-laki'), ('P', 'Perempuan'), ('O', 'Lainnya')]

    nama             = models.CharField(max_length=200)
    email            = models.EmailField(blank=True, null=True)
    telepon          = models.CharField(max_length=20, blank=True, null=True)
    alamat           = models.TextField(blank=True, null=True)
    npwp             = models.CharField(max_length=20, blank=True, null=True, unique=True)
    gender           = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    tanggal_lahir    = models.DateField(blank=True, null=True)

    # EB hierarchy — all three levels stored; auto-populated from user's selection
    entitas_bisnis     = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='customers')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.SET_NULL, null=True, blank=True, related_name='customers')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.SET_NULL, null=True, blank=True, related_name='customers')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def umur(self) -> int | None:
        if not self.tanggal_lahir:
            return None
        today = date.today()
        return today.year - self.tanggal_lahir.year - (
            (today.month, today.day) < (self.tanggal_lahir.month, self.tanggal_lahir.day)
        )
```

**EB resolution rule (enforced in view, not model):**
- User picks any level via hierarchical TomSelect (value format: `lv1:X`, `lv2:Y`, `lv3:Z`)
- `_resolve_eb_selection()` from `apps.purchase.views` resolves to `{lv1_id, lv2_id, lv3_id}`
- View writes all three FKs; lower levels null if not applicable

---

## URLs

Prefix: `customers/`  
Namespace: `customers`  
Registered in `naveda_integra/urls.py` as `path('customers/', include('apps.customers.urls', namespace='customers'))`

| URL | Name | View |
|-----|------|------|
| `customers/` | `list` | `customer_list` |
| `customers/tambah/` | `create` | `customer_create` |
| `customers/<pk>/edit/` | `update` | `customer_update` |
| `customers/<pk>/hapus/` | `delete` | `customer_delete` |
| `customers/quick-create/` | `quick_create` | `customer_quick_create` |

---

## Views

### `customer_list`
- GET params: `q` (search nama/email/telepon), `entitas_bisnis` (multi, EB filter)
- EB filter: same pattern as pendapatan — `_resolve_eb_selection()` → filter on `entitas_bisnis_id__in`
- Passes `eb_tree` to template for `eb_filter_modal` component
- Paginated (20 per page)

### `customer_create` / `customer_update`
- Standard form page
- `eb_options_json` passed for TomSelect initialization
- On POST: resolve EB selection → set lv1/lv2/lv3 FKs → save
- Redirect to `customers:list` on success

### `customer_delete`
- POST only → delete → redirect to `customers:list`

### `customer_quick_create`
- POST only, AJAX
- Same EB resolution logic as create
- Returns `{"success": true, "customer": {"id": X, "nama": "..."}}`
- Returns `{"success": false, "errors": {...}}` on validation failure

---

## Templates

```
templates/
  customers/
    list.html         ← filter bar (eb_filter_modal + search), table, paginator
    form.html         ← shared create/edit form page
    hapus_konfirmasi.html
  components/
    customer_create_modal.html   ← reusable inline-create modal for other modules
```

### `list.html` columns
Nama | Entitas Bisnis | Email | Telepon | Gender | Umur | Aksi (Edit / Hapus)

### `form.html` fields
- EB selector (hierarchical TomSelect, `eb_options_json`)
- Nama (required)
- Email, Telepon, Alamat (optional)
- NPWP (optional)
- Gender (select)
- Tanggal Lahir (date picker)

### `customer_create_modal.html`

Reusable component. Other modules include it and bind a JS callback:

```html
{% include 'components/customer_create_modal.html' %}
```

Modal submits via `fetch()` to `{% url 'customers:quick_create' %}`.  
On success, calling module receives `{id, nama}` and injects into its customer TomSelect.

---

## Navigation (`base.html`)

Add after Entitas Bisnis submenu block, before Master Data label:

```html
<span class="ni-nav-label">Customers</span>
<div class="ni-nav-item">
  <a href="{% url 'customers:list' %}" class="ni-nav-link {% if 'customers' in request.path %}ni-nav-link--active{% endif %}">
    <i data-lucide="users-2" class="ni-nav-link__icon"></i>
    <span class="ni-nav-link__text">Customers</span>
  </a>
</div>
```

---

## Django App Registration

Add `'apps.customers'` to `INSTALLED_APPS` in `config/settings/`.

---

## Key Constraints

- No inline styles in templates — class names only, CSS in `static/css/`
- TomSelect CSS via `tomselect.css` (never inline)
- EB selection always via `_get_eb_dropdown_options()` + `_resolve_eb_selection()` from `apps.purchase.views`
- `umur` never stored — always derived from `tanggal_lahir`
- `pos_crm.Member` remains separate — do not merge or replace it
