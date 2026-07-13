# Sales Detail Page: Journal History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This project is NOT a git repository.** Skip every `git commit` step below — there is nothing to commit to. Just check the box and move to the next step.
>
> **Working directory for test/shell commands:** `naveda_integra/` (where `setup.cfg` and `manage.py` live), inside `d:\DATA\Documents\Kerja\Naveda Integra Finance\NIF Website Dev`.

**Goal:** Show all journal entries (sales + tax) generated for a sales transaction on the sales detail page, mirroring the existing "Riwayat Jurnal" section already shipped on the pendapatan detail page.

**Architecture:** Neither `sales` nor `pendapatan` has a real FK from `JurnalHeader` to its source transaction — both identify journals via a `uraian_transaksi` string-match, a pattern sales already uses elsewhere (`sales_delete`, `reverse_sales_automated_journals`). This plan adds the same query + template pattern to `sales_detail`, and extracts the journal-accordion CSS (currently only in `pendapatan/detail.html`'s inline `<style>`) into the shared `transaction-forms.css` so both templates use one definition.

**Tech Stack:** Django (views, templates), `pytest-django`.

**Reference spec:** `docs/superpowers/specs/2026-07-13-sales-detail-journal-history-design.md`

---

## File Structure

- Modify: `naveda_integra/apps/sales/views.py` — `sales_detail` function (~lines 450-497), add journal query.
- Modify: `naveda_integra/apps/sales/tests.py` — new tests.
- Modify: `naveda_integra/templates/sales/sales_detail.html` — add `extra_css` link, insert "Riwayat Jurnal" section.
- Modify: `naveda_integra/templates/pendapatan/detail.html` — remove the now-shared `.ni-jrn-*` CSS block from its inline `<style>`.
- Modify: `naveda_integra/static/css/transaction-forms.css` — add the `.ni-jrn-*` CSS block.

---

### Task 1: Query journals (sales + tax) in `sales_detail`

**Files:**
- Modify: `naveda_integra/apps/sales/views.py:450-497`
- Modify: `naveda_integra/apps/sales/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `naveda_integra/apps/sales/tests.py` (new test class — uses `force_login`, not `self.client.login()`, to avoid the pre-existing unrelated django-axes issue in `SalesViewTests`; mirrors the `_eb_groups_payload` fixture pattern already used in that class):

```python
class SalesDetailJournalHistoryTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(kode='admin2', nama='Admin2')
        self.user = User.objects.create_user(email='jrn@test.com', password='pass1234', role=self.role)
        self.client = Client()
        self.client.force_login(self.user)

        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Cafe Jurnal', tipe_entitas=self.tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        self.akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='3', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi', tipe_item='RM', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan Tunai', module='sales', direction='outflow',
            default_offset_account=self.akun_persediaan,
        )
        FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )

    def _eb_groups_payload(self, quantity='5', selling_price='20000'):
        groups = [{
            'eb_selection': f'lv1:{self.eb.pk}',
            'payment_account_id': self.akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'quantity': quantity,
                'selling_price': selling_price,
                'offset_coa_account_id': self.akun_persediaan.pk,
                'revenue_account_id': self.akun_pendapatan.pk,
                'payment_account_id': self.akun_modal.pk,
            }],
        }]
        return json.dumps(groups)

    def test_detail_page_shows_created_journal(self):
        from apps.jurnal.models import JurnalHeader
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test jurnal di detail',
            'eb_groups_data': self._eb_groups_payload(),
        })
        header = SalesHeader.objects.first()
        journal = JurnalHeader.objects.get(
            uraian_transaksi__startswith=f'Penjualan {header.transaction_id} —',
        )
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(journal, resp.context['journals'])
        self.assertContains(resp, journal.nomor_transaksi)

    def test_detail_page_journal_shows_debit_credit_lines(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test debit kredit',
            'eb_groups_data': self._eb_groups_payload(),
        })
        header = SalesHeader.objects.first()
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertContains(resp, self.akun_pendapatan.nama)

    def test_detail_page_with_no_journals_shows_empty_state(self):
        header = SalesHeader.objects.create()
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertEqual(resp.context['journals'], [])
        self.assertContains(resp, 'Belum ada jurnal')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/sales/tests.py -k SalesDetailJournalHistory -v`
Expected: FAIL — `KeyError: 'journals'` (not in context yet) and/or the empty-state text not found (template doesn't render it yet).

- [ ] **Step 3: Implement the view logic**

In `naveda_integra/apps/sales/views.py`, change:

```python
@login_required
def sales_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """View sales transaction detail."""
    sales = get_object_or_404(SalesHeader, pk=pk)
    eb_groups = sales.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3', 'payment_account',
    ).prefetch_related(
        'items__item', 'items__sub_transaction_type',
        'items__offset_coa_account', 'items__revenue_account',
        'items__payment_account',
        'items__tax_account', 'items__tax_payment_account',
        'items__tax_lines__tax_account', 'items__tax_lines__tax_payment_account',
    ).all()

    # Build inventory mutations from per-batch FIFO allocations
    inventory_mutations = []
    allocations = (
        SalesItemFIFOAllocation.objects
        .filter(sales_item__sales_eb__sales_header=sales)
        .select_related(
            'inventory_record__item',
            'inventory_record__entitas_bisnis',
            'sales_item__sales_eb__entitas_bisnis',
            'sales_item__item',
        )
        .order_by('inventory_record__tanggal', 'inventory_record__inventory_number')
    )
    for alloc in allocations:
        inv_rec = alloc.inventory_record
        is_bulk_alloc = alloc.sales_item.item.tipe_item in ('RMB', 'FGB', 'ITMB')
        inventory_mutations.append({
            'inventory_number': inv_rec.inventory_number,
            'inventory_pk': inv_rec.pk,
            'item': str(inv_rec.item),
            'entitas_bisnis': alloc.sales_item.sales_eb.entitas_bisnis.nama,
            'quantity_sold': alloc.quantity_consumed,
            'cogs': alloc.cogs_amount,
            'is_bulk': is_bulk_alloc,
        })

    event_logs = sales.event_logs.select_related('actor').order_by('timestamp')

    return render(request, 'sales/sales_detail.html', {
        'sales': sales,
        'eb_groups': eb_groups,
        'inventory_mutations': inventory_mutations,
        'event_logs': event_logs,
    })
```

to:

```python
@login_required
def sales_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """View sales transaction detail."""
    sales = get_object_or_404(SalesHeader, pk=pk)
    eb_groups = sales.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3', 'payment_account',
    ).prefetch_related(
        'items__item', 'items__sub_transaction_type',
        'items__offset_coa_account', 'items__revenue_account',
        'items__payment_account',
        'items__tax_account', 'items__tax_payment_account',
        'items__tax_lines__tax_account', 'items__tax_lines__tax_payment_account',
    ).all()

    # Build inventory mutations from per-batch FIFO allocations
    inventory_mutations = []
    allocations = (
        SalesItemFIFOAllocation.objects
        .filter(sales_item__sales_eb__sales_header=sales)
        .select_related(
            'inventory_record__item',
            'inventory_record__entitas_bisnis',
            'sales_item__sales_eb__entitas_bisnis',
            'sales_item__item',
        )
        .order_by('inventory_record__tanggal', 'inventory_record__inventory_number')
    )
    for alloc in allocations:
        inv_rec = alloc.inventory_record
        is_bulk_alloc = alloc.sales_item.item.tipe_item in ('RMB', 'FGB', 'ITMB')
        inventory_mutations.append({
            'inventory_number': inv_rec.inventory_number,
            'inventory_pk': inv_rec.pk,
            'item': str(inv_rec.item),
            'entitas_bisnis': alloc.sales_item.sales_eb.entitas_bisnis.nama,
            'quantity_sold': alloc.quantity_consumed,
            'cogs': alloc.cogs_amount,
            'is_bulk': is_bulk_alloc,
        })

    event_logs = sales.event_logs.select_related('actor').order_by('timestamp')

    from apps.jurnal.models import JurnalHeader
    uraian_match = f'Penjualan {sales.transaction_id} —'
    journals = list(
        JurnalHeader.objects
        .filter(uraian_transaksi__startswith=uraian_match, is_penyesuaian=False)
        .prefetch_related('details__akun')
        .order_by('tanggal', 'id')
    )
    for jh in journals:
        jh.source_label = 'sales'

    from apps.pajak.models import PajakTransaksi
    si_ids = [si.pk for eg in eb_groups for si in eg.items.all()]
    pajak_jurnal_ids = []
    if si_ids:
        pajak_jurnal_ids = list(
            PajakTransaksi.objects
            .filter(source_type='sales_item', source_id__in=si_ids, jurnal_header__isnull=False)
            .values_list('jurnal_header_id', flat=True)
        )
    if pajak_jurnal_ids:
        pajak_journals = list(
            JurnalHeader.objects
            .filter(pk__in=pajak_jurnal_ids)
            .prefetch_related('details__akun')
        )
        for jh in pajak_journals:
            jh.source_label = 'pajak'
        journals = sorted(journals + pajak_journals, key=lambda j: (j.tanggal, j.id))

    return render(request, 'sales/sales_detail.html', {
        'sales': sales,
        'eb_groups': eb_groups,
        'inventory_mutations': inventory_mutations,
        'event_logs': event_logs,
        'journals': journals,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/sales/tests.py -k SalesDetailJournalHistory -v`
Expected: still FAIL on the two tests that check rendered HTML content (`test_detail_page_shows_created_journal`'s `assertContains`, `test_detail_page_journal_shows_debit_credit_lines`, `test_detail_page_with_no_journals_shows_empty_state`'s `assertContains`) — the view now provides `journals` in context, so context-only assertions (`self.assertIn(journal, resp.context['journals'])`, `self.assertEqual(resp.context['journals'], [])`) should PASS, but the template doesn't render the section yet (Task 2). Confirm this split: context assertions pass, HTML-content assertions fail.

- [ ] **Step 5: Mark task complete** (no git repo — skip commit; HTML assertions will pass after Task 2)

---

### Task 2: Add the "Riwayat Jurnal" section to the template, and extract shared CSS

**Files:**
- Modify: `naveda_integra/templates/sales/sales_detail.html` (top `{% load %}`/`extra_css`, and insert new section ~line 267-269)
- Modify: `naveda_integra/templates/pendapatan/detail.html` (remove `.ni-jrn-*` CSS block, ~lines 124-158)
- Modify: `naveda_integra/static/css/transaction-forms.css` (add the `.ni-jrn-*` CSS block)

- [ ] **Step 1: Move the `.ni-jrn-*` CSS block into the shared stylesheet**

In `naveda_integra/templates/pendapatan/detail.html`, remove this block from the inline `<style>` (currently around lines 124-158):

```css
/* ── Journal entry accordion ─────────────────────────────────────── */
.ni-jrn-entry {
  border: 1px solid var(--ni-border);
  border-radius: var(--ni-radius);
  margin-bottom: 8px;
  overflow: hidden;
}
.ni-jrn-entry:last-child { margin-bottom: 0; }
.ni-jrn-entry summary {
  list-style: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  background: var(--ni-bg);
  font-size: 0.8125rem;
  user-select: none;
}
.ni-jrn-entry summary::-webkit-details-marker { display: none; }
.ni-jrn-entry[open] summary { background: color-mix(in srgb, var(--ni-primary) 4%, var(--ni-bg)); }
.ni-jrn-entry__nomor { font-weight: 600; color: var(--ni-primary); min-width: 140px; font-size: 0.8rem; }
.ni-jrn-entry__date  { color: var(--ni-text-muted); white-space: nowrap; }
.ni-jrn-entry__uraian { flex: 1; color: var(--ni-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ni-jrn-entry__caret { margin-left: auto; color: var(--ni-text-muted); transition: transform 200ms ease; flex-shrink: 0; }
.ni-jrn-entry[open] .ni-jrn-entry__caret { transform: rotate(180deg); }
.ni-jrn-entry__body { padding: 0 14px 12px; }
.ni-jrn-table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; margin-top: 8px; }
.ni-jrn-table th { padding: 5px 8px; text-align: left; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ni-text-muted); border-bottom: 1px solid var(--ni-border); }
.ni-jrn-table td { padding: 6px 8px; border-bottom: 1px solid var(--ni-border); color: var(--ni-text); }
.ni-jrn-table tr:last-child td { border-bottom: none; }
.ni-jrn-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.ni-jrn-table .dr  { color: var(--ni-primary); }
.ni-jrn-table .cr  { color: var(--ni-text-muted); }
.ni-jrn-table tfoot td { font-weight: 600; border-top: 1px solid var(--ni-border); border-bottom: none; }
```

Append that exact same block to the end of `naveda_integra/static/css/transaction-forms.css` (add a `/* ── Journal entry accordion ─────────────────────────────────────── */` header comment as shown above, so it's self-documenting in its new shared location).

`pendapatan/detail.html` already has `<link rel="stylesheet" href="{% static 'css/transaction-forms.css' %}">` in its `extra_css` block (confirmed present), so nothing else changes there — the rendered page should look identical.

- [ ] **Step 2: Load `static` and link the shared CSS in `sales_detail.html`**

Change (line 1-3):

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Detail Sales {{ sales.transaction_id }}{% endblock %}
```

to:

```html
{% extends 'base.html' %}
{% load humanize static %}
{% block title %}Detail Sales {{ sales.transaction_id }}{% endblock %}
```

Then, right after the `{% block extra_css %}` line (currently line 5), add the stylesheet link:

```html
{% block extra_css %}
<link rel="stylesheet" href="{% static 'css/transaction-forms.css' %}">
<style>
```

(i.e. insert the `<link>` line between `{% block extra_css %}` and the existing `<style>` tag — don't remove the existing `<style>` block, it has unrelated mobile-responsive rules.)

- [ ] **Step 3: Insert the "Riwayat Jurnal" section**

Change (around lines 266-269):

```html
  </div>
</div>
{% endif %}

{% include 'components/delete_modal.html' %}
```

to:

```html
  </div>
</div>
{% endif %}

{# ── Riwayat Jurnal ────────────────────────────────────────────────────────── #}
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header">
    <div>
      <h2 class="ni-card__title">Riwayat Jurnal</h2>
      <p style="font-size:0.8rem;color:var(--ni-text-muted);margin:3px 0 0;">Semua entri jurnal yang dibuat untuk transaksi ini</p>
    </div>
    <span style="font-size:0.875rem;font-weight:600;color:var(--ni-text-muted);">{{ journals|length }} jurnal</span>
  </div>
  <div class="ni-card__body">
    {% if journals %}
    {% for jh in journals %}
    <details class="ni-jrn-entry" {% if forloop.first %}open{% endif %}>
      <summary>
        <i data-lucide="book-open" style="width:14px;height:14px;color:var(--ni-primary);flex-shrink:0;"></i>
        <span class="ni-jrn-entry__nomor">{{ jh.nomor_transaksi }}</span>
        {% if jh.source_label == 'pajak' %}<span style="font-size:0.7rem;padding:1px 7px;background:#fef3c7;color:#92400e;border-radius:999px;font-weight:600;white-space:nowrap;">Pajak</span>{% endif %}
        <span class="ni-jrn-entry__date">{{ jh.tanggal|date:"d M Y" }}</span>
        <span class="ni-jrn-entry__uraian">{{ jh.uraian_transaksi }}</span>
        <i data-lucide="chevron-down" class="ni-jrn-entry__caret" style="width:14px;height:14px;"></i>
      </summary>
      <div class="ni-jrn-entry__body">
        <p style="font-size:0.78rem;color:var(--ni-text-muted);margin:4px 0 8px;">{{ jh.uraian_transaksi }}</p>
        <table class="ni-jrn-table">
          <thead>
            <tr>
              <th>Kode Akun</th>
              <th>Nama Akun</th>
              <th class="num">Debit (Rp)</th>
              <th class="num">Kredit (Rp)</th>
            </tr>
          </thead>
          <tbody>
            {% for d in jh.details.all %}
            <tr>
              <td style="font-family:ui-monospace,monospace;font-size:0.78rem;">{{ d.akun.kode_akun }}</td>
              <td>{{ d.akun.nama }}</td>
              <td class="num dr">{% if d.debit %}{{ d.debit|floatformat:0|intcomma }}{% else %}&mdash;{% endif %}</td>
              <td class="num cr">{% if d.kredit %}{{ d.kredit|floatformat:0|intcomma }}{% else %}&mdash;{% endif %}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </details>
    {% endfor %}
    {% else %}
    <div style="text-align:center;padding:32px 0;color:var(--ni-text-muted);">
      <i data-lucide="book" style="width:32px;height:32px;opacity:0.3;margin-bottom:8px;"></i>
      <p style="font-size:0.875rem;margin:0;">Belum ada jurnal — jurnal dibuat otomatis saat konfirmasi.</p>
    </div>
    {% endif %}
  </div>
</div>

{% include 'components/delete_modal.html' %}
```

- [ ] **Step 4: Run the Task 1 tests again — now expected to fully pass**

Run: `pytest apps/sales/tests.py -k SalesDetailJournalHistory -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full sales test suite to check for regressions**

Run: `pytest apps/sales/tests.py -k "not SalesViewTests" -v`
Expected: PASS (no regressions; `SalesViewTests` is excluded due to a pre-existing, unrelated django-axes issue with `self.client.login()` confirmed in an earlier session — not something this task touches or should try to fix)

- [ ] **Step 6: Run the pendapatan test suite to confirm the CSS move didn't break anything**

Run: `pytest apps/pendapatan/tests.py -v`
Expected: PASS (no regressions — this is a pure CSS relocation, no Python/template logic in pendapatan changed)

- [ ] **Step 7: Mark task complete** (no git repo — skip commit)

---

### Task 3: Manual verification in the browser

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server** (from `naveda_integra/`): `python manage.py runserver`

- [ ] **Step 2: Open an existing (or new) confirmed sales transaction's detail page**

Confirm the new "Riwayat Jurnal" card appears after "Mutasi Inventory" and before "Riwayat Aktivitas", showing one accordion entry per journal, each expandable to show the debit/credit account lines, matching the visual style of the same section on a pendapatan detail page.

- [ ] **Step 3: Open a pendapatan detail page and confirm it still renders identically**

The journal accordion section should look exactly the same as before (this was a pure CSS relocation, not a visual change).

- [ ] **Step 4: Check the empty state**

Open a sales transaction that has no journals yet (e.g. one created directly via Django admin, or a draft/incomplete one if such a state exists) and confirm the "Belum ada jurnal" message renders correctly instead of an empty table.

- [ ] **Step 5: Mark task complete** (no git repo — skip commit)
