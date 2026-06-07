# Piutang (Accounts Receivable) — Design Spec
**Date:** 2026-06-07
**Status:** Approved
**Scope:** Full implementation of `apps/piutang/` — replacing the existing stub. Mirrors `apps/utang/` architecture on the receivable side.

---

## 1. Overview

Piutang tracks money owed **to** the company. It can originate from three sources:
- **Manual** — entered directly by user
- **From Sales** — auto-created when a credit sale is confirmed (see Pendapatan spec for the sales-side trigger)
- **From Pendapatan** — auto-created when a credit revenue transaction is confirmed

Key capabilities: payment recording, installment schedules (flat/anuitas), short-term ↔ long-term reclassification, bad-debt write-off, approval workflow, attachments, aging report.

---

## 2. Models

### `PiutangHeader`

| Field | Type | Notes |
|---|---|---|
| `nomor_piutang` | CharField(100, unique, editable=False) | Auto TRX-PIU-001 |
| `tanggal` | DateField(db_index, default=today) | |
| `jatuh_tempo` | DateField(null, blank) | |
| `debitur` | CharField(255, blank) | Free-text external party name |
| `entitas_bisnis` | FK(EntitasBisnis, SET_NULL, null, blank) | Internal EB receiving payment |
| `deskripsi` | CharField(512, blank) | |
| `source_type` | CharField choices: `manual \| from_sales \| from_pendapatan` | default=manual |
| `source_sales` | FK(SalesHeader, SET_NULL, null, blank) | Populated when from_sales |
| `source_pendapatan` | FK(PendapatanHeader, SET_NULL, null, blank) | Populated when from_pendapatan |
| `jumlah_pokok` | DecimalField(19,4) | Total face value |
| `jumlah_terbayar` | DecimalField(19,4, default=0) | Denormalized — updated on each payment |
| `status` | CharField choices: `draft \| open \| partial \| paid \| overdue \| written_off \| cancelled` | default=draft |
| `jenis_jangka_waktu` | CharField choices: `short_term \| long_term` | default=short_term |
| `requires_approval` | BooleanField(default=False) | |
| `approval_status` | CharField choices: `'' \| pending \| approved \| rejected` | blank=True |
| `approved_by` | FK(User, SET_NULL, null, blank) | |
| `approved_at` | DateTimeField(null, blank) | |
| `coa_piutang_account` | FK(Akun, PROTECT) | Balance sheet receivable account |
| `jenis_bunga` | CharField choices: `tanpa_bunga \| flat \| anuitas` | default=tanpa_bunga |
| `bunga_persen` | DecimalField(8,4, null, blank) | Annual rate |
| `jumlah_angsuran` | PositiveSmallIntegerField(null, blank) | Number of installments |
| `periode_angsuran` | CharField choices: `bulanan \| triwulanan \| semesteran \| tahunan` | default=bulanan |
| `is_locked` | BooleanField(default=False) | Set when period closes |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` / `updated_at` | DateTimeField auto | |

**Auto-number:** `TRX-PIU-` prefix, `select_for_update` pattern identical to `UTG-XXXX` in utang.

**Properties:**
- `sisa_piutang` → `jumlah_pokok - jumlah_terbayar`
- `is_overdue` → `jatuh_tempo` past today and status not in (paid, cancelled, written_off)
- `days_overdue` → days past `jatuh_tempo`, 0 if not overdue
- `can_pay` → status in (open, partial, overdue) and not is_locked
- `can_reklasifikasi` → status in (open, partial, overdue) and jenis_jangka_waktu=long_term and jatuh_tempo set
- `entitas_display` → debitur if set, else entitas_bisnis name

**Meta:** `ordering = ['-tanggal', '-created_at']`  
**Indexes:** `(tanggal, status)`, `(source_type, status)`

---

### `PiutangDetail`

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | FK(PiutangHeader, CASCADE) | |
| `deskripsi` | CharField(255, blank) | |
| `jumlah` | DecimalField(19,4) | |
| `revenue_account` | FK(Akun, PROTECT, null, blank) | Reference only — journal already made at source |
| `sub_transaction_type` | FK(SubTransactionType, SET_NULL, null, blank) | |

---

### `PiutangPenerimaan`

Mirrors `UtangPembayaran`. Records each payment received.

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | FK(PiutangHeader, CASCADE, related_name='penerimaan') | |
| `tanggal_terima` | DateField(db_index, default=today) | |
| `jumlah_diterima` | DecimalField(19,4) | |
| `angsuran_no` | PositiveSmallIntegerField(null, blank) | Which installment number |
| `payment_account` | FK(Akun, PROTECT) | Kas/bank receiving the funds |
| `jurnal_header` | FK(JurnalHeader, SET_NULL, null, blank) | Auto-generated |
| `metode_penerimaan` | CharField choices: `transfer \| tunai \| giro \| cek` | |
| `nomor_referensi` | CharField(100, blank) | Transfer/check number |
| `catatan` | CharField(512, blank) | |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` | DateTimeField(auto_now_add) | |

**Meta:** `ordering = ['-tanggal_terima', '-created_at']`

---

### `PiutangReklasifikasi`

Mirrors `UtangReklasifikasi`. Records short-term ↔ long-term reclassification.

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | FK(PiutangHeader, CASCADE) | |
| `tanggal` | DateField | |
| `dari_akun` | FK(Akun, PROTECT) | Source CoA |
| `ke_akun` | FK(Akun, PROTECT) | Destination CoA |
| `jumlah` | DecimalField(19,4) | |
| `keterangan` | CharField(255, blank) | |
| `jurnal` | OneToOneField(JurnalHeader, CASCADE) | Auto-generated |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` | DateTimeField(auto_now_add) | |

---

### `PiutangWriteOff`

No equivalent in utang. Records bad-debt write-off.

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | OneToOneField(PiutangHeader, CASCADE) | One write-off per piutang |
| `tanggal` | DateField | |
| `jumlah_dihapus` | DecimalField(19,4) | Must equal sisa_piutang at time of write-off |
| `metode` | CharField choices: `langsung \| cadangan` | |
| `bad_debt_account` | FK(Akun, PROTECT) | Beban piutang tak tertagih |
| `allowance_account` | FK(Akun, PROTECT, null, blank) | Cadangan kerugian piutang — cadangan method only |
| `alasan` | TextField(blank) | |
| `jurnal` | FK(JurnalHeader, SET_NULL, null, blank) | Auto-generated |
| `created_by` | FK(User, SET_NULL, null, blank) | |
| `created_at` | DateTimeField(auto_now_add) | |

---

### `PiutangAttachment`

Mirrors `UtangAttachment`.

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | FK(PiutangHeader, CASCADE) | |
| `file` | FileField(`piutang/attachments/%Y/%m/`) | |
| `file_name` | CharField(255) | |
| `jenis_dokumen` | CharField choices: `invoice \| kontrak \| spk \| perjanjian \| berita_acara \| kuitansi \| lainnya` | |
| `uploaded_by` | FK(User, SET_NULL, null, blank) | |
| `uploaded_at` | DateTimeField(auto_now_add) | |

---

### `PiutangAuditLog`

Mirrors `UtangAuditLog`. FK to header uses SET_NULL (log survives header deletion).

| Field | Type | Notes |
|---|---|---|
| `piutang_header` | FK(PiutangHeader, SET_NULL, null, blank) | |
| `nomor_piutang` | CharField(100, blank) | Denormalized — survives deletion |
| `action` | CharField choices (see below) | |
| `user` | FK(User, SET_NULL, null, blank) | |
| `timestamp` | DateTimeField(auto_now_add, db_index) | |
| `before_json` | JSONField(default=dict) | |
| `after_json` | JSONField(default=dict) | |
| `notes` | CharField(512, blank) | |

Action choices: `CREATED | EDITED | SUBMIT_APPROVAL | APPROVED | REJECTED | PAYMENT | REVERSE_PAYMENT | WRITE_OFF | REKLASIFIKASI | CANCELLED`

---

## 3. Service Layer (`piutang_services.py`)

### `create_manual_piutang(data, user) → PiutangHeader`
- Create `PiutangHeader` with status=draft
- Create `PiutangDetail` rows from data
- Log `CREATED`

### `create_piutang_from_sales(sales_header, user) → PiutangHeader`
- Called by `confirm_sales()` when `SalesHeader.payment_type = 'credit'`
- `source_type = 'from_sales'`, `source_sales = sales_header`
- `jumlah_pokok` = sum of credit SalesItem totals
- `status = 'open'` (bypass approval)
- Create one `PiutangDetail` per SalesEntitasBisnis group
- Log `CREATED`

### `create_piutang_from_pendapatan(pendapatan_header, user) → PiutangHeader`
- Called by `confirm_pendapatan()` when `payment_type = 'credit'`
- `source_type = 'from_pendapatan'`, `source_pendapatan = pendapatan_header`
- `jumlah_pokok` = sum of all credit PendapatanItem totals
- `status = 'open'` (bypass approval)
- Log `CREATED`

### `create_piutang_payment(piutang, data, user) → PiutangPenerimaan`
Wrapped in `transaction.atomic()`:
1. Validate `jumlah_diterima ≤ piutang.sisa_piutang` — raise `ValueError` if exceeded
2. Create `PiutangPenerimaan`
3. Generate jurnal: `DR payment_account / CR coa_piutang_account`
4. Update `jumlah_terbayar` (re-aggregate from penerimaan set, not += to avoid race condition)
5. Recompute status: `partial` if sisa > 0, `paid` if sisa = 0
6. Log `PAYMENT`

### `compute_angsuran_schedule(piutang) → list[dict]`
Pure function. Returns `[{no, periode, pokok, bunga, total}, ...]`.
- `tanpa_bunga`: equal principal split
- `flat`: `bunga = jumlah_pokok × bunga_persen / 12` per period, constant
- `anuitas`: standard annuity formula, reducing balance interest

### `compute_bagian_lancar(piutang) → Decimal`
Returns portion of `sisa_piutang` due within 12 months. Used for reklasifikasi display and auto-suggest.

### `write_off_piutang(piutang, data, user) → PiutangWriteOff`
Wrapped in `transaction.atomic()`:
- `langsung`: `DR bad_debt_account / CR coa_piutang_account`
- `cadangan`: `DR allowance_account / CR coa_piutang_account`
- Create `PiutangWriteOff`, generate jurnal
- `status → written_off`, `is_locked = True`
- Log `WRITE_OFF`

### `reverse_piutang_payment(penerimaan, user)`
Wrapped in `transaction.atomic()`:
- Reverse the linked `JurnalHeader` (create counter-entry)
- Re-aggregate `jumlah_terbayar` on header
- Recompute status (paid → partial or open)
- Log `REVERSE_PAYMENT`

### `get_piutang_aging() → dict`
Groups `open | partial | overdue` piutang by age of `jatuh_tempo`:
`current | 1-30 | 31-60 | 61-90 | >90` days — per debitur and per EB.

### `get_piutang_dashboard_kpi() → dict`
Returns: total outstanding, total overdue, total collected this month, collection rate (collected / (collected + outstanding)).

---

## 4. URL Structure

```
/piutang/dashboard/
/piutang/                               list
/piutang/create/                        form buat baru (manual)
/piutang/<pk>/                          detail
/piutang/<pk>/edit/                     edit (draft only)
/piutang/<pk>/delete/                   delete (draft only)
/piutang/<pk>/terima/                   catat penerimaan
/piutang/<pk>/submit-approval/
/piutang/<pk>/approve/
/piutang/<pk>/reject/
/piutang/<pk>/penerimaan/<ppk>/cancel/  reverse payment
/piutang/<pk>/write-off/                hapus buku
/piutang/<pk>/reklasifikasi/            catat reklasifikasi
/piutang/<pk>/reklasifikasi/<rpk>/reverse/
/piutang/<pk>/attachments/upload/
/piutang/<pk>/attachments/<apk>/delete/

# Reports
/piutang/reports/aging/
/piutang/reports/subjek/               per debitur
/piutang/reports/akun/                 per akun piutang
/piutang/reports/jatuh-tempo/          upcoming due dates
/piutang/reports/write-off/            write-off history
```

---

## 5. Migration Plan

`apps/piutang/` stub already has `0001_initial.py` with placeholder models.

Required:
1. New migration replacing stub models with full schema
2. No data to preserve (stub is empty)

Foreign key imports needed in migrations:
- `entitas_bisnis.EntitasBisnis`
- `master_data.Akun`
- `accounts.User`
- `jurnal.JurnalHeader`
- `sales.SalesHeader` (added in Phase 2 of master plan)
- `pendapatan.PendapatanHeader` (added in Phase 3)

`source_sales` and `source_pendapatan` FKs can be added in separate migrations when those apps are ready — or all at once if building sequentially.

---

## 6. UI Notes

Mirror `utang` views/templates. Key differences:
- "Kreditor" label → "Debitur"
- "Pembayaran" → "Penerimaan"
- Add Write-Off page (no equivalent in utang)
- Dashboard KPI cards: Outstanding / Overdue / Collected this month / Collection rate
- Aging table on reports page
