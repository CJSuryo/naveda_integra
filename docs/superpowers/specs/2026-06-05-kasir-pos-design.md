# Kasir POS — Design Spec
**Date:** 2026-06-05  
**Status:** Approved  
**Scope:** New full-screen POS cashier page, cascading outlet config, user FK on SalesHeader, sales event log.

---

## 1. Context

Naveda Integra needs a tablet-first cashier (Kasir) screen for café/retail outlets. Design reference: `docs/superpowers/plans/Naveda POS/design_handoff_kasir_pos/`. Visual direction locked to **Cool theme / Comfy density / Photo cards** as specified in the handoff README.

Existing `pos_cashier` view at `/sales/pos/` is kept temporarily and removed later. New Kasir lives at `/kasir/`.

---

## 2. Data Model Changes

### 2a. `SalesHeader` — add `created_by`

```python
created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='sales_created',
)
```

- Set in `_handle_sales_save` and `api_kasir_submit`.
- `SET_NULL` — deleting a user does not cascade-delete sales.
- Migration: nullable, no data migration required.

### 2b. `SalesEventLog` — new model (in `apps/sales/models.py`)

```python
class SalesEventLog(models.Model):
    EVENT_TYPES = [
        ('CREATED', 'Dibuat'),
        ('EDITED', 'Diedit'),
        ('VOIDED', 'Dibatalkan'),
        ('FIFO_PROCESSED', 'FIFO Diproses'),
        ('JOURNAL_CREATED', 'Jurnal Dibuat'),
        ('PAYMENT_PROCESSED', 'Pembayaran Diproses'),
        ('LOCKED', 'Dikunci'),
    ]
    sales_header = models.ForeignKey(SalesHeader, on_delete=models.CASCADE, related_name='event_logs')
    event_type   = models.CharField(max_length=40, choices=EVENT_TYPES)
    description  = models.TextField(blank=True)
    actor        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
```

Written by:
- `_handle_sales_save` → CREATED or EDITED
- `sales_delete` → VOIDED (before deletion, logged separately)
- `process_sales_fifo` (or its caller) → FIFO_PROCESSED
- `create_sales_automated_journals` (or its caller) → JOURNAL_CREATED
- `api_kasir_submit` → CREATED + PAYMENT_PROCESSED

Displayed in `sales_detail.html` as a chronological timeline.

### 2c. `OutletPOSConfig` — new model (in `apps/pos_config/models.py`)

Adds lv3 specificity to the existing `MerchantPOSConfig` (lv1) + `StorePOSConfig` (lv2) cascade.

```python
class OutletPOSConfig(models.Model):
    entitas_bisnis_lv3      = models.OneToOneField('entitas_bisnis.EntitasBisnisLv3', on_delete=models.CASCADE, related_name='pos_config')
    merchant_config         = models.ForeignKey(MerchantPOSConfig, on_delete=models.CASCADE, related_name='outlets')
    sub_transaction_type    = models.ForeignKey('purchase.SubTransactionType', on_delete=models.PROTECT, null=True, blank=True)
    revenue_account         = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='pos_outlet_revenue')
    offset_coa_account      = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='pos_outlet_offset')
    default_payment_account = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='pos_outlet_payment')
    tax_pct                 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_active               = models.BooleanField(default=True)

    def __str__(self):
        return f'Outlet POS Config — {self.entitas_bisnis_lv3.nama}'
```

**Config resolution function** (`apps/pos_config/utils.py`):

```python
def resolve_pos_config(lv3) -> dict:
    """Return effective POS config for a lv3 outlet (lv3 → lv2 → lv1)."""
    outlet  = getattr(lv3, 'pos_config', None)
    store   = getattr(lv3.parent_lv2, 'pos_config', None)
    merchant = getattr(lv3.parent_lv2.entitas_bisnis, 'pos_config', None)

    def first(*vals):
        return next((v for v in vals if v is not None), None)

    # Note: StorePOSConfig (lv2) intentionally has no STT field — STT cascade is lv3 → lv1 only.
    # lv2 can override tax/printer but not accounting defaults.
    return {
        'sub_transaction_type': first(
            outlet and outlet.sub_transaction_type_id,
            merchant and merchant.sub_transaction_type_id,
        ),
        'revenue_account': first(
            outlet and outlet.revenue_account_id,
            merchant and merchant.revenue_account_id,
        ),
        'offset_coa_account': first(
            outlet and outlet.offset_coa_account_id,
            merchant and merchant.offset_coa_account_id,
        ),
        'payment_account': first(
            outlet and outlet.default_payment_account_id,
            store and store.merchant_config.default_payment_account_id,
            merchant and merchant.default_payment_account_id,
        ),
        'tax_pct': first(
            outlet and outlet.tax_pct,
            store and store.tax_pct,
            merchant and merchant.default_tax_pct,
        ) or Decimal('0'),
        'qris_image_url': merchant.qris_image.url if merchant and merchant.qris_image else None,
    }
```

---

## 3. URL & View Architecture

All new Kasir views in `apps/sales/kasir_views.py`. Registered in `apps/sales/urls.py`.

### New URL patterns

| URL | View | Method | Purpose |
|-----|------|--------|---------|
| `/kasir/` | `kasir_pos` | GET | Full-screen POS page |
| `/kasir/api/submit/` | `api_kasir_submit` | POST | Create sale, return TRX id + change |
| `/kasir/api/catalog/` | `api_kasir_catalog` | GET | Items for lv3 (wraps existing `api_pos_items` logic) |
| `/kasir/api/config/<lv3_pk>/` | `api_kasir_config` | GET | Resolved POS config for store |

### `kasir_pos` view

- `GET /kasir/` → renders `templates/kasir/pos.html` (standalone, no `base.html`).
- Passes `stores` = active `EntitasBisnisLv3` list (for startup store-selector).
- Template is fully self-contained: CSS, JS, icons inline.

### `api_kasir_submit` view

Input (JSON POST body):
```json
{
  "lv3_pk": 3,
  "tanggal": "2026-06-05",
  "cart": [
    { "item_pk": 12, "qty": 2, "unit_price": 28000, "selections": [...], "modifier_labels": "Gula Sedikit" }
  ],
  "tender": "cash",
  "tendered_amount": 60000,
  "discount": { "type": "pct", "val": 10 }
}
```

Server-side:
1. Resolve POS config for lv3 → get STT, accounts, tax_pct.
2. Compute totals (discount, tax, grand total) server-side — never trust client totals.
3. Create `SalesHeader` (with `created_by=request.user`).
4. Create `SalesEntitasBisnis` (lv3 → lv2 → lv1 IDs).
5. Create `SalesItem` per cart line (accounts from resolved config).
6. Call `process_sales_fifo`, `create_sales_automated_journals`.
7. Write `SalesEventLog`: CREATED, FIFO_PROCESSED, JOURNAL_CREATED, PAYMENT_PROCESSED.
8. Return `{ ok: true, trx_id: "TRX-SAL-049", change: 5000 }`.

### Sidebar — `base.html`

Insert after Dashboard link, before User link:

```html
<div class="ni-nav-item">
  <a href="{% url 'sales:kasir_pos' %}"
     class="ni-nav-link {% if 'kasir' in request.path %}ni-nav-link--active{% endif %}">
    <i data-lucide="monitor-check" class="ni-nav-link__icon"></i>
    <span class="ni-nav-link__text">Kasir</span>
  </a>
</div>
```

Once the user navigates to `/kasir/`, the standalone page replaces the entire viewport — no sidebar visible.

### EntitasBisnis detail pages — POS config sections

Add POS config card to existing detail/form pages:
- **lv1 detail** (`entitas_bisnis/detail.html`): `MerchantPOSConfig` edit form (STT, accounts, tax %, QRIS image).
- **lv2 detail** (`entitas_bisnis/lv2/detail.html`): `StorePOSConfig` edit form (printer, tax override).
- **lv3 form** (`entitas_bisnis/lv3/form.html`): Add `OutletPOSConfig` inline section at the bottom of the existing lv3 create/edit form (no separate detail page exists for lv3). Shows effective resolved values alongside override fields.

---

## 4. Frontend POS Screen

**File:** `templates/kasir/pos.html`  
**No base template.** Loads:
- Plus Jakarta Sans from Google Fonts
- Lucide icons via CDN (`https://unpkg.com/lucide@latest`)
- All POS CSS in `<style>` block (Cool theme tokens exactly as spec'd)
- All POS JS in `<script>` block at bottom

### Startup flow

1. Page loads → if `localStorage.kasir_lv3_pk` is set and store is still active → skip selector.
2. Otherwise: full-screen store-selector overlay (dark `#15110d` bg, store cards grid).
3. On store select → load catalog via `GET /kasir/api/catalog/?lv3_pk=X` + config via `GET /kasir/api/config/X/` → render POS.

### JS state

```js
const S = {
  store: null,       // { lv3_pk, name, brandName, config }
  cart: [],          // [{ lineId, item, qty, selections, sig, modLabels, unitPrice, lineTotal }]
  tender: 'cash',    // 'cash'|'card'|'qris'
  discount: null,    // null | { type:'pct'|'amt', val }
  held: [],          // [{ id, label, time, count, total, cart }]
  ui: {
    modPanel:   { open:false, item:null, isEdit:false, lineId:null, sels:{}, qty:1 },
    heldPanel:  false,
    discPanel:  false,
    numpad:     { open:false, value:'' },
    success:    { open:false, data:null },
    toast:      null,
  },
};
```

Single `render()` dispatched after every state mutation. Targeted DOM updates per region (cart list, totals, card bubbles). Event delegation on `#pos-root`.

### Derived values (computed each render)

```
subtotal   = Σ cart[i].lineTotal
discAmt    = type=pct → round(subtotal * val/100) | type=amt → min(val, subtotal)
taxedBase  = max(0, subtotal − discAmt)
tax        = round(taxedBase × config.tax_pct / 100)
grandTotal = taxedBase + tax
```

### Seven UI regions

| Region | Trigger | DOM strategy |
|--------|---------|--------------|
| Catalog + Ticket | always visible | 2-col CSS grid |
| Modifier panel | item with modifiers tapped | `translateX(0)` from right, 560px, scrim |
| Held bills panel | Tertahan chip | slide from right |
| Discount panel | Tambah diskon | slide from right, 460px |
| Numpad sheet | Pay with Tunai | `translateY(0)` slide up over ticket footer |
| Success screen | payment confirmed | full-screen cover |
| Toast | add/hold/discount | bottom-center pill, auto-dismiss 2.2s |

### Line merge logic

Before adding to cart: compute signature `sig = item_pk + '|' + sortedGroupKeys.map(gk => gk+':'+sortedOptPks).join('|')`. If matching `sig` exists in cart → increment `qty` + recalculate `lineTotal`. Else append new line.

### CSS

Cool theme tokens exactly as in handoff `styles.css`. Scoped to `.pos-root[data-theme="cool"]`. No overlap with existing app CSS (standalone page, no shared stylesheets loaded).

---

## 5. Sales Detail Event Log

In `templates/sales/sales_detail.html`, add a "Riwayat Aktivitas" section after the inventory mutations table.

Each `SalesEventLog` entry renders as a timeline row:

```
● [pill: event_type]   actor.name (or "System")   timestamp (dd MMM YYYY HH:mm:ss)
  description (if any)
```

Pill colors:
- Green: `CREATED`, `PAYMENT_PROCESSED`
- Blue: `FIFO_PROCESSED`, `JOURNAL_CREATED`
- Amber: `EDITED`
- Red: `VOIDED`
- Grey: `LOCKED`

`sales_detail` view updated to prefetch `event_logs__actor`.

---

## 6. Out of Scope

- Receipt printing (thermal printer integration)
- Kitchen display / order queue
- Shift management (ShiftLog already modelled, not wired in this phase)
- Barcode scanner hardware integration (search input accepts scan output as text already)
- The "Tweaks" dev panel from the prototype — only Cool/Comfy/Photo direction implemented

---

## 7. File Checklist

| File | Change |
|------|--------|
| `apps/sales/models.py` | Add `created_by` to `SalesHeader`; add `SalesEventLog` |
| `apps/sales/migrations/XXXX_salesheader_createdby_eventlog.py` | New migration |
| `apps/pos_config/models.py` | Add `OutletPOSConfig` |
| `apps/pos_config/migrations/XXXX_outlet_pos_config.py` | New migration |
| `apps/pos_config/utils.py` | New — `resolve_pos_config()` |
| `apps/sales/kasir_views.py` | New — `kasir_pos`, `api_kasir_submit`, `api_kasir_catalog`, `api_kasir_config` |
| `apps/sales/views.py` | Add `created_by` + event log writes to `_handle_sales_save`, `sales_delete` |
| `apps/sales/services.py` | Add event log writes after FIFO + journal creation |
| `apps/sales/urls.py` | Register `/kasir/` URL group |
| `templates/kasir/pos.html` | New — full-screen standalone POS |
| `templates/sales/sales_detail.html` | Add event log timeline section |
| `templates/base.html` | Add Kasir sidebar link below Dashboard |
| `templates/entitas_bisnis/detail.html` | Add MerchantPOSConfig card (lv1) |
| `templates/entitas_bisnis/lv2/detail.html` | Add StorePOSConfig card (lv2) |
| `templates/entitas_bisnis/lv3/form.html` | Add OutletPOSConfig inline section |
| `apps/pos_config/views.py` | Add create/update views for OutletPOSConfig |
| `apps/pos_config/urls.py` | Register outlet config CRUD |
