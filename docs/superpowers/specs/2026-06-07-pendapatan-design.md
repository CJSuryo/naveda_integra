# Pendapatan (Revenue) — Design Spec
**Date:** 2026-06-07
**Status:** Approved
**Scope:** New `apps/pendapatan/` app — core revenue transaction module. Deferred Revenue and Recurring are separate specs that extend this app.

---

## 1. Overview

Pendapatan records non-inventory revenue (rent, services, interest, management fees, etc.). It uses the same multi-EB join-table pattern as Sales but has no FIFO or ItemMaster dependency — all items are free-text.

Transactions can be:
- **Manual** — entered directly
- **From Sales** — `SalesHeader` with `payment_type=credit` auto-generates a piutang; the revenue journal comes from sales itself. *Pendapatan is not created from sales — sales already generates its own revenue journal.*
- **Recurring** — generated from a `RecurringTemplate` (see recurring spec)

On confirm:
- Journals are auto-generated per item
- If `payment_type=credit` → `PiutangHeader` is created in `apps/piutang/`
- If any item has `is_deferred=True` → `DeferredRevenueSchedule` is created (see deferred spec)

---

## 2. Cross-Cutting Changes

### `SubTransactionType.MODULE_CHOICES` — add `'pendapatan'`

In `apps/purchase/models.py`, extend the choices list:

```python
MODULE_CHOICES = [
    ('purchase', 'Purchase'),
    ('sales', 'Sales'),
    ('pendapatan', 'Pendapatan'),   # NEW
]
```

New migration needed in `purchase` app.

### `SalesHeader.payment_type` — new field

Add to `apps/sales/models.py` on `SalesHeader`:

```python
payment_type = models.CharField(
    max_length=10,
    choices=[('cash', 'Cash'), ('credit', 'Kredit')],
    default='cash',
    verbose_name='Tipe Pembayaran',
)
```

- Default `cash` — all existing records treated as cash, no data breakage
- New migration in `sales` app
- In `confirm_sales()` service: if `payment_type='credit'` → call `create_piutang_from_sales(header, user)`

---

## 3. Models

### `PendapatanHeader`

| Field | Type | Notes |
|---|---|---|
| `transaction_id` | CharField(100, unique, editable=False) | Auto TRX-PND-001 |
| `tanggal` | DateField(db_index, default=today) | |
| `deskripsi` | TextField(blank) | |
| `source_type` | CharField choices: `manual \| from_sales \| recurring` | default=manual |
| `source_sales` | FK(SalesHeader, SET_NULL, null, blank) | Populated when from_sales |
| `source_recurring` | FK(RecurringTemplate, SET_NULL, null, blank) | Populated when recurring |
| `payment_type` | CharField choices: `cash \| credit` | Applies to whole transaction |
| `status` | CharField choices: `draft \| confirmed \| voided` | default=draft |
| `is_locked` | BooleanField(default=False) | Period close |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` / `updated_at` | DateTimeField auto | |

**Auto-number:** `TRX-PND-` prefix, `select_for_update` pattern identical to `TRX-SAL-` in sales.

**Meta:** `ordering = ['-tanggal', '-created_at']`

---

### `PendapatanEntitasBisnis`

Join table — mirrors `SalesEntitasBisnis` exactly.

| Field | Type | Notes |
|---|---|---|
| `pendapatan_header` | FK(PendapatanHeader, CASCADE) | |
| `entitas_bisnis` | FK(EntitasBisnis, PROTECT) | |
| `entitas_bisnis_lv2` | FK(EntitasBisnisLv2, PROTECT, null, blank) | |
| `entitas_bisnis_lv3` | FK(EntitasBisnisLv3, PROTECT, null, blank) | |
| `payment_account` | FK(Akun, PROTECT, null, blank) | Kas/bank (cash) or piutang account (credit) |

**Indexes:** `(pendapatan_header, entitas_bisnis)`, `(entitas_bisnis_lv2)`, `(entitas_bisnis_lv3)`

---

### `PendapatanItem`

| Field | Type | Notes |
|---|---|---|
| `pendapatan_eb` | FK(PendapatanEntitasBisnis, CASCADE) | |
| `deskripsi_item` | TextField | Free text — no ItemMaster FK |
| `kategori` | CharField choices: `sewa \| jasa \| bunga \| dividen \| komisi \| royalti \| management_fee \| penjualan_aset \| lainnya` | |
| `sub_transaction_type` | FK(SubTransactionType, PROTECT) | module=pendapatan |
| `jumlah_bruto` | DecimalField(19,4) | Pre-tax amount |
| `revenue_account` | FK(Akun, PROTECT) | Auto-fill from STT mapping |
| `payment_account` | FK(Akun, PROTECT, null, blank) | Kas/bank (cash) or piutang account (credit) — can override EB-level |
| `tax` | DecimalField(19,4, null, blank) | Tax nominal |
| `tax_type` | CharField choices: `ppn_keluaran \| pph_23 \| pph_21 \| pph_4_2` | blank |
| `tax_account` | FK(Akun, PROTECT, null, blank) | |
| `tax_payment` | CharField choices: `belum_transfer \| sudah_transfer` | blank |
| `tax_payment_account` | FK(Akun, PROTECT, null, blank) | |
| `is_deferred` | BooleanField(default=False) | Reveals deferred fields in UI |
| `deferred_account` | FK(Akun, PROTECT, null, blank) | Liability (pendapatan diterima di muka) — required when is_deferred=True |
| `recognition_account` | FK(Akun, PROTECT, null, blank) | Revenue account for period recognition — required when is_deferred=True |
| `deferred_tanggal_mulai` | DateField(null, blank) | First recognition period |
| `deferred_tanggal_selesai` | DateField(null, blank) | Last recognition period |
| `deferred_metode` | CharField choices: `straight_line \| custom`, blank | default=straight_line |

**Indexes:** `(pendapatan_eb,)`, `(sub_transaction_type,)`

---

### `PendapatanEventLog`

Mirrors `SalesEventLog`.

| Field | Type | Notes |
|---|---|---|
| `pendapatan_header` | FK(PendapatanHeader, CASCADE) | |
| `event_type` | CharField choices (see below) | |
| `description` | TextField(blank) | |
| `actor` | FK(User, SET_NULL, null, blank) | |
| `timestamp` | DateTimeField(auto_now_add) | |

Event choices: `CREATED | CONFIRMED | VOIDED | JOURNAL_CREATED | PIUTANG_CREATED | DEFERRED_SCHEDULED | RECURRING_GENERATED`

**Meta:** `ordering = ['timestamp']`

---

## 4. Service Layer (`pendapatan_services.py`)

### `confirm_pendapatan(header, user)`

Main orchestrator. Wrapped in `transaction.atomic()`.

1. Guard: `header.status == 'draft'` — raise if not
2. Validate all required accounts present on each item
3. Call `create_pendapatan_journals(header, user)`
4. If `header.payment_type == 'credit'` → `create_piutang_from_pendapatan(header, user)` — log `PIUTANG_CREATED`
5. For each `PendapatanItem` where `is_deferred=True` → `create_deferred_schedule(item)` — log `DEFERRED_SCHEDULED`
6. `header.status = 'confirmed'`, save
7. Log `CONFIRMED`

### `create_pendapatan_journals(header, user) → list[JurnalHeader]`

Per `PendapatanEntitasBisnis` group, one `JurnalHeader`. Per item within the group:

**Cash:**
```
DR  payment_account (item-level, falls back to EB-level)
CR  revenue_account
```

**Credit:**
```
DR  piutang_account (from PendapatanEntitasBisnis.payment_account)
CR  revenue_account
```

**If tax exists (per tax_type):**
- `ppn_keluaran, belum_transfer`: `DR payment_account / CR tax_account` + separate `DR tax_account / CR tax_payment_account`
- `pph_23/21/4_2`: standard withholding logic (same as SalesItem tax handling)

Log `JOURNAL_CREATED`.

### `create_piutang_from_pendapatan(header, user) → PiutangHeader`

Delegates to `piutang_services.create_piutang_from_pendapatan(header, user)`.

### `void_pendapatan(header, user)`

Wrapped in `transaction.atomic()`:

1. Guard: `header.status == 'confirmed'` and not `is_locked`
2. Reverse all `JurnalHeader` linked to this transaction (counter-entries)
3. If linked `PiutangHeader` exists and status not in (paid, partial) → set `status = 'cancelled'`
4. If linked `PiutangHeader` status is partial → raise error (partial payments exist — cannot void)
5. Reverse all `DeferredRevenueEntry` with status=pending (set to reversed)
6. `header.status = 'voided'`, save
7. Log `VOIDED`

### `get_pendapatan_dashboard_kpi(entitas_bisnis=None) → dict`

Returns for current month:
- Total pendapatan (vs last month)
- Breakdown cash vs credit
- Total deferred revenue outstanding (all pending DeferredRevenueEntry)
- Recurring due in next 30 days
- Top 5 kategori by jumlah_bruto

---

## 5. API Endpoint

`GET /pendapatan/api/stt-defaults/?stt_id=<id>`

Returns JSON: `{revenue_account_id, revenue_account_nama, payment_account_id, payment_account_nama}` from the STT's default CoA mapping. Used for auto-fill when user selects `sub_transaction_type` on the item form.

---

## 6. URL Structure

```
/pendapatan/                            dashboard
/pendapatan/list/                       list semua transaksi
/pendapatan/create/                     form buat baru
/pendapatan/<pk>/                       detail
/pendapatan/<pk>/edit/                  edit (draft only)
/pendapatan/<pk>/confirm/               POST → confirm_pendapatan
/pendapatan/<pk>/void/                  POST → void_pendapatan

# Reports
/pendapatan/reports/summary/            per kategori / per EB / per periode
/pendapatan/reports/deferred/           deferred revenue position
/pendapatan/reports/recurring/          calendar view upcoming recurring

# API
/pendapatan/api/stt-defaults/
```

Deferred and Recurring URLs defined in their respective specs.

---

## 7. Dashboard KPI Cards

1. Total pendapatan bulan ini (vs bulan lalu — % change)
2. Cash vs Credit breakdown (pie or stacked bar)
3. Deferred revenue belum diakui (total outstanding DeferredRevenueEntry pending)
4. Recurring jatuh dalam 30 hari ke depan (count + total amount)
5. Top 5 kategori bulan ini (bar chart or table)

---

## 8. Migration Plan

1. New app `pendapatan` — `python manage.py startapp pendapatan` inside `apps/`
2. Register in `INSTALLED_APPS`
3. Register in root `urls.py` under `/pendapatan/`
4. Initial migration: `PendapatanHeader`, `PendapatanEntitasBisnis`, `PendapatanItem`, `PendapatanEventLog`
5. Add `SubTransactionType` module choice `pendapatan` (migration in purchase app)
6. Add `SalesHeader.payment_type` (migration in sales app)
7. `source_recurring` FK on `PendapatanHeader` added in recurring migration (avoids circular dependency during initial build)
