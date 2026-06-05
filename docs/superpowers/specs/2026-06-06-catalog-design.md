# Catalog & Harga Jual — Design Spec
**Date:** 2026-06-06
**Status:** Approved
**Scope:** New Catalog management page in `pos_catalog` app — manage selling prices per EntitasBisnis, catalog logs, and `unit_price` → `unit_cost` rename in inventory.

---

## 1. Overview

Admins manage which inventory items are available for sale at kasir, at what price, and how they appear. Config is at EntitasBisnis (lv1) level — all outlets under an EB share the same catalog. A separate Catalog Logs page tracks all field changes.

---

## 2. Models — `apps/pos_catalog/`

### `CatalogItem`

| Field | Type | Notes |
|---|---|---|
| `entitas_bisnis` | FK(EntitasBisnis, CASCADE) | |
| `item` | FK(ItemMasterPurchase, PROTECT) | |
| `selling_price` | Decimal(15,4) | Required |
| `display_name` | CharField(200, blank) | Overrides `item.nama` in kasir |
| `display_order` | IntegerField | Default: `max(existing for this EB) + 1`, or `1` if none exist |
| `product_image` | ImageField(`catalog/`) | Optional |
| `is_active` | BooleanField | Default True |
| `created_at` | DateTimeField(auto_now_add) | |
| `updated_at` | DateTimeField(auto_now) | |

Constraints: `unique_together = ('entitas_bisnis', 'item')`

### `CatalogItemLog`

| Field | Type | Notes |
|---|---|---|
| `catalog_item` | FK(CatalogItem, CASCADE) | |
| `field_name` | CharField(50) | e.g. `'selling_price'`, `'is_active'`, `'display_name'` |
| `old_value` | TextField | String representation of old value |
| `new_value` | TextField | String representation of new value |
| `changed_at` | DateTimeField(auto_now_add) | |
| `changed_by` | FK(User, SET_NULL, null=True) | |

Logs written in upsert endpoint before saving — diff old vs new fields, one row per changed field.

---

## 3. URLs — added to `apps/pos_catalog/urls.py`

```
GET  /pos/catalog/<eb_pk>/               catalog_list        Main catalog page
GET  /pos/catalog/<eb_pk>/items/         catalog_items_ajax  AJAX: filter items by tipe_item
POST /pos/catalog/<eb_pk>/items/upsert/  catalog_upsert      AJAX: create/update CatalogItem + write logs
GET  /pos/catalog/<eb_pk>/logs/          catalog_logs        Catalog Logs page (paginated)
```

All views: `@login_required`, check `pos_config_manage` permission.

---

## 4. Views

### `catalog_list(request, eb_pk)`
Renders page shell: EB name in header, "Tambah Harga Jual" button, "Catalog Logs →" link, empty table placeholder. Category filter buttons hidden until "Tambah Harga Jual" is clicked (JS shows them).

### `catalog_items_ajax(request, eb_pk)`
GET only. Reads `?tipe_item=FG` param. Queries:
```python
items = ItemMasterPurchase.objects.filter(
    tipe_item=tipe_item,
    inventory_records__entitas_bisnis=eb,
).distinct().order_by('nama')
```
Annotates each item with its `CatalogItem` if one exists for this EB. Returns rendered HTML fragment (table rows) via `JsonResponse({'html': ...})`.

### `catalog_upsert(request, eb_pk)`
POST only. Accepts `multipart/form-data`: `item_id`, `selling_price`, `display_name`, `display_order`, `is_active`, `product_image` (file, optional).

Flow:
1. `get_or_create` CatalogItem by `(entitas_bisnis, item)`
2. Diff old vs new values for all changed fields
3. Write one `CatalogItemLog` row per changed field
4. Save CatalogItem
5. Return `{ success: true, item: { id, display_name, selling_price, is_active, display_order, image_url } }`

### `catalog_logs(request, eb_pk)`
Paginated (50/page) table of `CatalogItemLog` for all `CatalogItem` records belonging to this EB. Optional `?q=` search by item name. Ordered by `-changed_at`.

---

## 5. Page UX

### Catalog List Page

**Initial state:**
```
[Catalog — {EB Name}]                          [Catalog Logs →]
[Tambah Harga Jual ▼]
──────────────────────────────────────────────
Pilih kategori untuk menampilkan item.
```

**After "Tambah Harga Jual" click:**
Category buttons appear: `[FG] [FGB] [RM] [RMB] [ITM] [ITMB]`

Selected button stays highlighted. Clicking a different button replaces table content.

**After category selected (AJAX loads rows):**
```
Item        | Display Name | Harga Jual | Active | Order | Image | Aksi
Item A      | Coffee Latte | Rp 35.000  | ✓      | 1     | 🖼    | [Edit]
Item B      | —            | —          | —      | —     | —     | [Edit]
```

Items with no `CatalogItem` show blank price/active/order/image cells.

### Inline Edit Rules

1. Click **Edit** → row cells become inputs; button changes to **Save** + **Cancel**; all other Edit buttons disabled
2. Click outside dirty row → `confirm("Ada perubahan belum disimpan. Discard?")` — Yes discards and restores, No keeps focus on row
3. **Save** → POST to upsert endpoint with `FormData` → on success, replaces row DOM with server HTML, re-enables other Edit buttons
4. **Cancel** → restore original values, re-enables other Edit buttons
5. Image field shows current thumbnail (if set); new file input only replaces image if a file is selected

### Catalog Logs Page

```
[← Catalog]  Catalog Logs — {EB Name}
[Search: item name...]

Tanggal       | Item      | Field         | Dari      | Ke        | Oleh
2026-06-06    | Item A    | selling_price | Rp 10.000 | Rp 15.000 | admin@...
2026-06-06    | Item A    | is_active     | False     | True      | admin@...
```

Paginated, newest first.

---

## 6. Entry Points

### EB List Page
Add **Catalog** button to lv1 row actions:
```
[Tambah Cabang] [Detail] [Catalog] [Hapus]
```
Links to `/pos/catalog/<eb_pk>/`.

### Setup Wizard
Add item 7 to **Direkomendasikan** section:
- Title: "Catalog & Harga Jual"
- ✓ when: `CatalogItem.objects.filter(entitas_bisnis=eb, is_active=True).exists()`
- Action button: → `/pos/catalog/<eb_pk>/`
- `checks` key: `catalog_ok`

---

## 7. `unit_price` → `unit_cost` Rename (Inventory)

| Location | Change |
|---|---|
| `InventoryRecord.unit_price` | `verbose_name='Unit Cost'` |
| `InventoryRecordForm` | label → `'Unit Cost'` |
| `apps/inventory/admin.py` | `list_display` column header update |
| Migration | `AlterField` for verbose_name — no data change |

Field name `unit_price` stays unchanged in Python/DB (renaming the field itself would require data migration and break all existing queries — not worth it for a label change).

---

## 8. Out of Scope

- Per-outlet price override (deferred — all outlets under same EB share one catalog)
- Bulk price import/export
- Catalog → kasir sync (kasir queries `CatalogItem` directly)
- Product categories/tags
