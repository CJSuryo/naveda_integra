# Recurring Revenue — Design Spec
**Date:** 2026-06-07
**Status:** Approved
**Scope:** `RecurringTemplate` model + services, living inside `apps/pendapatan/`. Extends Pendapatan core (Phase 5 of master plan). Parallel-buildable with Deferred Revenue.

---

## 1. Overview

`RecurringTemplate` stores a template for revenue that recurs on a schedule (monthly rent, quarterly management fee, etc.). On each trigger (manual or via management command), it generates a new `PendapatanHeader` + items from the template and optionally auto-confirms it.

---

## 2. Model

### `RecurringTemplate`

| Field | Type | Notes |
|---|---|---|
| `nama` | CharField(255) | e.g. "Sewa Kantor Gedung A" |
| `entitas_bisnis` | FK(EntitasBisnis, PROTECT) | |
| `entitas_bisnis_lv2` | FK(EntitasBisnisLv2, PROTECT, null, blank) | |
| `entitas_bisnis_lv3` | FK(EntitasBisnisLv3, PROTECT, null, blank) | |
| `deskripsi_item` | TextField | Free-text item description for generated items |
| `kategori` | CharField choices: same as `PendapatanItem.kategori` | |
| `sub_transaction_type` | FK(SubTransactionType, PROTECT) | module=pendapatan |
| `jumlah` | DecimalField(19,4) | Amount per occurrence |
| `revenue_account` | FK(Akun, PROTECT) | |
| `payment_account` | FK(Akun, PROTECT, null, blank) | |
| `payment_type` | CharField choices: `cash \| credit` | |
| `frekuensi` | CharField choices: `harian \| mingguan \| bulanan \| triwulanan \| semesteran \| tahunan` | |
| `tanggal_mulai` | DateField | First occurrence |
| `tanggal_selesai` | DateField(null, blank) | null = no end date |
| `tanggal_berikutnya` | DateField | Next scheduled occurrence — auto-computed after each generation |
| `auto_confirm` | BooleanField(default=False) | If True, generated PendapatanHeader is immediately confirmed |
| `is_active` | BooleanField(default=True) | |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` | DateTimeField(auto_now_add) | |

**Meta:** `ordering = ['tanggal_berikutnya']`

**Post-save signal or `save()` override:** On create, if `tanggal_berikutnya` is not set, initialize it to `tanggal_mulai`.

---

## 3. Service Layer

### `compute_next_date(current_date, frekuensi) → date`

Pure function. No DB access.

| frekuensi | Logic |
|---|---|
| harian | +1 day |
| mingguan | +7 days |
| bulanan | +1 month (same day, clamp to last day of month) |
| triwulanan | +3 months |
| semesteran | +6 months |
| tahunan | +1 year |

### `generate_from_recurring(template, user) → PendapatanHeader`

Wrapped in `transaction.atomic()`:

1. Create `PendapatanHeader`:
   - `source_type = 'recurring'`
   - `source_recurring = template`
   - `payment_type = template.payment_type`
   - `tanggal = template.tanggal_berikutnya`
   - `status = 'draft'`

2. Create `PendapatanEntitasBisnis` from template's EB fields

3. Create `PendapatanItem`:
   - `deskripsi_item = template.deskripsi_item`
   - `kategori = template.kategori`
   - `sub_transaction_type = template.sub_transaction_type`
   - `jumlah_bruto = template.jumlah`
   - `revenue_account = template.revenue_account`
   - `payment_account = template.payment_account`
   - `is_deferred = False` (deferred recurring not supported in v1)

4. Update `template.tanggal_berikutnya = compute_next_date(template.tanggal_berikutnya, template.frekuensi)`

5. If `template.tanggal_selesai` is set and new `tanggal_berikutnya > tanggal_selesai`:
   - `template.is_active = False`

6. Save template

7. Log `RECURRING_GENERATED` on `PendapatanEventLog` of the new header

8. If `template.auto_confirm = True`:
   - Call `confirm_pendapatan(header, user)` from `pendapatan_services`

9. Return `header`

---

## 4. Management Command

`management/commands/generate_recurring_pendapatan.py`

```
python manage.py generate_recurring_pendapatan
```

- Finds all `RecurringTemplate` where:
  - `is_active = True`
  - `tanggal_berikutnya ≤ today`
  - `tanggal_selesai is None OR tanggal_berikutnya ≤ tanggal_selesai`
- Calls `generate_from_recurring(template, system_user)` for each
- Prints summary: N generated, N confirmed, N errors

Designed for daily cron run (idempotent per day — each template advances `tanggal_berikutnya` after generation so re-runs skip already-generated ones).

---

## 5. URL Structure (additions to `/pendapatan/`)

```
/pendapatan/recurring/                  list all templates
/pendapatan/recurring/create/           buat template baru
/pendapatan/recurring/<pk>/             detail + history of generated pendapatan
/pendapatan/recurring/<pk>/edit/
/pendapatan/recurring/<pk>/delete/      soft delete — set is_active=False
/pendapatan/recurring/<pk>/generate/    POST → trigger generate_from_recurring manually
```

---

## 6. Report: Calendar View

`/pendapatan/reports/recurring/`

Shows a calendar (or list grouped by month) of all upcoming `tanggal_berikutnya` for active templates. Allows operators to see what's scheduled in the next 3 months and manually trigger early if needed.

---

## 7. Migration Plan

New migration in `pendapatan` app adding `RecurringTemplate`.

Also requires:
- `PendapatanHeader.source_recurring` FK (added in this migration as an `ALTER TABLE` — null/blank, no data impact)

Build order relative to other phases:
- Depends on: Pendapatan core (Phase 3)
- Does NOT depend on: Deferred Revenue — can be built in parallel with Phase 4

---

## 8. v1 Limitations

- Deferred recurring not supported — `RecurringTemplate` always generates non-deferred items
- Only one item per template — multi-item recurring requires multiple templates
- No catch-up logic — if cron was down for 3 days and frekuensi=harian, it generates one, not three. Operator should run manual generate for missed dates.
