# Invoice Payment Method Detection & Lunas Status

Date: 2026-07-13

## Background

The "Metode Pembayaran" field on the Sales invoice (`templates/sales/sales_invoice.html:299`) always renders `-`. Root cause: it reads `eg.payment_account`, a legacy `SalesEntitasBisnis.payment_account` FK that has been hard-coded to `None` at creation time since the app moved to per-item payment accounts (`apps/sales/views.py:927`, comment `# now per-item on SalesItem`). The real per-item field, `SalesItem.payment_account` (`apps/sales/models.py:200-207`), is populated correctly and required at data entry (`views.py:795-796`), but is never surfaced on the invoice. The sibling `pendapatan` app has the identical legacy pattern (`PendapatanEntitasBisnis.payment_account`, only ever set from the first item) and the same gap in its invoice template.

Separately, sales/pendapatan items can each use a different payment account (cash register, different bank account, etc.), and the business wants the invoice to reflect this instead of a single (broken) value, plus show whether a credit sale has been settled.

## Goals

1. Fix the always-`-` display bug.
2. Detect and display, per invoice, one of three payment-method states: **Kas**, **Kredit**, **Kas dan Kredit**.
3. Show payment method per line item (new column next to "Kategori" in the item table).
4. Show a **Lunas** / **Belum Lunas** badge reflecting whether the transaction is settled.
5. Apply consistently to both `sales` and `pendapatan` invoices.

## Non-goals

- No change to accounting/journal logic, piutang (receivable) creation, or how much is posted to AR. `SalesHeader.payment_type` (cash/credit, header-level) remains the sole driver of whether a `PiutangHeader` is created and for what amount.
- No per-item cash/credit override field — classification is derived from the account's new flag (see below), not entered separately per item.
- No reconciliation logic if the derived Kas/Kredit label disagrees with `payment_type`/actual piutang state — this is treated as a useful surfaced signal, not an error to auto-correct.

## Data model change

Add `is_kas_setara` (BooleanField, default `False`) to `master_data.Akun`. Set manually per account via the existing Akun CRUD form/admin (e.g. "Kas Tunai", "Bank BCA" → `True`; "Piutang Dagang" → `False`). One Django migration; no data backfill beyond the default.

## Business logic

**Per-item label** (`SalesItem`, and `pendapatan`'s `KewajibabPelaksanaan`):
- `payment_account.is_kas_setara == True` → `"Kas"`
- `payment_account.is_kas_setara == False` → `"Kredit"`
- `payment_account is None` → `"-"` (unexpected in practice; field is required at entry)

**Per-invoice label** (aggregated across all items in the `SalesEntitasBisnis` group / `sales`/`header` scope shown on one invoice):
- All items `"Kas"` → `"Kas"`
- All items `"Kredit"` → `"Kredit"`
- Mixed → `"Kas dan Kredit"`

**Lunas / Belum Lunas badge** (header-level, independent of the label above):
- `SalesHeader.payment_type == 'cash'` → `"Lunas"`
- `SalesHeader.payment_type == 'credit'` → look up linked `PiutangHeader` (`source_sales=sales_header`):
  - `status == 'paid'` → `"Lunas"`
  - any other status (`open`/`partial`/`overdue`/etc.) → `"Belum Lunas"`

Same logic mirrored for `pendapatan` using its equivalent header/piutang link.

## Template changes

- `templates/sales/sales_invoice.html`:
  - Replace the `eg.payment_account|default:'—'` line (~line 299) with the new per-invoice label.
  - Add a "Pembayaran" column next to "Kategori" in the item table (~lines 320-358), showing the per-item label.
  - Add the Lunas/Belum Lunas badge next to the Metode Pembayaran line.
- `templates/pendapatan/invoice.html`: same three changes, mirrored (currently shows `header.get_payment_type_display`, ~line 311; item loop ~lines 330-353).

## Testing

- Unit test for the label helper: all-Kas, all-Kredit, mixed → correct 3-way output.
- Unit test for Lunas logic: cash header → Lunas; credit header with `PiutangHeader.status='paid'` → Lunas; credit header with `status` in `open`/`partial`/`overdue` → Belum Lunas; credit header with no linked `PiutangHeader` (edge case, shouldn't normally happen) → Belum Lunas.
- Manual verification: render a sales invoice with items on different accounts (one `is_kas_setara=True`, one `False`) and confirm "Kas dan Kredit" + correct per-item column + correct badge.
- Regression: existing single-payment-method invoices (all-cash, all-credit) still render correctly, no `-` regression.
