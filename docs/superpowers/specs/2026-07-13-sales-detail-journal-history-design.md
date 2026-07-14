# Sales Detail Page: Journal History Section

Date: 2026-07-13

## Background

The `pendapatan` (revenue) module's detail page shows a "Riwayat Jurnal" (journal history) section listing every journal entry (`JurnalHeader`/`JurnalDetail`) created for that transaction, including tax-related journals. The `sales` module's detail page (`templates/sales/sales_detail.html`) has no equivalent — even though sales transactions already generate journals via `create_sales_automated_journals` (`apps/sales/services.py:139-220`), one `JurnalHeader` per entitas-bisnis group, plus separate tax journals via the `pajak` module. The user wants the sales detail page to show these journals the same way pendapatan does.

Neither module has a real FK from `JurnalHeader` back to its source transaction — both identify "their" journals by string-matching `JurnalHeader.uraian_transaksi`. Sales already uses this pattern elsewhere (`sales_delete` view, `reverse_sales_automated_journals` service): `uraian_transaksi__startswith=f'Penjualan {sales.transaction_id} —'`.

## Goal

Add a "Riwayat Jurnal" section to the sales detail page, mirroring pendapatan's, showing all journals (sales + tax) linked to that sales transaction.

## Non-goals

- No FK/schema changes — keep using the existing string-match pattern, consistent with the rest of the codebase.
- No changes to journal creation logic (`create_sales_automated_journals`) or to the pendapatan detail page's behavior.
- No new links to a dedicated "journal detail" page — pendapatan's version is fully inline (accordion), and this should match.

## Design

**View** (`apps/sales/views.py`, `sales_detail`, ~lines 450-497):
- Add a `journals` query: `JurnalHeader.objects.filter(uraian_transaksi__startswith=f'Penjualan {sales.transaction_id} —', is_penyesuaian=False).prefetch_related('details__akun').order_by('tanggal', 'id')`. Tag each with `jh.source_label = 'sales'`.
- Merge in tax journals: collect `si_ids` from the already-prefetched `eb_groups`' items, look up `PajakTransaksi.objects.filter(source_type='sales_item', source_id__in=si_ids, jurnal_header__isnull=False).values_list('jurnal_header_id', flat=True)`, fetch those `JurnalHeader`s, tag with `jh.source_label = 'pajak'`, merge and re-sort by `(tanggal, id)` — identical pattern to `pendapatan_detail`.
- Pass `journals` into the template context.

**Template** (`templates/sales/sales_detail.html`):
- Add `{% load humanize static %}` (currently only loads `humanize`) and `<link rel="stylesheet" href="{% static 'css/transaction-forms.css' %}">` in `extra_css`.
- Insert a "Riwayat Jurnal" `ni-card` section between the "Mutasi Inventory" card and the delete-modal include (~line 267-269), copying the accordion/table markup verbatim from `templates/pendapatan/detail.html:546-599` (adjusted only for the `journals` variable name, which is already the same).
- Empty state: same "Belum ada jurnal — jurnal dibuat otomatis saat konfirmasi." message.

**CSS**:
- Move the `.ni-jrn-*` rule block (`templates/pendapatan/detail.html:124-158`) into `static/css/transaction-forms.css` (already linked by both templates once this task is done), and delete it from pendapatan's inline `<style>` block. No visual change intended for pendapatan.

## Testing

- View test: create a sales transaction (confirmed, so `create_sales_automated_journals` has run), GET the detail page, assert the response's `journals` context contains the expected `JurnalHeader`(s) and that rendered HTML contains each journal's `nomor_transaksi`.
- View test: create a sales transaction with a tax line that produces a `PajakTransaksi` with a linked `jurnal_header`, assert that journal appears in `journals` with `source_label == 'pajak'` and the "Pajak" badge renders.
- Regression: existing `sales_detail` tests (if any) still pass; `pendapatan` detail page still renders identically after the CSS move (visual, verified manually — no automated visual regression tooling in this project).
