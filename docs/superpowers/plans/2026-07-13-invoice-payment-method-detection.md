# Invoice Payment Method Detection & Lunas Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **This project is NOT a git repository.** Skip every `git commit` step below — there is nothing to commit to. Just check the box and move to the next step.
>
> **Working directory for test/shell commands:** `naveda_integra/` (where `setup.cfg` and `manage.py` live), inside `d:\DATA\Documents\Kerja\Naveda Integra Finance\NIF Website Dev`.

**Goal:** Fix the always-`-` "Metode Pembayaran" field on Sales and Pendapatan invoices, detect a 3-way payment label (Kas / Kredit / Kas dan Kredit) per invoice from per-item accounts, show payment method per line item, and show a Lunas/Belum Lunas badge based on existing piutang data.

**Architecture:** Add one new boolean field `is_kas_setara` to `master_data.Akun` (set manually per account via the existing Django admin). Compute per-item and per-invoice payment labels and Lunas status directly inside the two invoice view functions (`sales_invoice`, `pendapatan_invoice`), following the existing inline-computation style already used there for tax totals. Surface the results in the two invoice templates. No changes to journal/piutang creation logic.

**Tech Stack:** Django (models, admin, views, templates), `pytest-django` (test runner, run via `pytest`, tests written as `django.test.TestCase`).

**Reference spec:** `docs/superpowers/specs/2026-07-13-invoice-payment-method-detection-design.md`

---

## File Structure

- Modify: `naveda_integra/apps/master_data/models.py` — add `is_kas_setara` field to `Akun`.
- Create: `naveda_integra/apps/master_data/migrations/0002_akun_is_kas_setara.py`.
- Modify: `naveda_integra/apps/master_data/admin.py` — expose `is_kas_setara` in `AkunAdmin`.
- Modify: `naveda_integra/apps/master_data/tests.py` — new tests for the field.
- Modify: `naveda_integra/apps/sales/views.py` — compute payment labels + Lunas status in `sales_invoice`.
- Modify: `naveda_integra/apps/sales/tests.py` — new tests for the invoice view.
- Modify: `naveda_integra/templates/sales/sales_invoice.html` — display changes.
- Modify: `naveda_integra/apps/pendapatan/views.py` — compute payment labels + Lunas status in `pendapatan_invoice`.
- Modify: `naveda_integra/apps/pendapatan/tests.py` — new tests for the invoice view.
- Modify: `naveda_integra/templates/pendapatan/invoice.html` — display changes.

---

### Task 1: Add `is_kas_setara` flag to `master_data.Akun`

**Files:**
- Modify: `naveda_integra/apps/master_data/models.py:190-191`
- Create: `naveda_integra/apps/master_data/migrations/0002_akun_is_kas_setara.py`
- Modify: `naveda_integra/apps/master_data/admin.py:107-111`
- Modify: `naveda_integra/apps/master_data/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `naveda_integra/apps/master_data/tests.py` (near the existing `AkunModelTests` class):

```python
class AkunIsKasSetaraTests(TestCase):
    def test_default_is_false(self):
        a = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang')
        self.assertFalse(a.is_kas_setara)

    def test_can_flag_as_kas(self):
        a = Akun.objects.create(kategori_id='aset', nama='Kas Tunai', is_kas_setara=True)
        self.assertTrue(a.is_kas_setara)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/master_data/tests.py -k AkunIsKasSetara -v`
Expected: FAIL — `TypeError: Akun() got unexpected keyword arguments: 'is_kas_setara'` (or `AttributeError` on `a.is_kas_setara`).

- [ ] **Step 3: Add the field to the model**

In `naveda_integra/apps/master_data/models.py`, change:

```python
    kode_akun = models.CharField(max_length=50, blank=True, default='', db_index=True)
```

to:

```python
    kode_akun = models.CharField(max_length=50, blank=True, default='', db_index=True)
    is_kas_setara = models.BooleanField(
        default=False,
        verbose_name='Kas/Setara Kas',
        help_text='Centang jika akun ini kas/bank (dibayar tunai). Biarkan kosong untuk akun piutang/kredit.',
    )
```

- [ ] **Step 4: Create the migration**

Create `naveda_integra/apps/master_data/migrations/0002_akun_is_kas_setara.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('master_data', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='akun',
            name='is_kas_setara',
            field=models.BooleanField(
                default=False,
                verbose_name='Kas/Setara Kas',
                help_text='Centang jika akun ini kas/bank (dibayar tunai). Biarkan kosong untuk akun piutang/kredit.',
            ),
        ),
    ]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest apps/master_data/tests.py -k AkunIsKasSetara -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Expose the flag in Django admin**

In `naveda_integra/apps/master_data/admin.py`, change:

```python
@admin.register(Akun)
class AkunAdmin(admin.ModelAdmin):
    list_display = ('id', 'kategori_id', 'kategori_akun', 'nama')
    list_filter = ('kategori_id',)
    search_fields = ('nama',)
```

to:

```python
@admin.register(Akun)
class AkunAdmin(admin.ModelAdmin):
    list_display = ('id', 'kategori_id', 'kategori_akun', 'nama', 'is_kas_setara')
    list_filter = ('kategori_id', 'is_kas_setara')
    list_editable = ('is_kas_setara',)
    search_fields = ('nama',)
```

- [ ] **Step 7: Run the full master_data test suite to check for regressions**

Run: `pytest apps/master_data/tests.py -v`
Expected: PASS (no regressions)

- [ ] **Step 8: Mark task complete** (no git repo — skip commit)

---

### Task 2: Compute payment labels + Lunas status in the Sales invoice view

**Files:**
- Modify: `naveda_integra/apps/sales/views.py` (the `sales_invoice` function, ~lines 502-608)
- Modify: `naveda_integra/apps/sales/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `naveda_integra/apps/sales/tests.py`:

```python
from apps.accounts.models import User


class SalesInvoicePaymentLabelTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='inv@test.com', password='pass', name='Invoice User')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', is_kas_setara=True)
        self.akun_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang', is_kas_setara=False)
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP')
        self.akun_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Beras', tipe_item='RM', coa_account=self.akun_kas,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan FnB', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )
        self.header = SalesHeader.objects.create(payment_type='cash')
        self.eb_group = SalesEntitasBisnis.objects.create(
            sales_header=self.header,
            entitas_bisnis=self.entitas,
        )

    def _make_item(self, payment_account):
        return SalesItem.objects.create(
            sales_eb=self.eb_group,
            item=self.item,
            sub_transaction_type=self.stt,
            quantity=Decimal('10'),
            selling_price=Decimal('50000'),
            offset_coa_account=self.akun_hpp,
            revenue_account=self.akun_pendapatan,
            payment_account=payment_account,
        )

    def test_all_cash_items_label_kas(self):
        self._make_item(self.akun_kas)
        self._make_item(self.akun_kas)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Kas')
        self.assertNotContains(resp, 'Kas dan Kredit')

    def test_mixed_items_label_kas_dan_kredit(self):
        self._make_item(self.akun_kas)
        self._make_item(self.akun_piutang)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Kas dan Kredit')

    def test_cash_header_shows_lunas(self):
        self._make_item(self.akun_kas)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')

    def test_credit_header_without_piutang_shows_belum_lunas(self):
        self.header.payment_type = 'credit'
        self.header.save()
        self._make_item(self.akun_piutang)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Belum Lunas')

    def test_credit_header_with_paid_piutang_shows_lunas(self):
        from apps.piutang.models import PiutangHeader
        self.header.payment_type = 'credit'
        self.header.save()
        self._make_item(self.akun_piutang)
        PiutangHeader.objects.create(
            nomor_piutang='PTG-TEST-001',
            source_type='from_sales',
            source_sales=self.header,
            jumlah_pokok=Decimal('500000'),
            jumlah_terbayar=Decimal('500000'),
            status='paid',
        )
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/sales/tests.py -k SalesInvoicePaymentLabel -v`
Expected: FAIL — assertions on 'Kas dan Kredit' / 'Belum Lunas' not found in response (the template doesn't render them yet).

- [ ] **Step 3: Implement the view logic**

In `naveda_integra/apps/sales/views.py`, inside `sales_invoice`, change the items loop and group-append block from:

```python
        items_data = []
        for si in eg.items.all():
            subtotal += si.total_sales or Decimal('0')
            si_pungut = Decimal('0')
            si_potong = Decimal('0')
            tax_lines_list = list(si.tax_lines.all())
            if tax_lines_list:
                for tl in tax_lines_list:
                    amt = _tax_amount(si, tl) or Decimal('0')
                    tl.amount = amt
                    tl.is_dipotong = SIFAT_PAJAK_MAP.get(tl.tax_type) == 'prepaid'
                    if tl.is_dipotong:
                        si_potong += amt
                    else:
                        si_pungut += amt
            elif si.tax:
                if SIFAT_PAJAK_MAP.get(si.tax_type) == 'prepaid':
                    si_potong += si.tax
                else:
                    si_pungut += si.tax
            pungut_total += si_pungut
            potong_total += si_potong
            items_data.append({
                'si': si,
                'tax_lines': tax_lines_list,
                'si_pungut': si_pungut,
                'si_potong': si_potong,
            })
        tax_total = pungut_total - potong_total
        group_total = subtotal + tax_total
        grand_total += group_total
        grand_tax += tax_total
        eb_groups_with_totals.append({
            'group': eg,
            'items_data': items_data,
            'subtotal': subtotal,
            'pungut_total': pungut_total,
            'potong_total': potong_total,
            'tax_total': tax_total,
            'group_total': group_total,
        })
```

to:

```python
        items_data = []
        for si in eg.items.all():
            subtotal += si.total_sales or Decimal('0')
            si_pungut = Decimal('0')
            si_potong = Decimal('0')
            tax_lines_list = list(si.tax_lines.all())
            if tax_lines_list:
                for tl in tax_lines_list:
                    amt = _tax_amount(si, tl) or Decimal('0')
                    tl.amount = amt
                    tl.is_dipotong = SIFAT_PAJAK_MAP.get(tl.tax_type) == 'prepaid'
                    if tl.is_dipotong:
                        si_potong += amt
                    else:
                        si_pungut += amt
            elif si.tax:
                if SIFAT_PAJAK_MAP.get(si.tax_type) == 'prepaid':
                    si_potong += si.tax
                else:
                    si_pungut += si.tax
            pungut_total += si_pungut
            potong_total += si_potong
            if si.payment_account_id is None:
                payment_label = '-'
            elif si.payment_account.is_kas_setara:
                payment_label = 'Kas'
            else:
                payment_label = 'Kredit'
            items_data.append({
                'si': si,
                'tax_lines': tax_lines_list,
                'si_pungut': si_pungut,
                'si_potong': si_potong,
                'payment_label': payment_label,
            })
        tax_total = pungut_total - potong_total
        group_total = subtotal + tax_total
        grand_total += group_total
        grand_tax += tax_total
        group_payment_labels = {d['payment_label'] for d in items_data if d['payment_label'] != '-'}
        if not group_payment_labels:
            group_payment_label = '-'
        elif group_payment_labels == {'Kas'}:
            group_payment_label = 'Kas'
        elif group_payment_labels == {'Kredit'}:
            group_payment_label = 'Kredit'
        else:
            group_payment_label = 'Kas dan Kredit'
        eb_groups_with_totals.append({
            'group': eg,
            'items_data': items_data,
            'subtotal': subtotal,
            'pungut_total': pungut_total,
            'potong_total': potong_total,
            'tax_total': tax_total,
            'group_total': group_total,
            'payment_label': group_payment_label,
        })
```

Then change the `return render(...)` call from:

```python
    return render(request, 'sales/sales_invoice.html', {
        'sales': sales,
        'eb_groups_data': eb_groups_with_totals,
        'company': company,
        'grand_total': grand_total,
        'grand_tax': grand_tax,
    })
```

to:

```python
    if sales.payment_type == 'cash':
        lunas_status = 'Lunas'
    else:
        piutang = sales.piutang_headers.order_by('-tanggal', '-id').first()
        lunas_status = 'Lunas' if piutang and piutang.status == 'paid' else 'Belum Lunas'

    return render(request, 'sales/sales_invoice.html', {
        'sales': sales,
        'eb_groups_data': eb_groups_with_totals,
        'company': company,
        'grand_total': grand_total,
        'grand_tax': grand_tax,
        'lunas_status': lunas_status,
    })
```

- [ ] **Step 4: Run tests — still expected to fail (template not updated yet)**

Run: `pytest apps/sales/tests.py -k SalesInvoicePaymentLabel -v`
Expected: FAIL — view now computes the right data, but the template (Task 3) doesn't render `gdata.payment_label` or `lunas_status` yet, so the assertions still won't find the text. This confirms the view change alone doesn't fix it (proceed to Task 3 before re-running).

- [ ] **Step 5: Mark task complete** (no git repo — skip commit; template changes land in Task 3, then re-run these tests)

---

### Task 3: Update the Sales invoice template

**Files:**
- Modify: `naveda_integra/templates/sales/sales_invoice.html:297-361`

- [ ] **Step 1: Replace the Metode Pembayaran block**

Change (around line 297-300):

```html
    <div class="inv-meta__block">
      <div class="inv-meta__label">Metode Pembayaran</div>
      <div class="inv-meta__value">{{ eg.payment_account|default:'—' }}</div>
    </div>
```

to:

```html
    <div class="inv-meta__block">
      <div class="inv-meta__label">Metode Pembayaran</div>
      <div class="inv-meta__value">
        {{ gdata.payment_label }}
        <span style="display:inline-block;margin-left:8px;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600;{% if lunas_status == 'Lunas' %}background:#dcfce7;color:#166534;{% else %}background:#fee2e2;color:#991b1b;{% endif %}">{{ lunas_status }}</span>
      </div>
    </div>
```

- [ ] **Step 2: Add the "Pembayaran" column header**

Change (around line 310-317):

```html
        <tr>
          <th>#</th>
          <th>Item</th>
          <th>Tipe</th>
          <th class="r">Qty</th>
          <th class="r">Harga</th>
          <th class="r">Total</th>
        </tr>
```

to:

```html
        <tr>
          <th>#</th>
          <th>Item</th>
          <th>Tipe</th>
          <th>Pembayaran</th>
          <th class="r">Qty</th>
          <th class="r">Harga</th>
          <th class="r">Total</th>
        </tr>
```

- [ ] **Step 3: Add the per-item payment cell**

Change (around line 322-335):

```html
        <tr>
          <td>{{ forloop.counter }}</td>
          <td>{{ si.item }}</td>
          <td style="color:#64748b;font-size:0.75rem;">{{ si.sub_transaction_type.nama }}</td>
          <td class="r">
```

to:

```html
        <tr>
          <td>{{ forloop.counter }}</td>
          <td>{{ si.item }}</td>
          <td style="color:#64748b;font-size:0.75rem;">{{ si.sub_transaction_type.nama }}</td>
          <td style="font-size:0.75rem;">{{ idata.payment_label }}</td>
          <td class="r">
```

- [ ] **Step 4: Fix colspans for the now-7-column table**

The table now has 7 columns (#, Item, Tipe, Pembayaran, Qty, Harga, Total) instead of 6. Update the two tax-row blocks and the empty-state row:

Change (around line 336-347):

```html
        {% if idata.tax_lines %}
        {% for tl in idata.tax_lines %}
        <tr class="tax-row">
          <td></td>
          <td colspan="4" style="padding-left:16px;">
```

to:

```html
        {% if idata.tax_lines %}
        {% for tl in idata.tax_lines %}
        <tr class="tax-row">
          <td></td>
          <td colspan="5" style="padding-left:16px;">
```

Change (around line 348-357):

```html
        {% elif si.tax %}
        <tr class="tax-row">
          <td></td>
          <td colspan="4" style="padding-left:16px;">
```

to:

```html
        {% elif si.tax %}
        <tr class="tax-row">
          <td></td>
          <td colspan="5" style="padding-left:16px;">
```

Change (around line 359-360):

```html
        {% empty %}
        <tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:16px 8px;">Tidak ada item.</td></tr>
```

to:

```html
        {% empty %}
        <tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:16px 8px;">Tidak ada item.</td></tr>
```

- [ ] **Step 5: Run the Task 2 tests again — now expected to pass**

Run: `pytest apps/sales/tests.py -k SalesInvoicePaymentLabel -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full sales test suite to check for regressions**

Run: `pytest apps/sales/tests.py -v`
Expected: PASS (no regressions)

- [ ] **Step 7: Mark task complete** (no git repo — skip commit)

---

### Task 4: Compute payment labels + Lunas status in the Pendapatan invoice view

**Files:**
- Modify: `naveda_integra/apps/pendapatan/views.py` (the `pendapatan_invoice` function, ~lines 578-670)
- Modify: `naveda_integra/apps/pendapatan/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `naveda_integra/apps/pendapatan/tests.py` (add `Client` and `reverse` imports at top alongside the existing `TestCase` import, and a `User` import):

```python
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
```

Then add:

```python
class PendapatanInvoicePaymentLabelTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='pend-inv@test.com', password='pass', name='Invoice User')
        self.client.force_login(self.user)
        self.f = make_fixtures()
        self.f['coa_kas'].is_kas_setara = True
        self.f['coa_kas'].save()
        # coa_piutang keeps the default is_kas_setara=False

    def test_cash_header_shows_lunas(self):
        header = make_header(self.f, payment_type='cash')
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')

    def test_credit_header_without_piutang_shows_belum_lunas(self):
        header = make_header(self.f, payment_type='credit')
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Belum Lunas')

    def test_credit_header_with_paid_piutang_shows_lunas(self):
        from apps.piutang.models import PiutangHeader
        header = make_header(self.f, payment_type='credit')
        PiutangHeader.objects.create(
            nomor_piutang='PTG-TEST-002',
            source_type='from_pendapatan',
            source_pendapatan=header,
            jumlah_pokok=Decimal('5000000'),
            jumlah_terbayar=Decimal('5000000'),
            status='paid',
        )
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/pendapatan/tests.py -k PendapatanInvoicePaymentLabel -v`
Expected: FAIL — 'Belum Lunas' / distinguishing text not present yet.

- [ ] **Step 3: Implement the view logic**

In `naveda_integra/apps/pendapatan/views.py`, inside `pendapatan_invoice`:

First, add `'entitas_groups__items__payment_account'` to the `prefetch_related(...)` call so the new lookup doesn't cause N+1 queries. Change:

```python
        .prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__entitas_bisnis_lv2',
            'entitas_groups__entitas_bisnis_lv3',
            'entitas_groups__payment_account',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__tax_lines',
        ),
```

to:

```python
        .prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__entitas_bisnis_lv2',
            'entitas_groups__entitas_bisnis_lv3',
            'entitas_groups__payment_account',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__tax_lines',
            'entitas_groups__items__payment_account',
        ),
```

Then change the items loop and group-append block from:

```python
        items_data = []
        for kp in eg.items.all():
            kp_pungut = Decimal('0')
            kp_potong = Decimal('0')
            for tl in kp.tax_lines.all():
                amt = _tax_amount(kp, tl) or Decimal('0')
                tl.amount = amt
                tl.is_dipotong = SIFAT_PAJAK_MAP.get(tl.tax_type) == 'prepaid'
                if tl.is_dipotong:
                    kp_potong += amt
                else:
                    kp_pungut += amt
            subtotal += kp.nilai_kontrak or Decimal('0')
            pungut_total += kp_pungut
            potong_total += kp_potong
            items_data.append({'kp': kp, 'kp_pungut': kp_pungut, 'kp_potong': kp_potong})
        group_total = subtotal + pungut_total - potong_total
        grand_total += group_total
        eb_groups_data.append({
            'group': eg,
            'items_data': items_data,
            'subtotal': subtotal,
            'pungut_total': pungut_total,
            'potong_total': potong_total,
            'group_total': group_total,
        })
```

to:

```python
        items_data = []
        for kp in eg.items.all():
            kp_pungut = Decimal('0')
            kp_potong = Decimal('0')
            for tl in kp.tax_lines.all():
                amt = _tax_amount(kp, tl) or Decimal('0')
                tl.amount = amt
                tl.is_dipotong = SIFAT_PAJAK_MAP.get(tl.tax_type) == 'prepaid'
                if tl.is_dipotong:
                    kp_potong += amt
                else:
                    kp_pungut += amt
            subtotal += kp.nilai_kontrak or Decimal('0')
            pungut_total += kp_pungut
            potong_total += kp_potong
            if kp.payment_account_id is None:
                payment_label = '-'
            elif kp.payment_account.is_kas_setara:
                payment_label = 'Kas'
            else:
                payment_label = 'Kredit'
            items_data.append({
                'kp': kp,
                'kp_pungut': kp_pungut,
                'kp_potong': kp_potong,
                'payment_label': payment_label,
            })
        group_total = subtotal + pungut_total - potong_total
        grand_total += group_total
        group_payment_labels = {d['payment_label'] for d in items_data if d['payment_label'] != '-'}
        if not group_payment_labels:
            group_payment_label = '-'
        elif group_payment_labels == {'Kas'}:
            group_payment_label = 'Kas'
        elif group_payment_labels == {'Kredit'}:
            group_payment_label = 'Kredit'
        else:
            group_payment_label = 'Kas dan Kredit'
        eb_groups_data.append({
            'group': eg,
            'items_data': items_data,
            'subtotal': subtotal,
            'pungut_total': pungut_total,
            'potong_total': potong_total,
            'group_total': group_total,
            'payment_label': group_payment_label,
        })
```

Then change the `return render(...)` call from:

```python
    return render(request, 'pendapatan/invoice.html', {
        'header': header,
        'company': company,
        'eb_groups_data': eb_groups_data,
        'grand_total': grand_total,
    })
```

to:

```python
    if header.payment_type == 'cash':
        lunas_status = 'Lunas'
    else:
        piutang = header.piutang_headers.order_by('-tanggal', '-id').first()
        lunas_status = 'Lunas' if piutang and piutang.status == 'paid' else 'Belum Lunas'

    return render(request, 'pendapatan/invoice.html', {
        'header': header,
        'company': company,
        'eb_groups_data': eb_groups_data,
        'grand_total': grand_total,
        'lunas_status': lunas_status,
    })
```

- [ ] **Step 4: Run tests — still expected to fail (template not updated yet)**

Run: `pytest apps/pendapatan/tests.py -k PendapatanInvoicePaymentLabel -v`
Expected: FAIL — view computes the right data, template (Task 5) doesn't render it yet.

- [ ] **Step 5: Mark task complete** (no git repo — skip commit; template changes land in Task 5, then re-run these tests)

---

### Task 5: Update the Pendapatan invoice template

**Files:**
- Modify: `naveda_integra/templates/pendapatan/invoice.html:309-357`

- [ ] **Step 1: Replace the Metode Pembayaran block**

Change (around line 309-312):

```html
    <div class="inv-meta__block">
      <div class="inv-meta__label">Metode Pembayaran</div>
      <div class="inv-meta__value">{{ header.get_payment_type_display }}</div>
    </div>
```

to:

```html
    <div class="inv-meta__block">
      <div class="inv-meta__label">Metode Pembayaran</div>
      <div class="inv-meta__value">
        {{ gdata.payment_label }}
        <span style="display:inline-block;margin-left:8px;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:600;{% if lunas_status == 'Lunas' %}background:#dcfce7;color:#166534;{% else %}background:#fee2e2;color:#991b1b;{% endif %}">{{ lunas_status }}</span>
      </div>
    </div>
```

- [ ] **Step 2: Add the "Pembayaran" column header next to Kategori**

Change (around line 322-327):

```html
        <tr>
          <th style="width:28px;">#</th>
          <th>Deskripsi Item</th>
          <th>Kategori</th>
          <th class="r">Nilai (Rp)</th>
        </tr>
```

to:

```html
        <tr>
          <th style="width:28px;">#</th>
          <th>Deskripsi Item</th>
          <th>Kategori</th>
          <th>Pembayaran</th>
          <th class="r">Nilai (Rp)</th>
        </tr>
```

- [ ] **Step 3: Add the per-item payment cell**

Change (around line 332-341):

```html
        <tr>
          <td>{{ forloop.counter }}</td>
          <td>
            {{ kp.deskripsi_item }}
            {% if kp.sub_transaction_type %}
            <div style="font-size:0.72rem;color:#94a3b8;margin-top:2px;">{{ kp.sub_transaction_type.nama }}</div>
            {% endif %}
          </td>
          <td style="color:#64748b;font-size:0.78rem;">{{ kp.get_kategori_display }}</td>
          <td class="r"><strong>{{ kp.nilai_kontrak|floatformat:0|intcomma }}</strong></td>
        </tr>
```

to:

```html
        <tr>
          <td>{{ forloop.counter }}</td>
          <td>
            {{ kp.deskripsi_item }}
            {% if kp.sub_transaction_type %}
            <div style="font-size:0.72rem;color:#94a3b8;margin-top:2px;">{{ kp.sub_transaction_type.nama }}</div>
            {% endif %}
          </td>
          <td style="color:#64748b;font-size:0.78rem;">{{ kp.get_kategori_display }}</td>
          <td style="font-size:0.78rem;">{{ idata.payment_label }}</td>
          <td class="r"><strong>{{ kp.nilai_kontrak|floatformat:0|intcomma }}</strong></td>
        </tr>
```

- [ ] **Step 4: Fix colspans for the now-5-column table**

Change (around line 343-352):

```html
        {% for tl in kp.tax_lines.all %}
        <tr class="tax-row">
          <td></td>
          <td colspan="2" style="padding-left:16px;">
```

to:

```html
        {% for tl in kp.tax_lines.all %}
        <tr class="tax-row">
          <td></td>
          <td colspan="3" style="padding-left:16px;">
```

Change (around line 355-356):

```html
        {% empty %}
        <tr><td colspan="4" style="text-align:center;color:#94a3b8;padding:16px 8px;">Tidak ada item.</td></tr>
```

to:

```html
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:16px 8px;">Tidak ada item.</td></tr>
```

- [ ] **Step 5: Run the Task 4 tests again — now expected to pass**

Run: `pytest apps/pendapatan/tests.py -k PendapatanInvoicePaymentLabel -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full pendapatan test suite to check for regressions**

Run: `pytest apps/pendapatan/tests.py -v`
Expected: PASS (no regressions)

- [ ] **Step 7: Mark task complete** (no git repo — skip commit)

---

### Task 6: Manual verification in the browser

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server**

Run: `python manage.py runserver` (from `naveda_integra/`)

- [ ] **Step 2: In Django admin, flag at least one Kas account and one Piutang account**

Visit `/admin/master_data/akun/`, tick `is_kas_setara` for a Kas/Bank account, leave it unticked for a Piutang account. Save.

- [ ] **Step 3: Open a real Sales invoice with mixed-account items**

Create or find a sales transaction with two items using different accounts (one flagged Kas, one not), then visit `/sales/<pk>/invoice/`. Confirm:
- Header "Metode Pembayaran" shows "Kas dan Kredit" with a Lunas/Belum Lunas badge next to it.
- The item table has a "Pembayaran" column between "Tipe" and "Qty" showing "Kas"/"Kredit" per row.
- Table layout isn't broken (tax sub-rows still align under the right columns).

- [ ] **Step 4: Repeat for a Pendapatan invoice**

Visit `/pendapatan/<pk>/invoice/` for a transaction with mixed-account items. Confirm the same three things (label, badge, new "Pembayaran" column next to "Kategori").

- [ ] **Step 5: Confirm the original bug is fixed**

Open any older sales invoice that previously showed "-" for Metode Pembayaran. Confirm it now shows "Kas", "Kredit", or "Kas dan Kredit" instead of "-".

- [ ] **Step 6: Mark task complete** (no git repo — skip commit)
