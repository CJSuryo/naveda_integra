# CoA "Kas/Setara Kas" Toggle for Aset Level 2 Accounts

Date: 2026-07-13

## Background

`master_data.Akun` has an `is_kas_setara` boolean flag (added in the invoice payment-method feature) that classifies an account as cash/bank (True) vs. receivable/credit (False). Currently the only way to set it is via Django admin (`/admin/master_data/akun/`). The user wants to set it from the Chart of Accounts (CoA) menu instead, where they already manage accounts day-to-day.

The CoA UI has two tiers below each category (Aset/Kewajiban/Ekuitas/Pendapatan/Beban): **Level 1** (`AsetLv1`, e.g. "Aset Lancar") and **Level 2** (`AsetLv2`, e.g. "Kas Tunai", kode `1.1.1`). Level 2 is the leaf that syncs to an `Akun` row via a `post_save` signal. The user wants the toggle available when adding/editing a Level 2 Aset account specifically (not Kewajiban/Ekuitas/Pendapatan/Beban — cash/bank accounts only ever live under Aset).

The real interactive edit/add UI is an AJAX modal in `templates/master_data/chart_of_accounts.html` (`#coaModalAddLv2`, `#coaModalEditLv2`), not the separate `master_data/aset/lv2_form.html` template (which is unreachable dead code in the current click-through flow — the modal always submits via `fetch()`/AJAX to the same `aset_lv2_create`/`aset_lv2_update` views).

## Goal

Let a user toggle `is_kas_setara` for an Aset Level 2 account directly from the CoA "Add" and "Edit" modals, without going through Django admin.

## Non-goals

- No changes to Kewajiban/Ekuitas/Pendapatan/Beban Level 2 modals.
- No changes to the invoice payment-label feature itself (already shipped).
- No new CoA hierarchy level — the existing Level 1/Level 2 structure is unchanged.
- Not fixing the unrelated pre-existing `get_lv2_url()`/`NoReverseMatch` dead-code issue noticed during investigation.

## Design

**Modal markup** (`chart_of_accounts.html`):
- Add a checkbox `<input type="checkbox" name="is_kas_setara" id="coaAddLv2IsKasSetara">` to `#coaModalAddLv2`, labeled "Kas/Setara Kas", rendered only when the modal is opened for the Aset category (the Add/Edit Lv2 modals are shared across all 5 categories, so the checkbox's wrapper `<div>` is shown/hidden by JS based on which category is being edited).
- Same addition to `#coaModalEditLv2`, plus prefill logic.

**View changes** (`apps/master_data/views.py`):
- `aset_lv2_create`: after `obj.save()` (which triggers the signal that creates the `Akun` row), read `is_kas_setara` from `request.POST` (checkbox presence) and update the newly-synced `Akun` row: `Akun.objects.filter(kategori_id='aset', kategori_akun=obj.pk).update(is_kas_setara=request.POST.get('is_kas_setara') == 'on')`.
- `aset_lv2_update`: same read-and-update, after the existing save/renumber logic.
- Other categories' create/update views (Kewajiban/Ekuitas/Pendapatan/Beban) are untouched — they simply never read this POST key.

**Prefill on edit** (`chart_of_accounts` view):
- Build a dict mapping `AsetLv2.pk -> is_kas_setara` from `Akun.objects.filter(kategori_id='aset').values_list('kategori_akun', 'is_kas_setara')`, and attach it to each Aset category context so the template can pass the current value into `niCoa.openEditLv2(...)`.

**JS** (`chart_of_accounts.html` inline script):
- `niCoa.openEditLv2(url, kode, nama, catIdx, lv1Idx, isKasSetara)` gains a 6th parameter; sets the checkbox's `checked` state from it, and shows/hides the checkbox's wrapper based on whether `catIdx` corresponds to the Aset category.
- `niCoa.openAddLv2(url, categoryName, catIdx, lv1Idx)` shows/hides the same checkbox wrapper in the Add modal based on `categoryName === 'Aset'` (unchecked by default).

## Testing

- View-level tests: creating an Aset Lv2 with `is_kas_setara=on` in POST results in the synced `Akun` row having `is_kas_setara=True`; omitting it (or category ≠ aset) leaves it `False`.
- Update test: toggling an existing Aset Lv2's `is_kas_setara` via POST updates the existing `Akun` row without creating a duplicate.
- Regression: Kewajiban/Ekuitas/Pendapatan/Beban Lv2 create/update still work unaffected (no `is_kas_setara` handling touches them).
- Manual: open CoA, add a new Aset Level 2 account with the checkbox ticked, confirm it shows as `is_kas_setara=True` in Django admin; edit it back off, confirm it updates.
