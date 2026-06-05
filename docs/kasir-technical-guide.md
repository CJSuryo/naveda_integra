# Kasir POS — Technical Background

Explains what happens behind the scenes for each feature in the cashier page. Intended for developers maintaining or extending the POS.

---

## Architecture Overview

```
Browser (templates/kasir/pos.html)
  ├── Standalone page — no base.html, no sidebar
  ├── Cool theme CSS (all in <style> block, CSS custom properties)
  ├── Vanilla JS state machine (S object + render())
  └── Fetches three Django JSON APIs:
        GET  /sales/kasir/api/config/<lv3_pk>/   → POS config for store
        GET  /sales/kasir/api/catalog/?lv3_pk=X  → Product catalog
        POST /sales/kasir/api/submit/             → Create sale

Django (apps/sales/kasir_views.py)
  ├── kasir_pos         → renders the template
  ├── api_kasir_config  → resolves cascading POS config
  ├── api_kasir_catalog → returns inventory items + modifier groups
  └── api_kasir_submit  → creates SalesHeader, runs FIFO, writes journals
```

---

## Store Selector

**Frontend:** On page load, Django renders `<button class="store-card" data-lv3-pk="...">` for every active `EntitasBisnisLv3`. The JS auto-selects from `localStorage.kasir_lv3_pk` on revisit.

**On store select:** Two parallel fetches fire simultaneously:
```js
Promise.all([
  fetch(`/sales/kasir/api/config/${lv3Pk}/`),
  fetch(`/sales/kasir/api/catalog/?lv3_pk=${lv3Pk}`)
])
```

`S.store` is populated, `S.catalog` and `S.categories` are set, and `render()` is called. The store selector div is hidden, the POS canvas is shown.

---

## POS Config Cascade

**Model hierarchy:**
```
EntitasBisnis (lv1)  →  MerchantPOSConfig   (default_tax_pct, STT, accounts)
EntitasBisnisLv2     →  StorePOSConfig       (tax_pct override, printer)
EntitasBisnisLv3     →  OutletPOSConfig      (tax_pct, STT, accounts override)
```

**`resolve_pos_config(lv3)` in `apps/pos_config/utils.py`:**
```
tax_pct:              outlet.tax_pct  →  store.tax_pct  →  merchant.default_tax_pct  →  0
sub_transaction_type: outlet.stt_id   →  merchant.stt_id   (skips lv2)
revenue_account:      outlet.rev_id   →  merchant.rev_id
offset_coa_account:   outlet.off_id   →  merchant.off_id
payment_account:      outlet.pay_id   →  merchant.pay_id
```

lv2 (`StorePOSConfig`) overrides **tax only**; accounting defaults cascade lv3 → lv1 directly because `StorePOSConfig` has no STT/account fields.

The resolved config is returned by `api_kasir_config` and stored in `S.store`. Tax rate, STT ID, and account IDs are used server-side in `api_kasir_submit` to create `SalesItem` records.

---

## Catalog Loading

**`api_kasir_catalog`** queries `InventoryRecord` filtered by the selected lv3:
```python
InventoryRecord.objects.filter(entitas_bisnis_lv3_id=lv3_pk, quantity__gt=0)
```
Falls back to lv1 inventory if no lv3-specific records exist. Excludes bulk item types (`RMB`, `FGB`, `ITMB`).

Each item includes `modifier_groups` resolved from `ProductModifierGroup` → `ModifierGroup` → `ModifierOption` in `apps/pos_catalog`. Categories are derived from `ItemMasterPurchase.kategori` (KategoriItem model).

---

## State Machine

All mutable state lives in a single JS object `S`:
```js
S = {
  store, catalog, categories, activeCat, query,
  cart,     // array of line objects
  tender,   // 'cash'|'card'|'qris'
  discount, // null | {type:'pct'|'amt', val}
  held,     // array of held order snapshots
  ui: { modPanel, heldOpen, discOpen, numpad, success }
}
```

Every state mutation is followed by `render()`, which calls five targeted DOM updaters:
- `renderBrandbar()` — held badge count, cashier name, clock
- `renderPills()` — category pill active state + counts
- `renderGrid()` — product card grid (filtered by activeCat + query)
- `renderTicket()` — cart lines, totals, tender selection, button states
- `renderOverlays()` — overlay open/close via `.on` class toggle + inner HTML

No virtual DOM. `renderGrid()` and `renderTicket()` use `innerHTML` with template literals for full re-render of their regions on every state change.

---

## Line Merge Logic

Adding a product computes a **signature** before inserting:
```js
sig = item_pk + '|' + sortedGroupPks.map(g => g + ':' + sortedOptPks).join('|')
// e.g. "42|7:101,103|9:205"
```

`mergeOrAdd(line)` looks for an existing cart line with the same `sig`:
- **Match found:** increments `qty`, recalculates `lineTotal`. No new line.
- **No match:** prepends new line to `S.cart` (most recent at top).

This means two taps of the same product with identical modifier selections produce one line, but different modifier selections (e.g. one "gula sedikit", one "gula normal") produce two separate lines.

---

## Modifier Panel

**Data flow:**
1. Product card tap → `tapItem(item)` → opens `S.ui.modPanel` with `defaultSels(item)`
2. `defaultSels()` pre-selects options marked `is_default=true` in `ModifierOption`, or the first option for required single-select groups.
3. User taps an option → `toggleOpt(group, optPk)` → updates `S.ui.modPanel.sels`
4. `renderOverlays()` re-renders modifier panel HTML immediately (no debounce)
5. Confirm → `confirmMod()` → builds final line, calls `mergeOrAdd()`

Single-select groups (`max_selections === 1`) behave as radio buttons — selecting one deselects the previous. Multi-select groups enforce `max_selections` cap.

---

## Pricing Calculation

Computed every render via `computeTotals()`:
```
subtotal   = Σ (line.unitPrice × line.qty)
discAmt    = pct → round(subtotal × val/100)  |  amt → min(val, subtotal)
taxedBase  = max(0, subtotal − discAmt)
tax        = round(taxedBase × taxPct / 100)
grand      = taxedBase + tax
```

`taxPct` comes from `S.store.taxPct` (resolved from POS config cascade). Default 11 if no store loaded yet.

`unitPrice` for a line = `item.selling_price` + sum of `additional_price` for all selected modifier options.

---

## Hold / Resume

**Hold:** `holdBill()` snapshots `S.cart` into `S.held` array with a timestamp label, then clears the active cart. The held snapshot is in-memory only — it is NOT persisted to the database. Refreshing the page loses held orders.

**Resume:** `resumeHeld(heldId)` clones the snapshot back into `S.cart` with fresh `lineId`s (to avoid ID collisions), removes it from `S.held`.

---

## Payment Submit Flow

On **Selesaikan** (non-cash: immediate; cash: after numpad confirm):

**Client → Server POST `/sales/kasir/api/submit/`:**
```json
{
  "lv3_pk": 3,
  "cart": [{ "item_pk": 42, "qty": 2, "unit_price": 28000, "modifier_labels": "Gula Sedikit" }],
  "tender": "cash",
  "tendered_amount": 60000,
  "discount": { "type": "pct", "val": 10 }
}
```

CSRF token sent via `X-CSRFToken` header (read from `<form style="display:none">{% csrf_token %}</form>` in the template).

**Server-side (`api_kasir_submit`):**

1. **Resolve POS config** — re-fetches `OutletPOSConfig` → `MerchantPOSConfig` cascade for the lv3. Gets `stt_id`, `revenue_id`, `offset_id`, `payment_id`, `tax_pct`.

2. **Validate config** — returns 400 if STT or revenue/offset accounts are missing. This is the most common error when a store is not fully configured.

3. **Server-side total recomputation** — subtotal, discount, tax, grand total recalculated from the posted cart. Client totals are **never trusted**.

4. **`SalesHeader.objects.create(..., created_by=request.user)`** — sets the user FK on the header.

5. **`SalesEntitasBisnis.objects.create(...)`** — links the sale to lv1/lv2/lv3 entity IDs extracted from the resolved lv3 object.

6. **`SalesItem.objects.create(...)` per cart line** — uses `offset_coa_account_id`, `revenue_account_id`, `payment_account_id` from resolved config. `inventory_account_id` comes from `ItemMasterPurchase.coa_account_id`.

7. **`process_sales_fifo(sales)`** — consumes inventory using FIFO batches (`FIFOBatch`). Updates `InventoryRecord.quantity`, creates `SalesItemFIFOAllocation` records, sets `SalesItem.cogs_amount`.

8. **`create_sales_automated_journals(sales)`** — generates `JurnalHeader` + `JurnalDetail` entries:
   - Debit HPP / Credit Persediaan (COGS entry)
   - Debit Kas/Bank / Credit Pendapatan (revenue entry)
   - Debit Kas / Credit PPN Keluaran (tax entry, if applicable)

9. **`SalesEventLog` writes** — four entries written inside the atomic block:
   ```
   CREATED         (actor = cashier user)
   FIFO_PROCESSED  (actor = None / system)
   JOURNAL_CREATED (actor = None / system)
   PAYMENT_PROCESSED (actor = cashier user, includes tender + change amount)
   ```

10. **Response** — `{ ok: true, trx_id: "TRX-SAL-049", grand_total: "...", change: "..." }`

Everything from step 4 onward runs inside `transaction.atomic()`. If any step fails (e.g. insufficient stock), the entire transaction rolls back.

---

## Event Log

`SalesEventLog` records a timestamped audit trail for every `SalesHeader`. Written from three places:

| Source | Events written |
|---|---|
| `api_kasir_submit` (POS) | CREATED, FIFO_PROCESSED, JOURNAL_CREATED, PAYMENT_PROCESSED |
| `_handle_sales_save` (form) | CREATED or EDITED, FIFO_PROCESSED, JOURNAL_CREATED |
| `sales_delete` (delete view) | VOIDED |

Displayed as a timeline in `sales_detail.html` under "Riwayat Aktivitas". Badge colors: green (CREATED/PAYMENT_PROCESSED), amber (EDITED), red (VOIDED), blue (FIFO/JOURNAL), grey (LOCKED).

---

## FIFO & Journal Wiring (reused from regular sales)

The POS submit endpoint calls the same service functions used by the regular `sales_create` form:
- `process_sales_fifo` — `apps/sales/services.py`
- `create_sales_automated_journals` — `apps/sales/services.py`

This ensures POS sales and form-entry sales produce identical inventory movements and journal entries. The only difference is that POS sales set `SalesHeader.created_by` and do not require manual account selection.

---

## Key Models

| Model | App | Purpose |
|---|---|---|
| `SalesHeader` | `sales` | Transaction header, holds `created_by` FK |
| `SalesEventLog` | `sales` | Audit log per transaction |
| `SalesEntitasBisnis` | `sales` | Links sale to EB lv1/lv2/lv3 |
| `SalesItem` | `sales` | One item line per transaction |
| `SalesItemFIFOAllocation` | `sales` | Per-batch FIFO consumption record |
| `MerchantPOSConfig` | `pos_config` | POS defaults at lv1 (merchant) |
| `StorePOSConfig` | `pos_config` | Tax/printer override at lv2 |
| `OutletPOSConfig` | `pos_config` | Full override at lv3 (outlet) |
| `ModifierGroup` | `pos_catalog` | Grouped options for a product |
| `ModifierOption` | `pos_catalog` | Single option within a group |
| `ProductModifierGroup` | `pos_catalog` | Links an item to its modifier groups |
| `InventoryRecord` | `inventory` | Current stock per item per location |
| `FIFOBatch` | `purchase` | FIFO cost batches for stock consumption |

---

## Adding a New Outlet to POS

1. Create `EntitasBisnisLv3` (or ensure it exists).
2. On `EntitasBisnis` (lv1) detail page → **POS Configuration** → set `MerchantPOSConfig` with at minimum: `sub_transaction_type`, `revenue_account`, `offset_coa_account`, `default_payment_account`, `default_tax_pct`.
3. On `EntitasBisnisLv3` form page → **Outlet POS Config** → optionally override any lv1 defaults.
4. Ensure the outlet has inventory (`InventoryRecord` records with `entitas_bisnis_lv3_id` set, or fallback via lv1 entity).
5. The outlet will now appear in the POS store selector.
