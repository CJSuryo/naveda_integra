# Sales payment_type — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `payment_type` (cash|credit) to `SalesHeader` and wire it to `create_piutang_from_sales()` on confirm so credit sales auto-generate a `PiutangHeader`.

**Architecture:** Single field addition on `SalesHeader` + one service call on confirm path. Default=cash means zero data migration risk.

**Tech Stack:** Django migrations, existing sales/piutang service layer.

**Spec:** `docs/superpowers/specs/2026-06-07-pendapatan-design.md` (Cross-Cutting Changes section)

**Prerequisite:** Phase 1 (Piutang) complete.

---

## File Map

| Action | File |
|---|---|
| Modify | `apps/sales/models.py` |
| Create | `apps/sales/migrations/0007_salesheader_payment_type.py` (via makemigrations) |
| Modify | `apps/sales/services.py` |
| Modify | `apps/piutang/services.py` |
| Modify | `apps/sales/tests.py` |

---

## Task 1: Add payment_type field to SalesHeader

**Files:**
- Modify: `apps/sales/models.py`

- [ ] **Step 1: Add field to SalesHeader**

In `apps/sales/models.py`, inside `SalesHeader`, add after `is_locked`:

```python
payment_type = models.CharField(
    max_length=10,
    choices=[('cash', 'Cash'), ('credit', 'Kredit')],
    default='cash',
    verbose_name='Tipe Pembayaran',
)
```

- [ ] **Step 2: Run makemigrations**

```bash
python manage.py makemigrations sales --name salesheader_payment_type
```

Expected: `Migrations for 'sales': apps/sales/migrations/0007_salesheader_payment_type.py`

- [ ] **Step 3: Run migrate**

```bash
python manage.py migrate sales
```

Expected: `Applying sales.0007_salesheader_payment_type... OK`

- [ ] **Step 4: Verify existing sales unaffected**

```bash
python manage.py test apps.sales -v 2
```

Expected: all existing sales tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sales/models.py apps/sales/migrations/0007_salesheader_payment_type.py
git commit -m "feat(sales): add payment_type field (cash|credit, default=cash)"
```

---

## Task 2: Implement create_piutang_from_sales

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/sales/tests.py`

- [ ] **Step 1: Write failing test**

Add to `apps/sales/tests.py` (at the bottom, new test class):

```python
from apps.piutang.models import PiutangHeader


class CreditSalesCreatesPiutangTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
        from apps.master_data.models import Akun
        from apps.purchase.models import ItemMasterPurchase, SubTransactionType

        tipe = TipeEntitas.objects.create(nama='Pelanggan')
        self.eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
        self.coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang', kode_akun='1.2.1')
        self.coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        self.coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        self.item = ItemMasterPurchase.objects.create(item_id='FG-001', nama='Produk A', tipe_item='FG')
        self.stt = SubTransactionType.objects.create(
            nama='Kredit', module='sales', direction='outflow',
            default_offset_account=self.coa_revenue,
        )

    def _make_credit_sales_header(self):
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        header = SalesHeader.objects.create(payment_type='credit')
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
            payment_account=self.coa_piutang,
        )
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('500000'),
            offset_coa_account=self.coa_kas, revenue_account=self.coa_revenue,
            payment_account=self.coa_piutang,
        )
        return header

    def test_creates_piutang_header(self):
        from apps.piutang.services import create_piutang_from_sales
        header = self._make_credit_sales_header()
        piutang = create_piutang_from_sales(header)
        self.assertIsNotNone(piutang.pk)
        self.assertEqual(piutang.source_type, 'from_sales')
        self.assertEqual(piutang.source_sales, header)
        self.assertEqual(piutang.status, 'open')

    def test_jumlah_pokok_equals_total_credit_items(self):
        from apps.piutang.services import create_piutang_from_sales
        header = self._make_credit_sales_header()
        piutang = create_piutang_from_sales(header)
        self.assertEqual(piutang.jumlah_pokok, Decimal('500000'))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.sales.tests.CreditSalesCreatesPiutangTests -v 2
```

Expected: `NotImplementedError` from the stub.

- [ ] **Step 3: Implement create_piutang_from_sales in piutang/services.py**

Replace the stub at the bottom of `apps/piutang/services.py`:

```python
def create_piutang_from_sales(sales_header, user=None) -> PiutangHeader:
    from decimal import Decimal
    from apps.sales.models import SalesItem

    total = Decimal('0')
    details = []
    for eb_group in sales_header.entitas_groups.select_related('entitas_bisnis').all():
        for item in eb_group.items.select_related('revenue_account').all():
            total += item.total_sales
            details.append({
                'deskripsi': str(item.item),
                'jumlah': item.total_sales,
                'revenue_account': item.revenue_account,
            })

    if total <= 0:
        raise ValueError('Total credit sales harus lebih besar dari 0.')

    coa_piutang = (
        sales_header.entitas_groups.first().payment_account
        if sales_header.entitas_groups.exists()
        else None
    )
    if not coa_piutang:
        raise ValueError('Payment account (akun piutang) diperlukan pada SalesEntitasBisnis.')

    eb = sales_header.entitas_groups.first().entitas_bisnis if sales_header.entitas_groups.exists() else None

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=sales_header.tanggal,
            entitas_bisnis=eb,
            debitur=str(eb) if eb else '',
            deskripsi=f'Piutang dari Sales {sales_header.transaction_id}',
            source_type='from_sales',
            source_sales=sales_header,
            jumlah_pokok=total,
            status='open',
            coa_piutang_account=coa_piutang,
            created_by=user,
        )
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d['deskripsi'],
                jumlah=d['jumlah'],
                revenue_account=d.get('revenue_account'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang
```

- [ ] **Step 4: Run test**

```bash
python manage.py test apps.sales.tests.CreditSalesCreatesPiutangTests -v 2
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/sales/tests.py
git commit -m "feat(piutang): implement create_piutang_from_sales"
```

---

## Task 3: Wire to sales confirm path

**Files:**
- Modify: `apps/sales/services.py`

- [ ] **Step 1: Find confirm entry point in sales/services.py**

```bash
grep -n "def create_sales_automated_journals\|def confirm_sales\|FIFO_PROCESSED\|JOURNAL_CREATED" apps/sales/services.py | head -20
```

The sales confirm flow calls `create_sales_automated_journals`. Find where journals are created and add the piutang call after.

- [ ] **Step 2: Add piutang call after journal creation**

In `apps/sales/services.py`, find the function that triggers on sales confirm (the one that calls `create_sales_automated_journals` or equivalent). After the journal creation block, add:

```python
# Auto-create piutang for credit sales
if sales_header.payment_type == 'credit':
    from apps.piutang.services import create_piutang_from_sales
    create_piutang_from_sales(sales_header, user=user)
```

> **Note:** Read `apps/sales/services.py` to find the exact confirm function name and insertion point before making this edit. The function likely contains `SalesEventLog.objects.create(event_type='JOURNAL_CREATED', ...)`. Insert the piutang call after journal creation but still inside the `transaction.atomic()` block.

- [ ] **Step 3: Run all sales tests**

```bash
python manage.py test apps.sales -v 2
```

Expected: all PASS. No regression.

- [ ] **Step 4: Run all piutang tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/sales/services.py
git commit -m "feat(sales): auto-create piutang when confirming credit sale"
```

---

## Task 4: Add payment_type to sales form

**Files:**
- Modify: `apps/sales/forms.py`

- [ ] **Step 1: Add payment_type to SalesHeaderForm**

In `apps/sales/forms.py`, find `SalesHeaderForm`. Add `'payment_type'` to the `fields` list and add a widget:

```python
'payment_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_payment_type'}),
```

- [ ] **Step 2: Verify form renders**

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/sales/create/` — confirm `payment_type` field appears.

- [ ] **Step 3: Commit**

```bash
git add apps/sales/forms.py
git commit -m "feat(sales): add payment_type field to SalesHeaderForm"
```
