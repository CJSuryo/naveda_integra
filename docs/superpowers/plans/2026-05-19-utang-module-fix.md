# Utang Module Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the Utang (Accounts Payable) module to Purchase so that utang records are automatically created, reversed, and reported in sync with purchase transactions.

**Architecture:** Purchase journals are created by `purchase/services.py` and owned there. Utang module only creates *payment* journals — it reads purchase data to build UtangHeader/UtangDetail records, then links back to PurchaseHeader for any journal lookups (Option B: no direct FK to JurnalHeader). Race conditions in payment are fixed with `select_for_update()`. All destructive operations write an audit snapshot to `UtangTerhapus` first.

**Tech Stack:** Django 4.x, Python 3.11+, SQLite (dev) / PostgreSQL (prod), Django test client for view tests.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `apps/utang/migrations/0002_utang_jatuh_tempo_locked.py` | Add `tanggal_jatuh_tempo` + `is_locked` to UtangHeader |
| Create | `apps/purchase/migrations/0005_subtransactiontype_payment_term_days.py` | Add `payment_term_days` to SubTransactionType |
| Modify | `apps/utang/models.py` | New fields + `is_overdue` / `days_overdue` properties |
| Modify | `apps/purchase/models.py` | Add `payment_term_days` to SubTransactionType |
| Modify | `apps/utang/services.py` | Full rewrite of 4 functions, 1 fix, 2 new functions, 4 reporting functions |
| Modify | `apps/purchase/views.py` | Wire create_utang_for_purchase at 2 sites, reverse at 4 sites |
| Modify | `apps/utang/forms.py` | Filter entitas_bisnis, utang_detail, coa_account querysets |
| Modify | `apps/utang/views.py` | Guards on update/delete/pay, new payment_delete view, 4 reporting views |
| Modify | `apps/utang/urls.py` | 5 new URL patterns |
| Modify | `apps/utang/tests.py` | Updated setUp + 8 new test cases |
| Create | `templates/utang/payment_delete.html` | Payment cancellation confirm page |
| Create | `templates/utang/report_subjek.html` | Utang per supplier report |
| Create | `templates/utang/report_akun.html` | Utang per COA report |
| Create | `templates/utang/report_aging.html` | Aging buckets report |
| Create | `templates/utang/report_jatuh_tempo.html` | Upcoming due dates report |

---

## Task 1: Migrations

**Files:**
- Create: `apps/utang/migrations/0002_utang_jatuh_tempo_locked.py`
- Create: `apps/purchase/migrations/0005_subtransactiontype_payment_term_days.py`

- [ ] **Step 1: Create utang migration 0002**

```python
# apps/utang/migrations/0002_utang_jatuh_tempo_locked.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utang', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='utangheader',
            name='tanggal_jatuh_tempo',
            field=models.DateField(
                blank=True, db_index=True, null=True,
                verbose_name='Tanggal Jatuh Tempo',
            ),
        ),
        migrations.AddField(
            model_name='utangheader',
            name='is_locked',
            field=models.BooleanField(default=False, verbose_name='Terkunci'),
        ),
    ]
```

- [ ] **Step 2: Create purchase migration 0005**

```python
# apps/purchase/migrations/0005_subtransactiontype_payment_term_days.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase', '0004_subtransactiontype_default_inventory_account_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subtransactiontype',
            name='payment_term_days',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name='Payment Term (hari)',
                help_text='Otomatis isi tanggal jatuh tempo utang. Kosongkan jika tidak ada.',
            ),
        ),
    ]
```

- [ ] **Step 3: Apply migrations and verify**

Run:
```
python manage.py migrate
```
Expected: `Applying utang.0002_utang_jatuh_tempo_locked... OK` and `Applying purchase.0005_subtransactiontype_payment_term_days... OK`

- [ ] **Step 4: Commit**

```bash
git add apps/utang/migrations/0002_utang_jatuh_tempo_locked.py apps/purchase/migrations/0005_subtransactiontype_payment_term_days.py
git commit -m "feat(utang): add tanggal_jatuh_tempo, is_locked, payment_term_days migrations"
```

---

## Task 2: Model Field Changes

**Files:**
- Modify: `apps/utang/models.py:9-98`
- Modify: `apps/purchase/models.py:213-300`

- [ ] **Step 1: Add fields and properties to `UtangHeader` in `apps/utang/models.py`**

Add `tanggal_jatuh_tempo` and `is_locked` fields inside `UtangHeader`, after the `status` field (line ~46). Add `is_overdue` and `days_overdue` properties after `entitas_display`:

```python
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open',
        verbose_name='Status',
    )
    tanggal_jatuh_tempo = models.DateField(
        null=True, blank=True, db_index=True,
        verbose_name='Tanggal Jatuh Tempo',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

After `entitas_display`, add:

```python
    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone
        if not self.tanggal_jatuh_tempo or self.status == 'paid':
            return False
        return timezone.now().date() > self.tanggal_jatuh_tempo

    @property
    def days_overdue(self) -> int:
        from django.utils import timezone
        if not self.tanggal_jatuh_tempo or self.status == 'paid':
            return 0
        return max(0, (timezone.now().date() - self.tanggal_jatuh_tempo).days)
```

- [ ] **Step 2: Add `payment_term_days` to `SubTransactionType` in `apps/purchase/models.py`**

After `default_tax_type` field (~line 292), before `class Meta`:

```python
    payment_term_days = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name='Payment Term (hari)',
        help_text='Otomatis isi tanggal jatuh tempo utang. Kosongkan jika tidak ada.',
    )
```

- [ ] **Step 3: Verify Django can load models**

Run:
```
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

```bash
git add apps/utang/models.py apps/purchase/models.py
git commit -m "feat(utang): add tanggal_jatuh_tempo, is_locked to UtangHeader; payment_term_days to SubTransactionType"
```

---

## Task 3: Services — `_next_utang_journal_number` + `create_utang_for_purchase` rewrite

**Files:**
- Modify: `apps/utang/services.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Write failing tests**

Replace the content of `apps/utang/tests.py` with:

```python
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import (
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem,
    ItemMasterPurchase, SubTransactionType,
)
from apps.purchase.services import create_automated_journals
from .models import UtangHeader, UtangDetail, UtangPembayaran, UtangTerhapus
from .services import (
    create_manual_utang,
    create_utang_for_purchase, create_utang_payment,
    reverse_utang_for_purchase, reverse_utang_header, reverse_utang_payment,
)


def make_fixtures():
    """Return a dict of common test fixtures."""
    tipe = TipeEntitas.objects.create(nama='Distributor')
    eb = EntitasBisnis.objects.create(
        nama='PT Demo', tipe_entitas=tipe, relasi='pemasok',
    )
    coa_utang = Akun.objects.create(
        kategori_id='kewajiban', nama='Utang Dagang', kode_akun='2.1.1',
    )
    coa_cash = Akun.objects.create(
        kategori_id='aset', nama='Kas', kode_akun='1.1.1',
    )
    sub_type = SubTransactionType.objects.create(
        nama='Kredit', module='purchase', direction='inflow',
        default_offset_account=coa_utang,
    )
    item = ItemMasterPurchase.objects.create(
        item_id='RM-0001', nama='Bahan', tipe_item='RM',
    )
    purchase = PurchaseHeader.objects.create(
        transaction_id='PUR-INV-0001', tanggal=date(2026, 4, 28), deskripsi='Test',
    )
    purchase_group = PurchaseEntitasBisnis.objects.create(
        purchase_header=purchase, entitas_bisnis=eb,
    )
    purchase_item = PurchaseItem.objects.create(
        purchase_eb=purchase_group,
        item=item,
        sub_transaction_type=sub_type,
        coa_account=coa_cash,
        offset_coa_account=coa_utang,
        quantity=Decimal('10'),
        unit_price=Decimal('10000'),
    )
    return {
        'tipe': tipe, 'eb': eb, 'coa_utang': coa_utang, 'coa_cash': coa_cash,
        'sub_type': sub_type, 'item': item, 'purchase': purchase,
        'purchase_group': purchase_group, 'purchase_item': purchase_item,
    }


class CreateUtangForPurchaseTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_utang_header_for_kewajiban_item(self):
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        utang = headers[0]
        self.assertEqual(utang.total_amount, Decimal('100000'))
        self.assertEqual(utang.status, 'open')
        self.assertEqual(utang.details.count(), 1)
        self.assertEqual(utang.entitas_bisnis, self.f['eb'])

    def test_skips_non_kewajiban_items(self):
        # Change offset to aset — should produce no utang
        self.f['purchase_item'].offset_coa_account = self.f['coa_cash']
        self.f['purchase_item'].save()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 0)
        self.assertEqual(UtangHeader.objects.count(), 0)

    def test_payment_term_days_sets_jatuh_tempo(self):
        self.f['sub_type'].payment_term_days = 30
        self.f['sub_type'].save()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        expected = date(2026, 4, 28) + timedelta(days=30)
        self.assertEqual(headers[0].tanggal_jatuh_tempo, expected)

    def test_no_payment_term_uses_param(self):
        jatuh_tempo = date(2026, 6, 1)
        headers = create_utang_for_purchase(
            self.f['purchase'], tanggal_jatuh_tempo=jatuh_tempo,
        )
        self.assertEqual(headers[0].tanggal_jatuh_tempo, jatuh_tempo)

    def test_multiple_items_same_coa_grouped_into_one_header(self):
        item2 = ItemMasterPurchase.objects.create(
            item_id='RM-0002', nama='Bahan2', tipe_item='RM',
        )
        PurchaseItem.objects.create(
            purchase_eb=self.f['purchase_group'],
            item=item2,
            sub_transaction_type=self.f['sub_type'],
            coa_account=self.f['coa_cash'],
            offset_coa_account=self.f['coa_utang'],
            quantity=Decimal('5'),
            unit_price=Decimal('10000'),
        )
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].details.count(), 2)
        self.assertEqual(headers[0].total_amount, Decimal('150000'))
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```
python manage.py test apps.utang.tests.CreateUtangForPurchaseTests -v 2
```
Expected: Some tests pass (existing logic), `test_payment_term_days_sets_jatuh_tempo` and `test_no_payment_term_uses_param` FAIL because `tanggal_jatuh_tempo` field doesn't exist on model yet — or field exists but service doesn't set it.

- [ ] **Step 3: Rewrite `create_utang_for_purchase` in `apps/utang/services.py`**

Replace the existing `create_utang_for_purchase` function (lines 35–76) with:

```python
def create_utang_for_purchase(purchase_header, tanggal_jatuh_tempo=None):
    """
    Build UtangHeader records from a PurchaseHeader.
    Called after create_automated_journals() — journals already exist,
    this function only creates the utang recap and does NOT create new journals.
    Returns list[UtangHeader].
    """
    from datetime import timedelta

    utang_headers = []
    with transaction.atomic():
        for eb_group in (
            purchase_header.entitas_groups
            .select_related('entitas_bisnis')
            .prefetch_related(
                'items__offset_coa_account',
                'items__coa_account',
                'items__item',
                'items__sub_transaction_type',
            )
            .all()
        ):
            utang_items = [
                item for item in eb_group.items.all()
                if item.offset_coa_account
                and item.offset_coa_account.kategori_id == 'kewajiban'
            ]
            if not utang_items:
                continue

            groups: dict[int, list] = {}
            for item in utang_items:
                groups.setdefault(item.offset_coa_account_id, []).append(item)

            for coa_id, items in groups.items():
                total_amount = sum(item.total_value for item in items)
                stt = items[0].sub_transaction_type
                jatuh_tempo = None
                if stt and stt.payment_term_days:
                    jatuh_tempo = purchase_header.tanggal + timedelta(
                        days=stt.payment_term_days
                    )
                elif tanggal_jatuh_tempo:
                    jatuh_tempo = tanggal_jatuh_tempo

                header = UtangHeader.objects.create(
                    purchase_header=purchase_header,
                    tanggal=purchase_header.tanggal,
                    tanggal_jatuh_tempo=jatuh_tempo,
                    entitas_bisnis=eb_group.entitas_bisnis,
                    deskripsi=f'Utang dari {purchase_header.transaction_id}',
                    total_amount=total_amount,
                    status='open',
                )
                UtangDetail.objects.bulk_create([
                    UtangDetail(
                        utang_header=header,
                        purchase_item=item,
                        coa_utang_account_id=coa_id,
                        description=str(item.item),
                        amount=item.total_value,
                    )
                    for item in items
                ])
                utang_headers.append(header)
    return utang_headers
```

- [ ] **Step 4: Fix `_next_utang_journal_number` in `apps/utang/services.py`**

Replace the existing `_next_utang_journal_number` function (lines 161–171) with:

```python
def _next_utang_journal_number() -> str:
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-UTG-')
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'TRX-UTG-{seq:04d}'
```

- [ ] **Step 5: Run tests and confirm they pass**

Run:
```
python manage.py test apps.utang.tests.CreateUtangForPurchaseTests -v 2
```
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/utang/services.py apps/utang/tests.py
git commit -m "feat(utang): rewrite create_utang_for_purchase with payment_term_days support; fix journal numbering"
```

---

## Task 4: Services — `reverse_utang_header` + `reverse_utang_for_purchase`

**Files:**
- Modify: `apps/utang/services.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Add failing tests to `apps/utang/tests.py`**

Append this class after `CreateUtangForPurchaseTests`:

```python
class ReverseUtangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_reverse_utang_header_writes_utang_terhapus(self):
        headers = create_utang_for_purchase(self.f['purchase'])
        utang = headers[0]
        reverse_utang_header(utang, user=None)
        self.assertEqual(UtangTerhapus.objects.count(), 1)
        record = UtangTerhapus.objects.first()
        self.assertIn('total_amount', record.snapshot)
        self.assertEqual(record.nomor_utang, utang.nomor_utang)

    def test_reverse_utang_header_deletes_payment_journals_not_purchase_journals(self):
        from apps.jurnal.models import JurnalHeader
        create_automated_journals(self.f['purchase'])
        journal_count_before = JurnalHeader.objects.count()
        headers = create_utang_for_purchase(self.f['purchase'])
        utang = headers[0]
        # Create a payment with its own journal
        payment = create_utang_payment(
            utang,
            utang_detail=utang.details.first(),
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('10000'),
            keterangan='Test',
        )
        self.assertIsNotNone(payment.jurnal_header)
        payment_journal_id = payment.jurnal_header_id
        reverse_utang_header(utang, user=None)
        # Payment journal deleted
        self.assertFalse(JurnalHeader.objects.filter(pk=payment_journal_id).exists())
        # Purchase journal untouched
        self.assertEqual(JurnalHeader.objects.count(), journal_count_before)

    def test_reverse_utang_for_purchase_clears_all_utang(self):
        create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(UtangHeader.objects.count(), 1)
        reverse_utang_for_purchase(self.f['purchase'])
        self.assertEqual(UtangHeader.objects.count(), 0)
        self.assertEqual(UtangTerhapus.objects.count(), 1)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```
python manage.py test apps.utang.tests.ReverseUtangTests -v 2
```
Expected: `test_reverse_utang_header_writes_utang_terhapus` FAILS (UtangTerhapus never written); other two may pass partially.

- [ ] **Step 3: Add `UtangTerhapus` to imports and rewrite `reverse_utang_header` in `apps/utang/services.py`**

Update the import at line 9:
```python
from .models import UtangHeader, UtangDetail, UtangPembayaran, UtangTerhapus
```

Replace the `reverse_utang_header` function (lines 102–107) with:

```python
def reverse_utang_header(utang_header: UtangHeader, user=None):
    """Delete utang and write audit trail to UtangTerhapus.
    Deletes only payment journals owned by this module.
    Does not touch purchase journals.
    """
    UtangTerhapus.objects.create(
        nomor_utang=utang_header.nomor_utang,
        uraian=utang_header.deskripsi,
        entitas_bisnis_nama=(
            str(utang_header.entitas_bisnis) if utang_header.entitas_bisnis else ''
        ),
        tanggal=utang_header.tanggal,
        deleted_by=user,
        snapshot={
            'total_amount': str(utang_header.total_amount),
            'status': utang_header.status,
            'tanggal_jatuh_tempo': (
                str(utang_header.tanggal_jatuh_tempo)
                if utang_header.tanggal_jatuh_tempo else None
            ),
            'purchase_header_id': utang_header.purchase_header_id,
            'details': [
                {
                    'coa': str(d.coa_utang_account),
                    'amount': str(d.amount),
                    'description': d.description,
                }
                for d in utang_header.details.select_related('coa_utang_account').all()
            ],
            'pembayaran': [
                {
                    'tanggal': str(p.tanggal),
                    'jumlah': str(p.jumlah),
                    'keterangan': p.keterangan,
                }
                for p in utang_header.pembayaran.all()
            ],
        },
    )
    for payment in utang_header.pembayaran.select_related('jurnal_header').all():
        if payment.jurnal_header_id:
            log_jurnal_terhapus(payment.jurnal_header, 'utang', None)
            payment.jurnal_header.delete()
    utang_header.delete()
```

- [ ] **Step 4: Run tests and confirm they pass**

Run:
```
python manage.py test apps.utang.tests.ReverseUtangTests -v 2
```
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/utang/services.py apps/utang/tests.py
git commit -m "feat(utang): reverse_utang_header writes UtangTerhapus audit trail; preserves purchase journals"
```

---

## Task 5: Services — `create_utang_payment` race condition fix + `reverse_utang_payment`

**Files:**
- Modify: `apps/utang/services.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Add failing tests for `reverse_utang_payment`**

Append this class to `apps/utang/tests.py`:

```python
class UtangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]
        self.detail = self.utang.details.first()

    def test_payment_creates_journal_and_updates_status(self):
        payment = create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('50000'),
            keterangan='Bayar parsial',
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'partial')
        self.assertIsNotNone(payment.jurnal_header)

    def test_overpayment_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_utang_payment(
                self.utang,
                utang_detail=self.detail,
                tanggal=date(2026, 4, 28),
                coa_account=self.f['coa_cash'],
                jumlah=Decimal('200000'),
                keterangan='Overpay',
            )

    def test_full_payment_sets_paid_status(self):
        create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('100000'),
            keterangan='Lunas',
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'paid')

    def test_reverse_utang_payment_deletes_journal_and_recalculates_status(self):
        from apps.jurnal.models import JurnalHeader
        payment = create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('50000'),
            keterangan='Bayar',
        )
        payment_journal_id = payment.jurnal_header_id
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'partial')

        reverse_utang_payment(payment)

        self.assertFalse(JurnalHeader.objects.filter(pk=payment_journal_id).exists())
        self.assertFalse(
            self.utang.pembayaran.filter(pk=payment.pk).exists()
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'open')
```

- [ ] **Step 2: Run tests to confirm `reverse_utang_payment` fails (function doesn't exist)**

Run:
```
python manage.py test apps.utang.tests.UtangPaymentTests -v 2
```
Expected: `ImportError` or `AttributeError` on `reverse_utang_payment` import.

- [ ] **Step 3: Fix `create_utang_payment` and add `reverse_utang_payment` in `apps/utang/services.py`**

Replace `create_utang_payment` (lines 79–99) with:

```python
def create_utang_payment(
    utang_header: UtangHeader, utang_detail, tanggal, coa_account, jumlah, keterangan
):
    if jumlah <= 0:
        raise ValueError('Jumlah pembayaran harus lebih besar dari 0.')

    with transaction.atomic():
        locked = UtangHeader.objects.select_for_update().get(pk=utang_header.pk)
        outstanding = locked.outstanding_amount
        if jumlah > outstanding:
            raise ValueError('Jumlah pembayaran tidak boleh melebihi sisa utang.')

        payment = UtangPembayaran.objects.create(
            utang_header=locked,
            utang_detail=utang_detail,
            tanggal=tanggal,
            coa_account=coa_account,
            jumlah=jumlah,
            keterangan=keterangan,
        )
        journal = _create_utang_payment_journal(payment)
        payment.jurnal_header = journal
        payment.save(update_fields=['jurnal_header'])
        _update_utang_status(locked)
        return payment
```

Add `reverse_utang_payment` after `reverse_utang_for_purchase` (after line 112):

```python
def reverse_utang_payment(payment: UtangPembayaran, user=None) -> None:
    """Cancel a single utang payment: delete its journal and recalculate header status."""
    utang_header = payment.utang_header
    with transaction.atomic():
        if payment.jurnal_header_id:
            log_jurnal_terhapus(payment.jurnal_header, 'utang', None)
            payment.jurnal_header.delete()
        payment.delete()
        _update_utang_status(utang_header)
```

- [ ] **Step 4: Update import in `apps/utang/tests.py`** — add `reverse_utang_payment` to the import line:

```python
from .services import (
    create_manual_utang,
    create_utang_for_purchase, create_utang_payment,
    reverse_utang_for_purchase, reverse_utang_header, reverse_utang_payment,
)
```

- [ ] **Step 5: Run tests and confirm they pass**

Run:
```
python manage.py test apps.utang.tests.UtangPaymentTests -v 2
```
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add apps/utang/services.py apps/utang/tests.py
git commit -m "feat(utang): fix create_utang_payment race condition with select_for_update; add reverse_utang_payment"
```

---

## Task 6: Services — 4 Reporting Functions

**Files:**
- Modify: `apps/utang/services.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Add failing tests**

Append to `apps/utang/tests.py`:

```python
class UtangReportingTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]

    def test_get_utang_per_subjek_returns_open_utang(self):
        from .services import get_utang_per_subjek
        result = list(get_utang_per_subjek())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['entitas_bisnis__nama'], 'PT Demo')
        self.assertEqual(result[0]['jumlah_invoice'], 1)

    def test_get_utang_per_group_akun_returns_kewajiban_sum(self):
        from .services import get_utang_per_group_akun
        result = list(get_utang_per_group_akun())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['total'], Decimal('100000'))

    def test_get_utang_aging_buckets_current(self):
        from .services import get_utang_aging
        # Set jatuh_tempo in the future (not overdue)
        self.utang.tanggal_jatuh_tempo = date(2099, 1, 1)
        self.utang.save()
        buckets = get_utang_aging()
        self.assertEqual(len(buckets['current']), 1)
        self.assertEqual(len(buckets['due_1_30']), 0)

    def test_get_utang_jatuh_tempo_returns_upcoming(self):
        from .services import get_utang_jatuh_tempo
        from django.utils import timezone
        # Due tomorrow
        tomorrow = timezone.now().date() + timedelta(days=1)
        self.utang.tanggal_jatuh_tempo = tomorrow
        self.utang.save()
        result = list(get_utang_jatuh_tempo(hari_ke_depan=7))
        self.assertEqual(len(result), 1)

    def test_get_utang_jatuh_tempo_excludes_far_future(self):
        from .services import get_utang_jatuh_tempo
        self.utang.tanggal_jatuh_tempo = date(2099, 1, 1)
        self.utang.save()
        result = list(get_utang_jatuh_tempo(hari_ke_depan=7))
        self.assertEqual(len(result), 0)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```
python manage.py test apps.utang.tests.UtangReportingTests -v 2
```
Expected: `ImportError` — functions not defined yet.

- [ ] **Step 3: Add 4 reporting functions and update imports in `apps/utang/services.py`**

At the top of `apps/utang/services.py`, change:
```python
from django.db.models import Sum
```
to:
```python
from django.db.models import Count, Sum
from django.utils import timezone
```

Add these functions at the end of `apps/utang/services.py`:

```python
def get_utang_per_subjek():
    """Group open/partial utang by supplier. Returns queryset."""
    return (
        UtangHeader.objects
        .filter(status__in=['open', 'partial'])
        .values('entitas_bisnis__id', 'entitas_bisnis__nama')
        .annotate(
            total_utang=Sum('total_amount'),
            total_bayar=Sum('pembayaran__jumlah'),
            jumlah_invoice=Count('id'),
        )
        .order_by('-total_utang')
    )


def get_utang_per_group_akun():
    """Group open/partial utang by COA account. Returns queryset."""
    return (
        UtangDetail.objects
        .filter(utang_header__status__in=['open', 'partial'])
        .values(
            'coa_utang_account__kode_akun',
            'coa_utang_account__nama',
        )
        .annotate(total=Sum('amount'))
        .order_by('coa_utang_account__kode_akun')
    )


def get_utang_aging():
    """Bucket open/partial utang with jatuh_tempo by days overdue."""
    today = timezone.now().date()
    qs = (
        UtangHeader.objects
        .filter(status__in=['open', 'partial'], tanggal_jatuh_tempo__isnull=False)
        .select_related('entitas_bisnis', 'purchase_header')
        .annotate(total_bayar=Sum('pembayaran__jumlah'))
    )
    buckets = {'current': [], 'due_1_30': [], 'due_31_60': [], 'due_60_plus': []}
    for u in qs:
        delta = (today - u.tanggal_jatuh_tempo).days
        outstanding = u.total_amount - (u.total_bayar or Decimal('0'))
        entry = {'utang': u, 'outstanding': outstanding, 'hari': delta}
        if delta <= 0:
            buckets['current'].append(entry)
        elif delta <= 30:
            buckets['due_1_30'].append(entry)
        elif delta <= 60:
            buckets['due_31_60'].append(entry)
        else:
            buckets['due_60_plus'].append(entry)
    return buckets


def get_utang_jatuh_tempo(hari_ke_depan: int = 7):
    """Return open/partial utang due within hari_ke_depan days. Returns queryset."""
    from datetime import timedelta
    batas = timezone.now().date() + timedelta(days=hari_ke_depan)
    return (
        UtangHeader.objects
        .filter(
            status__in=['open', 'partial'],
            tanggal_jatuh_tempo__isnull=False,
            tanggal_jatuh_tempo__lte=batas,
        )
        .select_related('entitas_bisnis')
        .order_by('tanggal_jatuh_tempo')
    )
```

- [ ] **Step 4: Run all utang tests**

Run:
```
python manage.py test apps.utang -v 2
```
Expected: All tests PASS (zero failures)

- [ ] **Step 5: Commit**

```bash
git add apps/utang/services.py apps/utang/tests.py
git commit -m "feat(utang): add get_utang_per_subjek, get_utang_per_group_akun, get_utang_aging, get_utang_jatuh_tempo"
```

---

## Task 7: Wire Purchase Views

**Files:**
- Modify: `apps/purchase/views.py`

This task has 6 wiring points. There is no TDD here because the purchase view logic is tested via the existing purchase test suite — utang integration is verified by the utang service tests already written.

- [ ] **Step 1: Add utang import to `apps/purchase/views.py`**

Find the import block at the top of the file. Add after the existing `.services` import:

```python
from apps.utang.services import create_utang_for_purchase, reverse_utang_for_purchase
```

- [ ] **Step 2: Wire `create_utang_for_purchase` at create site 1 (~line 1247)**

Find this block (single-prefix path, create/update in-place):
```python
            create_aset_tetap_records(purchase)
            create_aset_lainnya_records(purchase)
            created_purchases.append(purchase)
```

Change to:
```python
            create_aset_tetap_records(purchase)
            create_aset_lainnya_records(purchase)
            create_utang_for_purchase(purchase)
            created_purchases.append(purchase)
```

- [ ] **Step 3: Wire `create_utang_for_purchase` at create site 2 (~line 1287)**

Find this block (multi-prefix path, inside the `for pfx` loop):
```python
                create_aset_tetap_records(purchase)
                create_aset_lainnya_records(purchase)
                created_purchases.append(purchase)
```

Change to:
```python
                create_aset_tetap_records(purchase)
                create_aset_lainnya_records(purchase)
                create_utang_for_purchase(purchase)
                created_purchases.append(purchase)
```

- [ ] **Step 4: Wire `reverse_utang_for_purchase` at reverse site 1 — update reset (~line 1194)**

Find this block:
```python
            reverse_fifo_batches(existing)
            reverse_automated_journals(existing)
            existing.entitas_groups.all().delete()
```

Change to:
```python
            reverse_fifo_batches(existing)
            reverse_utang_for_purchase(existing)
            reverse_automated_journals(existing)
            existing.entitas_groups.all().delete()
```

- [ ] **Step 5: Wire `reverse_utang_for_purchase` at reverse site 2 — explicit delete (~line 565)**

Find this block inside `with transaction.atomic()` in the delete view:
```python
            reverse_fifo_batches(purchase)
            reverse_automated_journals(purchase)
            purchase.delete()
```

Change to:
```python
            reverse_fifo_batches(purchase)
            reverse_utang_for_purchase(purchase)
            reverse_automated_journals(purchase)
            purchase.delete()
```

- [ ] **Step 6: Wire `reverse_utang_for_purchase` at reverse site 3 — prefix change (~line 1214)**

Find this block:
```python
            else:
                # Prefix changed — delete old and create new
                existing.delete()
```

Change to:
```python
            else:
                # Prefix changed — delete old and create new
                reverse_utang_for_purchase(existing)
                existing.delete()
```

- [ ] **Step 7: Wire `reverse_utang_for_purchase` at reverse site 4 — split delete (~line 1251)**

Find this block:
```python
            # Delete existing if it exists (we're splitting into multiple)
            if existing:
                existing.delete()
```

Change to:
```python
            # Delete existing if it exists (we're splitting into multiple)
            if existing:
                reverse_utang_for_purchase(existing)
                existing.delete()
```

- [ ] **Step 8: Verify Django check passes**

Run:
```
python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 9: Commit**

```bash
git add apps/purchase/views.py
git commit -m "feat(purchase): wire create_utang_for_purchase at 2 create sites; reverse_utang_for_purchase at 4 reverse sites"
```

---

## Task 8: Fix Forms

**Files:**
- Modify: `apps/utang/forms.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Add form tests to `apps/utang/tests.py`**

Append:

```python
class UtangFormTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]

    def test_payment_form_utang_detail_scoped_to_header(self):
        from .forms import UtangPembayaranForm
        # Create a second utang to pollute the queryset
        from apps.purchase.models import PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem
        purchase2 = PurchaseHeader.objects.create(
            transaction_id='PUR-INV-0002', tanggal=date(2026, 4, 29), deskripsi='Test2',
        )
        pg2 = PurchaseEntitasBisnis.objects.create(
            purchase_header=purchase2, entitas_bisnis=self.f['eb'],
        )
        PurchaseItem.objects.create(
            purchase_eb=pg2,
            item=self.f['item'],
            sub_transaction_type=self.f['sub_type'],
            coa_account=self.f['coa_cash'],
            offset_coa_account=self.f['coa_utang'],
            quantity=Decimal('1'),
            unit_price=Decimal('1000'),
        )
        create_utang_for_purchase(purchase2)
        # Form scoped to self.utang should only see its own 1 detail
        form = UtangPembayaranForm(utang_header=self.utang)
        self.assertEqual(form.fields['utang_detail'].queryset.count(), 1)

    def test_payment_form_coa_filtered_to_aset(self):
        from .forms import UtangPembayaranForm
        form = UtangPembayaranForm(utang_header=self.utang)
        for akun in form.fields['coa_account'].queryset:
            self.assertEqual(akun.kategori_id, 'aset')

    def test_header_form_filters_entitas_to_pemasok(self):
        from .forms import UtangHeaderForm
        # Create a pelanggan entity — should not appear
        tipe = TipeEntitas.objects.first()
        EntitasBisnis.objects.create(
            nama='PT Pelanggan', tipe_entitas=tipe, relasi='pelanggan',
        )
        form = UtangHeaderForm()
        for eb in form.fields['entitas_bisnis'].queryset:
            self.assertIn(eb.relasi, ['pemasok', 'keduanya'])
```

- [ ] **Step 2: Run to confirm failures**

Run:
```
python manage.py test apps.utang.tests.UtangFormTests -v 2
```
Expected: All 3 FAIL — forms not yet filtered.

- [ ] **Step 3: Rewrite `apps/utang/forms.py`**

Replace the entire file:

```python
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun

from .models import UtangDetail, UtangHeader, UtangPembayaran


class UtangHeaderForm(forms.ModelForm):
    class Meta:
        model = UtangHeader
        fields = ['tanggal', 'entitas_bisnis', 'total_amount', 'deskripsi']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'total_amount': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].required = False
        self.fields['deskripsi'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            relasi__in=['pemasok', 'keduanya'],
            status_aktif=True,
        )


class UtangPembayaranForm(forms.ModelForm):
    class Meta:
        model = UtangPembayaran
        fields = ['utang_detail', 'tanggal', 'coa_account', 'jumlah', 'keterangan']
        widgets = {
            'utang_detail': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'coa_account': forms.Select(attrs={'class': 'ni-input'}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, utang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['utang_detail'].required = False
        self.fields['coa_account'].queryset = Akun.objects.filter(kategori_id='aset')
        if utang_header is not None:
            self.fields['utang_detail'].queryset = UtangDetail.objects.filter(
                utang_header=utang_header,
            )
        else:
            self.fields['utang_detail'].queryset = UtangDetail.objects.none()
```

- [ ] **Step 4: Run form tests**

Run:
```
python manage.py test apps.utang.tests.UtangFormTests -v 2
```
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/utang/forms.py apps/utang/tests.py
git commit -m "fix(utang): scope utang_detail and coa_account in payment form; filter entitas_bisnis to pemasok"
```

---

## Task 9: Utang Views — Guards + `utang_payment_delete` + Reporting Views

**Files:**
- Modify: `apps/utang/views.py`
- Modify: `apps/utang/tests.py`

- [ ] **Step 1: Add view tests**

Append to `apps/utang/tests.py`:

```python
from django.contrib.auth import get_user_model
from django.test import Client

UserModel = get_user_model()


class UtangViewGuardTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang_from_purchase = headers[0]
        # Manual utang (no purchase_header)
        self.manual_utang = create_manual_utang(
            tanggal=date(2026, 4, 28),
            entitas_bisnis=self.f['eb'],
            coa_utang_account=self.f['coa_utang'],
            total_amount=Decimal('50000'),
            deskripsi='Manual',
        )
        self.user = UserModel.objects.create_user(
            username='testuser', password='testpass',
        )
        self.client = Client()
        self.client.login(username='testuser', password='testpass')

    def test_utang_update_blocks_purchase_linked_utang(self):
        response = self.client.post(
            f'/utang/{self.utang_from_purchase.pk}/edit/',
            {'tanggal': '2026-04-28', 'total_amount': '999'},
        )
        self.assertRedirects(
            response, f'/utang/{self.utang_from_purchase.pk}/',
            fetch_redirect_response=False,
        )
        self.utang_from_purchase.refresh_from_db()
        self.assertNotEqual(self.utang_from_purchase.total_amount, Decimal('999'))

    def test_utang_update_allows_manual_utang(self):
        response = self.client.post(
            f'/utang/{self.manual_utang.pk}/edit/',
            {
                'tanggal': '2026-04-28',
                'total_amount': '50000',
                'deskripsi': 'Updated',
            },
        )
        self.assertRedirects(
            response, f'/utang/{self.manual_utang.pk}/',
            fetch_redirect_response=False,
        )

    def test_utang_delete_blocked_when_locked(self):
        self.manual_utang.is_locked = True
        self.manual_utang.save()
        response = self.client.post(f'/utang/{self.manual_utang.pk}/delete/')
        self.assertRedirects(
            response, f'/utang/{self.manual_utang.pk}/',
            fetch_redirect_response=False,
        )
        self.assertTrue(UtangHeader.objects.filter(pk=self.manual_utang.pk).exists())

    def test_utang_pay_blocked_when_locked(self):
        self.utang_from_purchase.is_locked = True
        self.utang_from_purchase.save()
        response = self.client.post(
            f'/utang/{self.utang_from_purchase.pk}/bayar/',
            {
                'tanggal': '2026-04-28',
                'coa_account': self.f['coa_cash'].pk,
                'jumlah': '10000',
                'keterangan': '',
            },
        )
        self.assertRedirects(
            response, f'/utang/{self.utang_from_purchase.pk}/',
            fetch_redirect_response=False,
        )
        self.assertEqual(UtangPembayaran.objects.count(), 0)

    def test_payment_delete_cancels_payment(self):
        payment = create_utang_payment(
            self.utang_from_purchase,
            utang_detail=self.utang_from_purchase.details.first(),
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('10000'),
            keterangan='Test',
        )
        response = self.client.post(
            f'/utang/{self.utang_from_purchase.pk}/bayar/{payment.pk}/hapus/',
        )
        self.assertRedirects(
            response, f'/utang/{self.utang_from_purchase.pk}/',
            fetch_redirect_response=False,
        )
        self.assertFalse(UtangPembayaran.objects.filter(pk=payment.pk).exists())
```

- [ ] **Step 2: Run to confirm failures**

Run:
```
python manage.py test apps.utang.tests.UtangViewGuardTests -v 2
```
Expected: Multiple failures — `payment_delete` URL doesn't exist, guards not implemented.

- [ ] **Step 3: Rewrite `apps/utang/views.py`**

Replace the entire file:

```python
from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UtangHeaderForm, UtangPembayaranForm
from .models import UtangHeader, UtangPembayaran
from .services import (
    create_manual_utang,
    create_utang_payment,
    get_utang_aging,
    get_utang_jatuh_tempo,
    get_utang_per_group_akun,
    get_utang_per_subjek,
    reverse_utang_header,
    reverse_utang_payment,
)


@login_required
def utang_list(request: HttpRequest) -> HttpResponse:
    utangs = UtangHeader.objects.select_related('entitas_bisnis').order_by(
        '-tanggal', '-created_at'
    )
    return render(request, 'utang/list.html', {'utangs': utangs})


@login_required
def utang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(
        UtangHeader.objects.select_related('entitas_bisnis').prefetch_related(
            'details__purchase_item__item', 'pembayaran__coa_account',
        ),
        pk=pk,
    )
    payment_form = UtangPembayaranForm(
        utang_header=utang, initial={'tanggal': utang.tanggal}
    )
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': payment_form})


@login_required
def utang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST)
        if form.is_valid():
            utang = create_manual_utang(**form.cleaned_data)
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dibuat.')
            return redirect('utang:detail', pk=utang.pk)
    else:
        form = UtangHeaderForm()
    return render(request, 'utang/form.html', {'form': form, 'title': 'Tambah Utang'})


@login_required
def utang_update(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.purchase_header_id:
        dj_messages.error(request, 'Utang dari purchase tidak bisa diedit manual.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST, instance=utang)
        if form.is_valid():
            form.save()
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil diperbarui.')
            return redirect('utang:detail', pk=pk)
    else:
        form = UtangHeaderForm(instance=utang)
    return render(request, 'utang/form.html', {'form': form, 'title': 'Edit Utang'})


@login_required
def utang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah terkunci (periode tutup buku).')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        reverse_utang_header(utang, request.user)
        dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dihapus.')
        return redirect('utang:list')
    return render(request, 'utang/delete.html', {'utang': utang})


@login_required
def utang_pay(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah terkunci (periode tutup buku).')
        return redirect('utang:detail', pk=pk)
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    form = UtangPembayaranForm(request.POST, utang_header=utang)
    if form.is_valid():
        try:
            create_utang_payment(utang, **form.cleaned_data)
            dj_messages.success(
                request, f'Pembayaran untuk {utang.nomor_utang} berhasil dicatat.'
            )
            return redirect('utang:detail', pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': form})


@login_required
def utang_payment_delete(request: HttpRequest, pk: int, payment_pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    payment = get_object_or_404(UtangPembayaran, pk=payment_pk, utang_header=utang)
    if utang.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah terkunci (periode tutup buku).')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        reverse_utang_payment(payment, request.user)
        dj_messages.success(request, 'Pembayaran berhasil dibatalkan.')
        return redirect('utang:detail', pk=pk)
    return render(request, 'utang/payment_delete.html', {'utang': utang, 'payment': payment})


@login_required
def utang_report_subjek(request: HttpRequest) -> HttpResponse:
    data = list(get_utang_per_subjek())
    if request.GET.get('format') == 'json':
        return JsonResponse({'data': data})
    return render(request, 'utang/report_subjek.html', {'data': data})


@login_required
def utang_report_akun(request: HttpRequest) -> HttpResponse:
    data = list(get_utang_per_group_akun())
    if request.GET.get('format') == 'json':
        return JsonResponse({'data': data})
    return render(request, 'utang/report_akun.html', {'data': data})


@login_required
def utang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_utang_aging()
    if request.GET.get('format') == 'json':
        serialized = {
            k: [
                {
                    'nomor': e['utang'].nomor_utang,
                    'outstanding': str(e['outstanding']),
                    'hari': e['hari'],
                }
                for e in v
            ]
            for k, v in buckets.items()
        }
        return JsonResponse({'data': serialized})
    return render(request, 'utang/report_aging.html', {'buckets': buckets})


@login_required
def utang_report_jatuh_tempo(request: HttpRequest) -> HttpResponse:
    hari = int(request.GET.get('hari', 7))
    utangs = list(get_utang_jatuh_tempo(hari_ke_depan=hari))
    if request.GET.get('format') == 'json':
        data = [
            {
                'nomor': u.nomor_utang,
                'entitas': str(u.entitas_bisnis),
                'jatuh_tempo': str(u.tanggal_jatuh_tempo),
                'total': str(u.total_amount),
            }
            for u in utangs
        ]
        return JsonResponse({'data': data})
    return render(
        request, 'utang/report_jatuh_tempo.html', {'utangs': utangs, 'hari': hari}
    )
```

- [ ] **Step 4: Run view tests (they'll fail because URLs don't exist yet — that's OK)**

Run:
```
python manage.py test apps.utang.tests.UtangViewGuardTests -v 2
```
Expected: Failures due to URL resolution (`NoReverseMatch`). Proceed to Task 10.

---

## Task 10: URLs + Templates

**Files:**
- Modify: `apps/utang/urls.py`
- Create: `templates/utang/payment_delete.html`
- Create: `templates/utang/report_subjek.html`
- Create: `templates/utang/report_akun.html`
- Create: `templates/utang/report_aging.html`
- Create: `templates/utang/report_jatuh_tempo.html`

- [ ] **Step 1: Update `apps/utang/urls.py`**

Replace the entire file:

```python
from django.urls import path

from . import views

app_name = 'utang'

urlpatterns = [
    path('', views.utang_list, name='list'),
    path('create/', views.utang_create, name='create'),
    path('<int:pk>/', views.utang_detail, name='detail'),
    path('<int:pk>/edit/', views.utang_update, name='update'),
    path('<int:pk>/delete/', views.utang_delete, name='delete'),
    path('<int:pk>/bayar/', views.utang_pay, name='pay'),
    path('<int:pk>/bayar/<int:payment_pk>/hapus/', views.utang_payment_delete, name='payment_delete'),
    path('laporan/subjek/', views.utang_report_subjek, name='report_subjek'),
    path('laporan/akun/', views.utang_report_akun, name='report_akun'),
    path('laporan/aging/', views.utang_report_aging, name='report_aging'),
    path('laporan/jatuh-tempo/', views.utang_report_jatuh_tempo, name='report_jatuh_tempo'),
]
```

- [ ] **Step 2: Create `templates/utang/payment_delete.html`**

```html
{% extends 'base.html' %}
{% block title %}Hapus Pembayaran{% endblock %}
{% block content %}
<div class="ni-card ni-animate-fade-in" style="max-width:560px; margin:0 auto;">
  <div class="ni-card__body" style="text-align:center; padding:40px 32px;">
    <div style="width:48px;height:48px;border-radius:50%;background:#fef2f2;color:var(--ni-danger);display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
      <i data-lucide="trash-2" style="width:24px;height:24px"></i>
    </div>
    <p style="font-size:1rem;color:var(--ni-text);margin-bottom:8px;">
      Batalkan pembayaran sebesar <strong>{{ payment.jumlah }}</strong>?
    </p>
    <p style="font-size:0.875rem;color:var(--ni-text-muted);margin-bottom:24px;">
      Jurnal pembayaran untuk <strong>{{ utang.nomor_utang }}</strong> akan dihapus.
    </p>
    <form method="post">
      {% csrf_token %}
      <div class="ni-btn-row" style="justify-content:center;">
        <button type="submit" class="ni-btn ni-btn--danger">Ya, Batalkan</button>
        <a href="{% url 'utang:detail' utang.pk %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `templates/utang/report_subjek.html`**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Laporan Utang per Pemasok{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Utang per Pemasok</h1>
    <p class="ni-page-header__subtitle">Total utang terbuka per entitas bisnis</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="?format=json" class="ni-btn ni-btn--secondary">JSON</a>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Pemasok</th>
          <th class="ni-text-right">Total Utang</th>
          <th class="ni-text-right">Total Bayar</th>
          <th class="ni-text-right">Jumlah Invoice</th>
        </tr>
      </thead>
      <tbody>
        {% for row in data %}
        <tr>
          <td>{{ row.entitas_bisnis__nama|default:'-' }}</td>
          <td class="ni-text-right">{{ row.total_utang|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.total_bayar|default:0|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.jumlah_invoice }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="4" class="ni-text-center ni-text-muted">Tidak ada data.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Create `templates/utang/report_akun.html`**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Laporan Utang per Akun{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Utang per Akun</h1>
    <p class="ni-page-header__subtitle">Total utang terbuka per akun COA</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="?format=json" class="ni-btn ni-btn--secondary">JSON</a>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Kode Akun</th>
          <th>Nama Akun</th>
          <th class="ni-text-right">Total</th>
        </tr>
      </thead>
      <tbody>
        {% for row in data %}
        <tr>
          <td>{{ row.coa_utang_account__kode_akun }}</td>
          <td>{{ row.coa_utang_account__nama }}</td>
          <td class="ni-text-right">{{ row.total|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="3" class="ni-text-center ni-text-muted">Tidak ada data.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create `templates/utang/report_aging.html`**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Laporan Aging Utang{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Aging Utang</h1>
    <p class="ni-page-header__subtitle">Pengelompokan utang berdasarkan hari lewat jatuh tempo</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="?format=json" class="ni-btn ni-btn--secondary">JSON</a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__header"><h2 class="ni-card__title">Belum Jatuh Tempo</h2></div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Nomor</th><th>Pemasok</th><th class="ni-text-right">Outstanding</th></tr></thead>
      <tbody>
        {% for entry in buckets.current %}
        <tr>
          <td><a href="{% url 'utang:detail' entry.utang.pk %}">{{ entry.utang.nomor_utang }}</a></td>
          <td>{{ entry.utang.entitas_display }}</td>
          <td class="ni-text-right">{{ entry.outstanding|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}<tr><td colspan="3" class="ni-text-center ni-text-muted">-</td></tr>{% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__header"><h2 class="ni-card__title">1–30 Hari</h2></div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Nomor</th><th>Pemasok</th><th class="ni-text-right">Hari</th><th class="ni-text-right">Outstanding</th></tr></thead>
      <tbody>
        {% for entry in buckets.due_1_30 %}
        <tr>
          <td><a href="{% url 'utang:detail' entry.utang.pk %}">{{ entry.utang.nomor_utang }}</a></td>
          <td>{{ entry.utang.entitas_display }}</td>
          <td class="ni-text-right">{{ entry.hari }}</td>
          <td class="ni-text-right">{{ entry.outstanding|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}<tr><td colspan="4" class="ni-text-center ni-text-muted">-</td></tr>{% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="ni-card ni-animate-fade-in" style="margin-bottom:16px;">
  <div class="ni-card__header"><h2 class="ni-card__title">31–60 Hari</h2></div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Nomor</th><th>Pemasok</th><th class="ni-text-right">Hari</th><th class="ni-text-right">Outstanding</th></tr></thead>
      <tbody>
        {% for entry in buckets.due_31_60 %}
        <tr>
          <td><a href="{% url 'utang:detail' entry.utang.pk %}">{{ entry.utang.nomor_utang }}</a></td>
          <td>{{ entry.utang.entitas_display }}</td>
          <td class="ni-text-right">{{ entry.hari }}</td>
          <td class="ni-text-right">{{ entry.outstanding|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}<tr><td colspan="4" class="ni-text-center ni-text-muted">-</td></tr>{% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">&gt;60 Hari</h2></div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Nomor</th><th>Pemasok</th><th class="ni-text-right">Hari</th><th class="ni-text-right">Outstanding</th></tr></thead>
      <tbody>
        {% for entry in buckets.due_60_plus %}
        <tr>
          <td><a href="{% url 'utang:detail' entry.utang.pk %}">{{ entry.utang.nomor_utang }}</a></td>
          <td>{{ entry.utang.entitas_display }}</td>
          <td class="ni-text-right">{{ entry.hari }}</td>
          <td class="ni-text-right">{{ entry.outstanding|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}<tr><td colspan="4" class="ni-text-center ni-text-muted">-</td></tr>{% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Create `templates/utang/report_jatuh_tempo.html`**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Utang Jatuh Tempo{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Utang Jatuh Tempo</h1>
    <p class="ni-page-header__subtitle">Jatuh tempo dalam {{ hari }} hari ke depan</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="?hari=30" class="ni-btn ni-btn--secondary">30 hari</a>
    <a href="?hari=7" class="ni-btn ni-btn--secondary">7 hari</a>
    <a href="?format=json&hari={{ hari }}" class="ni-btn ni-btn--secondary">JSON</a>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Nomor</th>
          <th>Pemasok</th>
          <th>Jatuh Tempo</th>
          <th class="ni-text-right">Total</th>
        </tr>
      </thead>
      <tbody>
        {% for u in utangs %}
        <tr>
          <td><a href="{% url 'utang:detail' u.pk %}">{{ u.nomor_utang }}</a></td>
          <td>{{ u.entitas_display }}</td>
          <td>{{ u.tanggal_jatuh_tempo }}</td>
          <td class="ni-text-right">{{ u.total_amount|floatformat:0|intcomma }}</td>
        </tr>
        {% empty %}
        <tr><td colspan="4" class="ni-text-center ni-text-muted">Tidak ada utang jatuh tempo.</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Run all utang tests**

Run:
```
python manage.py test apps.utang -v 2
```
Expected: All tests PASS

- [ ] **Step 8: Run full test suite**

Run:
```
python manage.py test
```
Expected: No regressions — all tests pass.

- [ ] **Step 9: Commit**

```bash
git add apps/utang/urls.py apps/utang/views.py templates/utang/
git commit -m "feat(utang): add payment_delete view, reporting views, 4 report URLs, 5 new templates"
```

---

## Self-Review Checklist

After implementing, verify these spec items are covered:

| # | Item | Task |
|---|------|------|
| 1 | Migration: tanggal_jatuh_tempo + is_locked | Task 1, 2 |
| 2 | Migration: payment_term_days on SubTransactionType | Task 1, 2 |
| 3 | Fix _next_utang_journal_number (ORDER BY) | Task 3 |
| 4 | Rewrite create_utang_for_purchase | Task 3 |
| 5 | UtangTerhapus written on reverse_utang_header | Task 4 |
| 6 | reverse_utang_for_purchase doesn't delete purchase journals | Task 4 |
| 7 | create_utang_payment select_for_update | Task 5 |
| 8 | reverse_utang_payment | Task 5 |
| 9 | 4 reporting functions | Task 6 |
| 10 | purchase/views.py — create_utang_for_purchase at 2 sites | Task 7 |
| 11 | purchase/views.py — reverse_utang_for_purchase at 4 sites | Task 7 |
| 12 | UtangPembayaranForm utang_detail scoped to header | Task 8 |
| 13 | UtangPembayaranForm coa_account filtered to aset | Task 8 |
| 14 | UtangHeaderForm entitas_bisnis filtered to pemasok | Task 8 |
| 15 | utang_update guard (purchase-linked) | Task 9 |
| 16 | utang_delete is_locked guard | Task 9 |
| 17 | utang_pay is_locked guard | Task 9 |
| 18 | utang_payment_delete view | Task 9 |
| 19 | pass utang_header to form in utang_detail + utang_pay | Task 9 |
| 20 | 4 reporting views (HTML + JSON) | Task 9 |
| 21 | 5 new URL patterns | Task 10 |
| 22 | 5 new templates | Task 10 |
