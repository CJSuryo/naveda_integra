# Utang Module Fix — Design Spec

**Date:** 2026-05-19  
**Status:** Approved  

---

## Problem

The Utang (Accounts Payable) module is disconnected from the Purchase module. When a purchase is saved with a liability offset account (`offset_coa_account.kategori_id == 'kewajiban'`), journals are created correctly by `create_automated_journals()`, but `create_utang_for_purchase()` is never called. Utang records are never created automatically.

Additional bugs identified:
- `UtangTerhapus` (audit trail) is never written on delete
- `reverse_utang_for_purchase()` not called on purchase delete/update — ghost utang records survive
- `create_utang_payment()` has a race condition — outstanding check happens outside the atomic block
- `_next_utang_journal_number()` uses a Python loop instead of ORDER BY (slow + race condition)
- `UtangPembayaranForm` leaks all utang details across all headers (security + UX bug)
- `UtangHeaderForm` shows all entities including customers (should show suppliers only)
- No way to cancel a payment — only whole-header delete
- No `is_locked` field for closing periods
- No `tanggal_jatuh_tempo` — due dates not tracked
- Reporting functions missing

---

## Architecture Decision: JurnalHeader Linking

**Option B chosen:** No `jurnal_header` FK on `UtangHeader`. Access journals via `utang.purchase_header.jurnal_headers.all()`.

Reason: The `jurnal_header` FK creates collision risk (multiple suppliers with same eb_id in `jurnal_map`) and requires a fragile `LIKE` query on `uraian_transaksi`. Since `purchase_header` FK already exists on `UtangHeader`, journal access is always available via two hops with no ambiguity.

---

## Scope: 22 Items

### Models & Migrations

**`UtangHeader` — 2 new fields:**
- `tanggal_jatuh_tempo: DateField(null=True, blank=True, db_index=True)`
- `is_locked: BooleanField(default=False)`
- Properties: `is_overdue`, `days_overdue`

**`SubTransactionType` — 1 new field:**
- `payment_term_days: PositiveIntegerField(null=True, blank=True)`

**Migrations:**
- `utang/migrations/0002_utang_jatuh_tempo_locked.py`
- `purchase/migrations/0005_subtransactiontype_payment_term_days.py`

---

### Service Layer (`utang/services.py`)

#### `create_utang_for_purchase(purchase_header, tanggal_jatuh_tempo=None)`
- Full rewrite. Uses `select_related` + `prefetch_related` on `entitas_groups`.
- Filters items where `offset_coa_account.kategori_id == 'kewajiban'` only.
- Groups per `(entitas_bisnis_id, coa_id)` — one `UtangHeader` per group.
- Auto-computes `jatuh_tempo` from `items[0].sub_transaction_type.payment_term_days` if set; falls back to `tanggal_jatuh_tempo` param.
- Does NOT create journals. Purchase already created them.
- Returns `list[UtangHeader]`.

#### `reverse_utang_for_purchase(purchase_header)`
- Iterates `purchase_header.utang_headers.all()`.
- For each: writes `UtangTerhapus` snapshot, deletes payment journals, deletes header.
- Does NOT touch purchase journals (owned by purchase module).

#### `reverse_utang_header(utang_header, user=None)`
- Writes `UtangTerhapus` snapshot before delete (was missing).
- Deletes payment journals (owned by utang module).
- Does not touch `utang.jurnal_header` (N/A — no FK per Option B).

#### `reverse_utang_payment(payment, user=None)` ← NEW
- Deletes payment's `jurnal_header` if exists (payment journal owned by utang).
- Deletes the `UtangPembayaran` record.
- Calls `_update_utang_status(utang_header)`.

#### `create_utang_payment()` — race condition fix
- Move outstanding check **inside** `transaction.atomic()` with `select_for_update()`.
- Pattern: lock row → recompute outstanding → validate → create.

#### `_next_utang_journal_number()` — performance fix
- Replace Python loop with `ORDER BY -nomor_transaksi + rsplit` pattern.
- Same pattern already used in `_generate_nomor_utang()`.

#### Reporting functions (4 new):
- `get_utang_per_subjek()` — group by entitas, sum total/paid, count invoices
- `get_utang_per_group_akun()` — group by COA account, sum amounts
- `get_utang_aging()` — bucket by days overdue: current, 1–30, 31–60, 60+
- `get_utang_jatuh_tempo(hari_ke_depan=7)` — upcoming due dates

---

### Purchase Integration (`purchase/views.py`)

**Import addition:**
```python
from apps.utang.services import create_utang_for_purchase, reverse_utang_for_purchase
```

**Two CREATE call sites (~lines 1243, 1283):**
```python
create_automated_journals(purchase)   # already returns list, no change needed
...
create_utang_for_purchase(purchase)
```

**Two REVERSE call sites — delete (~line 565) and update (~line 1191):**
```python
reverse_utang_for_purchase(existing_or_purchase)  # added before reverse_automated_journals
reverse_automated_journals(...)
```

**Two cascade-delete call sites (~lines 1215, 1252 — prefix change / split):**
- `existing.delete()` cascades via `on_delete=CASCADE` but skips `UtangTerhapus` snapshot.
- Add explicit `reverse_utang_for_purchase(existing)` before each `.delete()` call.

---

### Forms (`utang/forms.py`)

**`UtangPembayaranForm`:**
- Add `__init__(self, *args, utang_header=None, **kwargs)`
- Filter `utang_detail` queryset to `utang_header.details.all()` when header provided
- Filter `coa_account` to `kategori_id='aset'` (kas/bank only)
- `utang_detail` marked `required=False`

**`UtangHeaderForm`:**
- Add `__init__` that filters `entitas_bisnis` to `relasi__in=['pemasok', 'keduanya'], status_aktif=True`

---

### Views (`utang/views.py`)

**`utang_update` — guard:**
```python
if utang.purchase_header_id:
    messages.error(..., 'Utang dari purchase tidak bisa diedit manual.')
    return redirect('utang:detail', pk=pk)
```

**`utang_delete` — `is_locked` guard:**
```python
if utang.is_locked:
    messages.error(..., 'Transaksi ini sudah terkunci.')
    return redirect('utang:detail', pk=pk)
```

**`utang_pay` — `is_locked` guard + pass `utang_header` to form:**
```python
if utang.is_locked:
    messages.error(..., 'Transaksi ini sudah terkunci.')
    return redirect('utang:detail', pk=pk)
form = UtangPembayaranForm(request.POST, utang_header=utang)
```

**`utang_detail` — pass `utang_header` to payment form:**
```python
payment_form = UtangPembayaranForm(utang_header=utang, initial={'tanggal': utang.tanggal})
```

**`utang_payment_delete` ← NEW:**
- GET: render confirmation page
- POST: call `reverse_utang_payment(payment, request.user)`

**4 reporting views ← NEW:**
- `utang_report_subjek`, `utang_report_akun`, `utang_report_aging`, `utang_report_jatuh_tempo`
- Each: if `request.headers.get('Accept') == 'application/json'` or `?format=json`, return `JsonResponse`; else render HTML template

---

### URLs (`utang/urls.py`)

New patterns:
```
<int:pk>/bayar/<int:payment_pk>/hapus/  →  payment_delete
laporan/subjek/                          →  report_subjek
laporan/akun/                            →  report_akun
laporan/aging/                           →  report_aging
laporan/jatuh-tempo/                     →  report_jatuh_tempo
```

---

### Templates

New templates needed:
- `utang/payment_delete.html` — confirmation page (same pattern as `utang/delete.html`)
- `utang/report_subjek.html`
- `utang/report_akun.html`
- `utang/report_aging.html`
- `utang/report_jatuh_tempo.html`

---

### Tests (`utang/tests.py`)

New/updated test cases:
1. `create_utang_for_purchase` — kewajiban items create headers; non-kewajiban skipped; `payment_term_days` auto-populates `tanggal_jatuh_tempo`
2. `reverse_utang_for_purchase` — `UtangTerhapus` written; purchase journal untouched
3. `create_utang_payment` — concurrent calls (simulate with `select_for_update`) don't overpay
4. `reverse_utang_payment` — payment + journal deleted; status recalculated
5. `utang_update` view — 302 redirect with error if `purchase_header` set
6. `utang_pay` view — 302 redirect with error if `is_locked`
7. `utang_delete` view — 302 redirect with error if `is_locked`
8. `UtangPembayaranForm` — `utang_detail` queryset scoped to header

---

## Implementation Order

1. Migration: `tanggal_jatuh_tempo` + `is_locked` on `UtangHeader`
2. Migration: `payment_term_days` on `SubTransactionType`
3. `utang/models.py` — add new fields + `is_overdue` / `days_overdue` properties
4. `purchase/models.py` — add `payment_term_days`
5. `utang/services.py` — fix `_next_utang_journal_number()`, rewrite `create_utang_for_purchase()`, fix `reverse_utang_header()` (add UtangTerhapus), fix `reverse_utang_for_purchase()`, fix `create_utang_payment()` (select_for_update), add `reverse_utang_payment()`, add 4 reporting functions
6. `purchase/views.py` — wire `create_utang_for_purchase()` at 4 call sites, wire `reverse_utang_for_purchase()` at 4 reverse sites
7. `utang/forms.py` — fix `UtangPembayaranForm` and `UtangHeaderForm`
8. `utang/views.py` — add guards, new `utang_payment_delete`, 4 reporting views
9. `utang/urls.py` — add 5 new URL patterns
10. Templates — 5 new templates
11. `utang/tests.py` — add/update tests
