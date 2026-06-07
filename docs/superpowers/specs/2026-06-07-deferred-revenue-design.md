# Deferred Revenue — Design Spec
**Date:** 2026-06-07
**Status:** Approved
**Scope:** `DeferredRevenueSchedule` and `DeferredRevenueEntry` models + services, living inside `apps/pendapatan/`. Extends Pendapatan core (Phase 4 of master plan).

---

## 1. Overview

When a `PendapatanItem` has `is_deferred=True`, the revenue is not recognized immediately. Instead:
1. On confirm, a `DeferredRevenueSchedule` is created for the item
2. The schedule generates `DeferredRevenueEntry` rows — one per recognition period
3. Each period, an operator (or a management command) calls `recognize_deferred_entry()` which posts a journal and marks the entry recognized

**Accounting flow:**

On confirm (when piutang/cash is recorded):
```
DR  payment_account / piutang_account    ← already in pendapatan journal
CR  deferred_account (liability)         ← replaces direct CR to revenue_account
```

On each period recognition:
```
DR  deferred_account (liability)
CR  recognition_account (revenue)
```

The `PendapatanItem.revenue_account` is NOT credited at confirm time for deferred items. Instead `deferred_account` is credited. This is enforced in `create_pendapatan_journals()` — it checks `item.is_deferred` and swaps the credit leg.

---

## 2. Models

### `DeferredRevenueSchedule`

| Field | Type | Notes |
|---|---|---|
| `pendapatan_item` | OneToOneField(PendapatanItem, CASCADE) | One schedule per deferred item |
| `jumlah_total` | DecimalField(19,4) | = `item.jumlah_bruto` at time of creation |
| `tanggal_mulai` | DateField | First period start |
| `tanggal_selesai` | DateField | Last period end |
| `metode` | CharField choices: `straight_line \| custom` | |
| `recognition_account` | FK(Akun, PROTECT) | Revenue account to recognize into |
| `deferred_account` | FK(Akun, PROTECT) | Liability — pendapatan diterima di muka |
| `created_at` | DateTimeField(auto_now_add) | |

**Properties:**
- `total_recognized` → sum of `entries.filter(status='recognized').jumlah`
- `total_remaining` → `jumlah_total - total_recognized`
- `n_periods` → count of entries

---

### `DeferredRevenueEntry`

| Field | Type | Notes |
|---|---|---|
| `schedule` | FK(DeferredRevenueSchedule, CASCADE) | |
| `periode` | DateField | 1st of month = month key (2025-01-01 = January 2025) |
| `jumlah` | DecimalField(19,4) | Amount to recognize this period |
| `status` | CharField choices: `pending \| recognized \| reversed` | default=pending |
| `jurnal_header` | FK(JurnalHeader, SET_NULL, null, blank) | Set on recognition |

**Meta:** `ordering = ['periode']`, `unique_together = ('schedule', 'periode')`

---

## 3. Service Layer

### `create_deferred_schedule(item) → DeferredRevenueSchedule`

Called by `confirm_pendapatan()` for each item where `is_deferred=True`.

1. Read `item.deferred_tanggal_mulai`, `item.deferred_tanggal_selesai`, `item.deferred_metode`, `item.recognition_account`, `item.deferred_account` directly from the item
2. Create `DeferredRevenueSchedule`
3. Compute periods: iterate months from `tanggal_mulai` to `tanggal_selesai`
4. **straight_line:** `jumlah = jumlah_total / n_months` per period; last period absorbs rounding remainder
5. **custom:** periods created with `jumlah=0` — user fills amounts manually via detail page
6. `DeferredRevenueEntry.objects.bulk_create(entries)`
7. Log `DEFERRED_SCHEDULED` on `PendapatanEventLog`

> **Deferred fields on `PendapatanItem`:** `deferred_account`, `recognition_account`, `deferred_tanggal_mulai`, `deferred_tanggal_selesai`, and `deferred_metode` are stored directly on the item (see Pendapatan spec). This allows `create_pendapatan_journals()` to read `deferred_account` at journal time (before the Schedule exists) and `create_deferred_schedule()` to read the rest without needing a separate data dict.

### `recognize_deferred_entry(entry, user) → JurnalHeader`

Wrapped in `transaction.atomic()`:

1. Guard: `entry.status == 'pending'`
2. Generate jurnal:
   ```
   DR  deferred_account
   CR  recognition_account
   amount = entry.jumlah
   ```
3. `entry.status = 'recognized'`, `entry.jurnal_header = jurnal`
4. Save entry
5. Return `JurnalHeader`

### `reverse_deferred_entry(entry, user)`

For use when voiding a `PendapatanHeader` — called from `void_pendapatan()`.

- Only operates on `entry.status == 'pending'`
- Sets `entry.status = 'reversed'` — no journal (pending entries have no journal to reverse)
- Recognized entries are NOT reversed here — those require a manual adjustment journal

---

## 4. Management Command

`management/commands/recognize_deferred_entries.py`

```
python manage.py recognize_deferred_entries --period 2025-01
```

- Finds all `DeferredRevenueEntry` where `periode = first day of given month` and `status = 'pending'`
- Calls `recognize_deferred_entry(entry, system_user)` for each
- Prints summary: N recognized, N errors
- Designed for monthly cronjob

---

## 5. URL Structure (additions to `/pendapatan/`)

```
/pendapatan/deferred/                         list all active schedules
/pendapatan/deferred/<pk>/                    detail: schedule + entry list
/pendapatan/deferred/<entry_pk>/recognize/    POST → recognize one period
```

---

## 6. Journal Adjustment for Deferred Items

In `create_pendapatan_journals()` (pendapatan_services.py), the credit leg changes when `item.is_deferred=True`:

| Scenario | DR | CR |
|---|---|---|
| Cash, not deferred | payment_account | revenue_account |
| Cash, deferred | payment_account | **deferred_account** |
| Credit, not deferred | piutang_account | revenue_account |
| Credit, deferred | piutang_account | **deferred_account** |

This is the only change to the core journal logic. `recognition_account` is credited later, period by period.

---

## 7. Migration Plan

New migration in `pendapatan` app adding `DeferredRevenueSchedule` and `DeferredRevenueEntry`.

No changes to other apps required. The deferred account and recognition account FKs point to `master_data.Akun` — already available.

The `deferred_data` flow (passing deferred fields from create form to service) requires form changes in the Pendapatan create view — handled as part of this phase's view/template work.
