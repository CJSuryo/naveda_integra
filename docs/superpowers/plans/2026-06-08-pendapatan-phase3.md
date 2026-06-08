# Pendapatan Core — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `apps/pendapatan/` — a new Django app for revenue transactions with multi-EB join table pattern, journal generation, and piutang integration.

**Architecture:** Mirrors Sales architecture. `PendapatanHeader` → `PendapatanEntitasBisnis` (join table) → `PendapatanItem`. Confirm orchestrator generates journals and optionally creates piutang. Deferred and Recurring models added in later phases.

**Tech Stack:** Django 4.x, Python 3.11+, `django.test.TestCase`.

**Spec:** `docs/superpowers/specs/2026-06-07-pendapatan-design.md`

**Prerequisites:** Phase 1 (Piutang) complete. Phase 2 (Sales payment_type) complete.

---

## File Map

| Action | File |
|---|---|
| Create | `apps/pendapatan/__init__.py` |
| Create | `apps/pendapatan/apps.py` |
| Create | `apps/pendapatan/models.py` |
| Create | `apps/pendapatan/services.py` |
| Create | `apps/pendapatan/tests.py` |
| Create | `apps/pendapatan/forms.py` |
| Create | `apps/pendapatan/views.py` |
| Create | `apps/pendapatan/urls.py` |
| Create | `apps/pendapatan/admin.py` |
| Create | `apps/pendapatan/migrations/__init__.py` |
| Modify | `naveda_integra/settings/base.py` |
| Modify | `naveda_integra/urls.py` |
| Modify | `apps/purchase/models.py` (SubTransactionType MODULE_CHOICES) |
| Modify | `apps/piutang/services.py` (implement create_piutang_from_pendapatan stub) |
| Create | `templates/pendapatan/dashboard.html` |
| Create | `templates/pendapatan/list.html` |
| Create | `templates/pendapatan/form.html` |
| Create | `templates/pendapatan/detail.html` |

---

## Task 1: Create app skeleton

**Files:**
- Create: `apps/pendapatan/__init__.py`
- Create: `apps/pendapatan/apps.py`
- Create: `apps/pendapatan/migrations/__init__.py`
- Modify: `naveda_integra/settings/base.py`
- Modify: `naveda_integra/urls.py`

- [ ] **Step 1: Create directory and files**

```bash
mkdir apps/pendapatan apps/pendapatan/migrations
touch apps/pendapatan/__init__.py apps/pendapatan/migrations/__init__.py
```

- [ ] **Step 2: Create apps.py**

```python
# apps/pendapatan/apps.py
from django.apps import AppConfig


class PendapatanConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.pendapatan'
    verbose_name = 'Pendapatan'
```

- [ ] **Step 3: Register in INSTALLED_APPS**

In `naveda_integra/settings/base.py`, add to `INSTALLED_APPS` after `apps.piutang`:

```python
'apps.pendapatan',
```

- [ ] **Step 4: Register URL**

In `naveda_integra/urls.py`, add after piutang line:

```python
path('pendapatan/', include('apps.pendapatan.urls', namespace='pendapatan')),
```

- [ ] **Step 5: Add SubTransactionType 'pendapatan' module choice**

In `apps/purchase/models.py`, find `MODULE_CHOICES` on `SubTransactionType`:

```python
MODULE_CHOICES = [
    ('purchase', 'Purchase'),
    ('sales', 'Sales'),
    ('pendapatan', 'Pendapatan'),  # ADD THIS LINE
]
```

Run makemigrations for purchase:

```bash
python manage.py makemigrations purchase --name add_pendapatan_module_choice
python manage.py migrate purchase
```

- [ ] **Step 6: Commit skeleton**

```bash
git add apps/pendapatan/ naveda_integra/settings/base.py naveda_integra/urls.py apps/purchase/models.py apps/purchase/migrations/
git commit -m "feat(pendapatan): create app skeleton and register in settings/urls"
```

---

## Task 2: Models

**Files:**
- Create: `apps/pendapatan/models.py`

- [ ] **Step 1: Write models.py**

```python
# apps/pendapatan/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


KATEGORI_CHOICES = [
    ('sewa', 'Sewa'),
    ('jasa', 'Jasa'),
    ('bunga', 'Bunga'),
    ('dividen', 'Dividen'),
    ('komisi', 'Komisi'),
    ('royalti', 'Royalti'),
    ('management_fee', 'Management Fee'),
    ('penjualan_aset', 'Penjualan Aset'),
    ('lainnya', 'Lainnya'),
]

DEFERRED_METODE_CHOICES = [
    ('straight_line', 'Garis Lurus'),
    ('custom', 'Custom'),
]

TAX_TYPE_CHOICES = [
    ('ppn_keluaran', 'PPN Keluaran'),
    ('pph_23', 'PPh 23'),
    ('pph_21', 'PPh 21'),
    ('pph_4_2', 'PPh 4(2)'),
]

TAX_PAYMENT_CHOICES = [
    ('belum_transfer', 'Belum Transfer'),
    ('sudah_transfer', 'Sudah Transfer'),
]


class PendapatanHeader(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Dikonfirmasi'),
        ('voided', 'Dibatalkan'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('from_sales', 'Dari Sales'),
        ('recurring', 'Recurring'),
    ]

    transaction_id = models.CharField(max_length=100, unique=True, editable=False, verbose_name='ID Transaksi')
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    deskripsi = models.TextField(blank=True, default='', verbose_name='Deskripsi')
    source_type = models.CharField(
        max_length=20, choices=SOURCE_TYPE_CHOICES, default='manual', verbose_name='Sumber',
    )
    source_sales = models.ForeignKey(
        'sales.SalesHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_headers', verbose_name='Sales Header',
    )
    source_recurring = models.ForeignKey(
        'pendapatan.RecurringTemplate', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='generated_headers', verbose_name='Recurring Template',
    )
    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'Cash'), ('credit', 'Kredit')],
        default='cash',
        verbose_name='Tipe Pembayaran',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Status',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pendapatan Header'
        verbose_name_plural = 'Pendapatan Header'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='idx_pendh_tanggal_status'),
        ]

    def __str__(self) -> str:
        return self.transaction_id

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = self._generate_transaction_id()
        super().save(*args, **kwargs)

    def _generate_transaction_id(self) -> str:
        from django.db import transaction as db_transaction
        prefix = 'TRX-PND'
        with db_transaction.atomic():
            last = (
                PendapatanHeader.objects
                .select_for_update()
                .filter(transaction_id__startswith=f'{prefix}-')
                .order_by('-transaction_id')
                .values_list('transaction_id', flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f'{prefix}-{seq:03d}'


class PendapatanEntitasBisnis(models.Model):
    pendapatan_header = models.ForeignKey(
        PendapatanHeader, on_delete=models.CASCADE, related_name='entitas_groups',
        verbose_name='Pendapatan Header',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='pendapatan_groups', verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_groups', verbose_name='EB Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_groups', verbose_name='EB Lv3',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_eb_payment', verbose_name='Akun Pembayaran',
    )

    class Meta:
        verbose_name = 'Pendapatan Entitas Bisnis'
        verbose_name_plural = 'Pendapatan Entitas Bisnis'
        indexes = [
            models.Index(fields=['pendapatan_header', 'entitas_bisnis'], name='idx_peb_header_eb'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_header.transaction_id} → {self.entitas_bisnis.nama}'


class PendapatanItem(models.Model):
    pendapatan_eb = models.ForeignKey(
        PendapatanEntitasBisnis, on_delete=models.CASCADE, related_name='items',
        verbose_name='Pendapatan EB Group',
    )
    deskripsi_item = models.TextField(verbose_name='Deskripsi Item')
    kategori = models.CharField(max_length=30, choices=KATEGORI_CHOICES, verbose_name='Kategori')
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType', on_delete=models.PROTECT,
        related_name='pendapatan_items', verbose_name='Sub-Tipe Transaksi',
    )
    jumlah_bruto = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Bruto')
    revenue_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='pendapatan_item_revenue', verbose_name='Akun Pendapatan',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_payment', verbose_name='Akun Pembayaran',
    )
    # Tax (identical pattern to SalesItem)
    tax = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True, verbose_name='Pajak (Nominal)')
    tax_type = models.CharField(max_length=30, choices=TAX_TYPE_CHOICES, blank=True, default='', verbose_name='Tipe Pajak')
    tax_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_tax', verbose_name='Akun Pajak',
    )
    tax_payment = models.CharField(max_length=20, choices=TAX_PAYMENT_CHOICES, blank=True, default='', verbose_name='Status Transfer Pajak')
    tax_payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_tax_payment', verbose_name='Akun Utang Pajak',
    )
    # Deferred revenue fields (revealed when is_deferred=True)
    is_deferred = models.BooleanField(default=False, verbose_name='Pendapatan Diterima di Muka')
    deferred_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_deferred', verbose_name='Akun Deferred (Liability)',
    )
    recognition_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pendapatan_item_recognition', verbose_name='Akun Pengakuan',
    )
    deferred_tanggal_mulai = models.DateField(null=True, blank=True, verbose_name='Tanggal Mulai Pengakuan')
    deferred_tanggal_selesai = models.DateField(null=True, blank=True, verbose_name='Tanggal Selesai Pengakuan')
    deferred_metode = models.CharField(
        max_length=20, choices=DEFERRED_METODE_CHOICES, blank=True, default='straight_line',
        verbose_name='Metode Pengakuan',
    )

    class Meta:
        verbose_name = 'Pendapatan Item'
        verbose_name_plural = 'Pendapatan Item'
        indexes = [
            models.Index(fields=['pendapatan_eb'], name='idx_pi_eb'),
            models.Index(fields=['sub_transaction_type'], name='idx_pi_stt'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_eb.pendapatan_header.transaction_id} — {self.deskripsi_item[:40]}'


class PendapatanEventLog(models.Model):
    EVENT_CHOICES = [
        ('CREATED', 'Dibuat'),
        ('CONFIRMED', 'Dikonfirmasi'),
        ('VOIDED', 'Dibatalkan'),
        ('JOURNAL_CREATED', 'Jurnal Dibuat'),
        ('PIUTANG_CREATED', 'Piutang Dibuat'),
        ('DEFERRED_SCHEDULED', 'Deferred Dijadwalkan'),
        ('RECURRING_GENERATED', 'Dihasilkan dari Recurring'),
    ]

    pendapatan_header = models.ForeignKey(
        PendapatanHeader, on_delete=models.CASCADE, related_name='event_logs',
        verbose_name='Pendapatan Header',
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    description = models.TextField(blank=True, default='')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pendapatan_event_logs',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Event Log Pendapatan'
        verbose_name_plural = 'Event Log Pendapatan'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['pendapatan_header', 'timestamp'], name='idx_pel_header_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.pendapatan_header.transaction_id} — {self.event_type} @ {self.timestamp}'


class RecurringTemplate(models.Model):
    """Placeholder — fully implemented in Phase 5."""
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Recurring Template'
        verbose_name_plural = 'Recurring Template'

    def __str__(self) -> str:
        return self.nama
```

- [ ] **Step 2: Run makemigrations**

```bash
python manage.py makemigrations pendapatan
```

Expected: `Migrations for 'pendapatan': apps/pendapatan/migrations/0001_initial.py`

- [ ] **Step 3: Run migrate**

```bash
python manage.py migrate pendapatan
```

Expected: `Applying pendapatan.0001_initial... OK`

- [ ] **Step 4: Commit**

```bash
git add apps/pendapatan/models.py apps/pendapatan/migrations/
git commit -m "feat(pendapatan): add models — PendapatanHeader, EB, Item, EventLog"
```

---

## Task 3: Service — confirm_pendapatan + journals

**Files:**
- Create: `apps/pendapatan/services.py`
- Create: `apps/pendapatan/tests.py`

- [ ] **Step 1: Write failing tests**

```python
# apps/pendapatan/tests.py
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType

from .models import PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog
from .services import confirm_pendapatan, create_pendapatan_header


def make_fixtures():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT Sewa', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1')
    stt = SubTransactionType.objects.create(
        nama='Sewa', module='pendapatan', direction='inflow',
        default_offset_account=coa_revenue,
    )
    return {'tipe': tipe, 'eb': eb, 'coa_kas': coa_kas, 'coa_piutang': coa_piutang,
            'coa_revenue': coa_revenue, 'stt': stt}


def make_header(f, payment_type='cash'):
    header = create_pendapatan_header(
        tanggal=date(2026, 6, 1),
        deskripsi='Sewa bulan Juni',
        payment_type=payment_type,
        entitas_bisnis=f['eb'],
        payment_account=f['coa_kas'] if payment_type == 'cash' else f['coa_piutang'],
        items=[{
            'deskripsi_item': 'Sewa Gedung A',
            'kategori': 'sewa',
            'sub_transaction_type': f['stt'],
            'jumlah_bruto': Decimal('5000000'),
            'revenue_account': f['coa_revenue'],
            'payment_account': f['coa_kas'] if payment_type == 'cash' else f['coa_piutang'],
        }],
    )
    return header


class CreatePendapatanHeaderTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_header_with_draft_status(self):
        header = make_header(self.f)
        self.assertEqual(header.status, 'draft')
        self.assertTrue(header.transaction_id.startswith('TRX-PND-'))

    def test_creates_eb_group_and_item(self):
        header = make_header(self.f)
        self.assertEqual(header.entitas_groups.count(), 1)
        eb_group = header.entitas_groups.first()
        self.assertEqual(eb_group.items.count(), 1)

    def test_logs_created_event(self):
        make_header(self.f)
        self.assertEqual(PendapatanEventLog.objects.filter(event_type='CREATED').count(), 1)


class ConfirmPendapatanCashTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.header = make_header(self.f, payment_type='cash')

    def test_status_becomes_confirmed(self):
        confirm_pendapatan(self.header)
        self.header.refresh_from_db()
        self.assertEqual(self.header.status, 'confirmed')

    def test_generates_journal(self):
        from apps.jurnal.models import JurnalHeader
        confirm_pendapatan(self.header)
        self.assertGreater(JurnalHeader.objects.count(), 0)

    def test_cash_journal_dr_payment_cr_revenue(self):
        confirm_pendapatan(self.header)
        from apps.jurnal.models import JurnalDetail
        dr = JurnalDetail.objects.filter(debit__gt=0).first()
        cr = JurnalDetail.objects.filter(kredit__gt=0).first()
        self.assertEqual(dr.akun, self.f['coa_kas'])
        self.assertEqual(cr.akun, self.f['coa_revenue'])

    def test_raises_if_already_confirmed(self):
        confirm_pendapatan(self.header)
        self.header.refresh_from_db()
        with self.assertRaises(ValueError):
            confirm_pendapatan(self.header)


class ConfirmPendapatanCreditTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.header = make_header(self.f, payment_type='credit')

    def test_creates_piutang_header(self):
        from apps.piutang.models import PiutangHeader
        confirm_pendapatan(self.header)
        self.assertEqual(PiutangHeader.objects.filter(source_pendapatan=self.header).count(), 1)

    def test_credit_journal_dr_piutang_cr_revenue(self):
        confirm_pendapatan(self.header)
        from apps.jurnal.models import JurnalDetail
        dr = JurnalDetail.objects.filter(debit__gt=0).first()
        cr = JurnalDetail.objects.filter(kredit__gt=0).first()
        self.assertEqual(dr.akun, self.f['coa_piutang'])
        self.assertEqual(cr.akun, self.f['coa_revenue'])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test apps.pendapatan.tests -v 2
```

Expected: ImportError — `create_pendapatan_header` not found.

- [ ] **Step 3: Write services.py**

```python
# apps/pendapatan/services.py
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import (
    PendapatanEntitasBisnis, PendapatanEventLog, PendapatanHeader, PendapatanItem,
)


def _log_event(header: PendapatanHeader, event_type: str, description: str = '', actor=None):
    PendapatanEventLog.objects.create(
        pendapatan_header=header,
        event_type=event_type,
        description=description,
        actor=actor,
    )


def _next_journal_number(prefix: str) -> str:
    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith=f'{prefix}-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        seq = 1
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        return f'{prefix}-{seq:04d}'


def create_pendapatan_header(
    tanggal,
    deskripsi: str,
    payment_type: str,
    entitas_bisnis,
    payment_account,
    items: list,
    entitas_bisnis_lv2=None,
    entitas_bisnis_lv3=None,
    source_type: str = 'manual',
    user=None,
) -> PendapatanHeader:
    if not items:
        raise ValueError('Minimal satu item diperlukan.')

    with transaction.atomic():
        header = PendapatanHeader.objects.create(
            tanggal=tanggal,
            deskripsi=deskripsi,
            payment_type=payment_type,
            source_type=source_type,
            status='draft',
            created_by=user,
        )
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header,
            entitas_bisnis=entitas_bisnis,
            entitas_bisnis_lv2=entitas_bisnis_lv2,
            entitas_bisnis_lv3=entitas_bisnis_lv3,
            payment_account=payment_account,
        )
        PendapatanItem.objects.bulk_create([
            PendapatanItem(
                pendapatan_eb=eb_group,
                deskripsi_item=it['deskripsi_item'],
                kategori=it['kategori'],
                sub_transaction_type=it['sub_transaction_type'],
                jumlah_bruto=Decimal(str(it['jumlah_bruto'])),
                revenue_account=it['revenue_account'],
                payment_account=it.get('payment_account'),
                tax=it.get('tax'),
                tax_type=it.get('tax_type', ''),
                tax_account=it.get('tax_account'),
                tax_payment=it.get('tax_payment', ''),
                tax_payment_account=it.get('tax_payment_account'),
                is_deferred=it.get('is_deferred', False),
                deferred_account=it.get('deferred_account'),
                recognition_account=it.get('recognition_account'),
                deferred_tanggal_mulai=it.get('deferred_tanggal_mulai'),
                deferred_tanggal_selesai=it.get('deferred_tanggal_selesai'),
                deferred_metode=it.get('deferred_metode', 'straight_line'),
            )
            for it in items
        ])
        _log_event(header, 'CREATED', actor=user)
    return header


def confirm_pendapatan(header: PendapatanHeader, user=None):
    if header.status != 'draft':
        raise ValueError(f'Hanya transaksi berstatus draft yang dapat dikonfirmasi. Status saat ini: {header.status}')

    with transaction.atomic():
        _create_pendapatan_journals(header, user)

        if header.payment_type == 'credit':
            from apps.piutang.services import create_piutang_from_pendapatan
            piutang = create_piutang_from_pendapatan(header, user)
            _log_event(header, 'PIUTANG_CREATED', description=piutang.nomor_piutang, actor=user)

        # Deferred items — handled in Phase 4
        for eb_group in header.entitas_groups.prefetch_related('items').all():
            for item in eb_group.items.filter(is_deferred=True):
                try:
                    from .deferred_services import create_deferred_schedule
                    create_deferred_schedule(item)
                    _log_event(header, 'DEFERRED_SCHEDULED', description=str(item.pk), actor=user)
                except ImportError:
                    pass  # deferred_services not yet implemented — skip in Phase 3

        header.status = 'confirmed'
        header.save(update_fields=['status'])
        _log_event(header, 'CONFIRMED', actor=user)


def void_pendapatan(header: PendapatanHeader, user=None):
    if header.status != 'confirmed':
        raise ValueError('Hanya transaksi terkonfirmasi yang dapat dibatalkan.')
    if header.is_locked:
        raise ValueError('Transaksi terkunci — tidak dapat dibatalkan.')

    with transaction.atomic():
        # Reverse all journals linked to this transaction
        # Find them via description pattern (journals created with TRX-PND prefix for this header)
        from apps.jurnal.models import JurnalHeader as JH, JurnalDetail as JD
        linked_journals = JH.objects.filter(
            nomor_transaksi__startswith='TRX-PND-J',
            uraian_transaksi__contains=header.transaction_id,
        )
        for jh in linked_journals:
            rev_nomor = _next_journal_number('TRX-PND-VD')
            rev = JH.objects.create(
                tanggal=timezone.now().date(),
                nomor_transaksi=rev_nomor,
                uraian_transaksi=f'Void {header.transaction_id}',
                entitas_bisnis=jh.entitas_bisnis,
                is_penyesuaian=True,
            )
            JD.objects.bulk_create([
                JD(jurnal_header=rev, akun=d.akun, debit=d.kredit, kredit=d.debit)
                for d in jh.details.all()
            ])

        # Cancel linked piutang (if not yet paid)
        for ph in header.piutang_headers.filter(status__in=('open', 'draft')):
            ph.status = 'cancelled'
            ph.save(update_fields=['status'])

        # Reverse pending deferred entries
        try:
            from .deferred_services import reverse_deferred_entry
            for eb_group in header.entitas_groups.prefetch_related('items').all():
                for item in eb_group.items.filter(is_deferred=True):
                    if hasattr(item, 'deferred_schedule'):
                        for entry in item.deferred_schedule.entries.filter(status='pending'):
                            reverse_deferred_entry(entry, user)
        except ImportError:
            pass

        header.status = 'voided'
        header.save(update_fields=['status'])
        _log_event(header, 'VOIDED', actor=user)


def _create_pendapatan_journals(header: PendapatanHeader, user=None):
    from apps.jurnal.models import JurnalHeader as JH, JurnalDetail as JD

    for eb_group in header.entitas_groups.select_related('entitas_bisnis', 'payment_account').prefetch_related('items').all():
        nomor = _next_journal_number('TRX-PND-J')
        jh = JH.objects.create(
            tanggal=header.tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Pendapatan {header.transaction_id} — {eb_group.entitas_bisnis.nama}',
            entitas_bisnis=eb_group.entitas_bisnis,
            is_penyesuaian=False,
        )
        entries = []
        for item in eb_group.items.select_related(
            'revenue_account', 'payment_account', 'tax_account', 'tax_payment_account',
            'deferred_account',
        ).all():
            # Determine payment account (item-level overrides EB-level)
            pay_acct = item.payment_account or eb_group.payment_account

            # Determine credit account — revenue or deferred
            cr_acct = item.deferred_account if item.is_deferred and item.deferred_account else item.revenue_account

            amount = item.jumlah_bruto
            entries.append(JD(jurnal_header=jh, akun=pay_acct, debit=amount, kredit=Decimal('0')))
            entries.append(JD(jurnal_header=jh, akun=cr_acct, debit=Decimal('0'), kredit=amount))

            # Tax lines
            if item.tax and item.tax_account:
                entries.append(JD(jurnal_header=jh, akun=pay_acct, debit=item.tax, kredit=Decimal('0')))
                entries.append(JD(jurnal_header=jh, akun=item.tax_account, debit=Decimal('0'), kredit=item.tax))
                if item.tax_payment == 'belum_transfer' and item.tax_payment_account:
                    entries.append(JD(jurnal_header=jh, akun=item.tax_account, debit=item.tax, kredit=Decimal('0')))
                    entries.append(JD(jurnal_header=jh, akun=item.tax_payment_account, debit=Decimal('0'), kredit=item.tax))

        JD.objects.bulk_create(entries)
        _log_event(header, 'JOURNAL_CREATED', description=jh.nomor_transaksi, actor=user)
```

- [ ] **Step 4: Implement create_piutang_from_pendapatan stub**

In `apps/piutang/services.py`, replace the `NotImplementedError` stub:

```python
def create_piutang_from_pendapatan(pendapatan_header, user=None) -> PiutangHeader:
    from decimal import Decimal

    total = Decimal('0')
    details = []
    for eb_group in pendapatan_header.entitas_groups.prefetch_related('items__revenue_account').all():
        for item in eb_group.items.all():
            total += item.jumlah_bruto
            details.append({
                'deskripsi': item.deskripsi_item[:255],
                'jumlah': item.jumlah_bruto,
                'revenue_account': item.revenue_account,
            })

    if total <= 0:
        raise ValueError('Total pendapatan kredit harus lebih besar dari 0.')

    coa_piutang = (
        pendapatan_header.entitas_groups.first().payment_account
        if pendapatan_header.entitas_groups.exists()
        else None
    )
    if not coa_piutang:
        raise ValueError('Payment account (akun piutang) diperlukan pada PendapatanEntitasBisnis.')

    eb = pendapatan_header.entitas_groups.first().entitas_bisnis if pendapatan_header.entitas_groups.exists() else None

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=pendapatan_header.tanggal,
            entitas_bisnis=eb,
            debitur=str(eb) if eb else '',
            deskripsi=f'Piutang dari Pendapatan {pendapatan_header.transaction_id}',
            source_type='from_pendapatan',
            source_pendapatan=pendapatan_header,
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

- [ ] **Step 5: Run tests**

```bash
python manage.py test apps.pendapatan.tests -v 2
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/pendapatan/services.py apps/pendapatan/tests.py apps/piutang/services.py
git commit -m "feat(pendapatan): add services — create_pendapatan_header, confirm, void, journals"
```

---

## Task 4: Admin + API endpoint

**Files:**
- Create: `apps/pendapatan/admin.py`
- Create partial: `apps/pendapatan/views.py` (API only)
- Create partial: `apps/pendapatan/urls.py`

- [ ] **Step 1: Write admin.py**

```python
# apps/pendapatan/admin.py
from django.contrib import admin
from .models import PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog


class PendapatanEBInline(admin.TabularInline):
    model = PendapatanEntitasBisnis
    extra = 0


class PendapatanEventLogInline(admin.TabularInline):
    model = PendapatanEventLog
    extra = 0
    readonly_fields = ('event_type', 'description', 'actor', 'timestamp')


@admin.register(PendapatanHeader)
class PendapatanHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'payment_type', 'status', 'source_type')
    list_filter = ('status', 'payment_type', 'source_type')
    search_fields = ('transaction_id', 'deskripsi')
    readonly_fields = ('transaction_id', 'created_at', 'updated_at')
    inlines = [PendapatanEBInline, PendapatanEventLogInline]
```

- [ ] **Step 2: Write STT defaults API**

```python
# apps/pendapatan/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages as dj_messages


@login_required
def stt_defaults(request: HttpRequest) -> JsonResponse:
    from apps.purchase.models import SubTransactionType
    stt_id = request.GET.get('stt_id')
    if not stt_id:
        return JsonResponse({'error': 'stt_id required'}, status=400)
    try:
        stt = SubTransactionType.objects.select_related(
            'default_offset_account'
        ).get(pk=stt_id, module='pendapatan')
    except SubTransactionType.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({
        'revenue_account_id': stt.default_offset_account_id,
        'revenue_account_nama': str(stt.default_offset_account) if stt.default_offset_account else '',
    })
```

- [ ] **Step 3: Write minimal urls.py with API endpoint**

```python
# apps/pendapatan/urls.py
from django.urls import path
from . import views

app_name = 'pendapatan'

urlpatterns = [
    path('api/stt-defaults/', views.stt_defaults, name='stt_defaults'),
]
```

- [ ] **Step 4: Run check**

```bash
python manage.py check
```

Expected: no issues.

- [ ] **Step 5: Commit**

```bash
git add apps/pendapatan/admin.py apps/pendapatan/views.py apps/pendapatan/urls.py
git commit -m "feat(pendapatan): add admin and STT defaults API"
```

---

## Task 5: Forms

**Files:**
- Create: `apps/pendapatan/forms.py`

- [ ] **Step 1: Write forms.py**

```python
# apps/pendapatan/forms.py
from django import forms
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType
from .models import PendapatanHeader


class PendapatanHeaderForm(forms.ModelForm):
    class Meta:
        model = PendapatanHeader
        fields = ['tanggal', 'deskripsi', 'payment_type']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'payment_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_payment_type'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False


class PendapatanItemForm(forms.Form):
    deskripsi_item = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Deskripsi item'}),
    )
    kategori = forms.ChoiceField(
        choices=[('', '— Pilih Kategori —')] + list(
            [('sewa', 'Sewa'), ('jasa', 'Jasa'), ('bunga', 'Bunga'), ('dividen', 'Dividen'),
             ('komisi', 'Komisi'), ('royalti', 'Royalti'), ('management_fee', 'Management Fee'),
             ('penjualan_aset', 'Penjualan Aset'), ('lainnya', 'Lainnya')]
        ),
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    sub_transaction_type = forms.ModelChoiceField(
        queryset=SubTransactionType.objects.filter(module='pendapatan').order_by('nama'),
        widget=forms.Select(attrs={'class': 'ni-input stt-select'}),
        empty_label='— Pilih STT —',
    )
    jumlah_bruto = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
    )
    revenue_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input revenue-account-field'}),
        empty_label='— Pilih Akun Pendapatan —',
    )
    payment_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='aset').order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Akun Kas/Bank (opsional) —',
    )
    # Deferred fields (shown only when is_deferred=True)
    is_deferred = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'ni-checkbox deferred-toggle'}),
        label='Pendapatan Diterima di Muka',
    )
    deferred_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
        empty_label='— Akun Deferred (Liability) —',
    )
    recognition_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
        empty_label='— Akun Pengakuan (Revenue) —',
    )
    deferred_tanggal_mulai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input deferred-field', 'type': 'date'}),
    )
    deferred_tanggal_selesai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input deferred-field', 'type': 'date'}),
    )
    deferred_metode = forms.ChoiceField(
        choices=[('straight_line', 'Garis Lurus'), ('custom', 'Custom')],
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_deferred'):
            required_fields = ['deferred_account', 'recognition_account',
                               'deferred_tanggal_mulai', 'deferred_tanggal_selesai']
            for f in required_fields:
                if not cleaned.get(f):
                    self.add_error(f, 'Field ini wajib diisi untuk item deferred.')
        return cleaned
```

- [ ] **Step 2: Commit**

```bash
git add apps/pendapatan/forms.py
git commit -m "feat(pendapatan): add forms"
```

---

## Task 6: Full views + URLs + templates

**Files:**
- Modify: `apps/pendapatan/views.py`
- Modify: `apps/pendapatan/urls.py`
- Create: `templates/pendapatan/dashboard.html`
- Create: `templates/pendapatan/list.html`
- Create: `templates/pendapatan/form.html`
- Create: `templates/pendapatan/detail.html`

- [ ] **Step 1: Complete views.py**

Append to `apps/pendapatan/views.py`:

```python
from django.utils import timezone
from .models import PendapatanHeader, PendapatanEventLog
from .services import confirm_pendapatan, create_pendapatan_header, void_pendapatan
from .forms import PendapatanHeaderForm, PendapatanItemForm


@login_required
def pendapatan_dashboard(request: HttpRequest) -> HttpResponse:
    from .services import get_pendapatan_dashboard_kpi
    kpi = get_pendapatan_dashboard_kpi()
    return render(request, 'pendapatan/dashboard.html', {'kpi': kpi})


@login_required
def pendapatan_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q
    qs = PendapatanHeader.objects.order_by('-tanggal', '-created_at')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(transaction_id__icontains=search) | Q(deskripsi__icontains=search))
    return render(request, 'pendapatan/list.html', {
        'pendapatans': list(qs),
        'status_filter': status_filter, 'search': search,
        'status_choices': PendapatanHeader.STATUS_CHOICES,
    })


@login_required
def pendapatan_create(request: HttpRequest) -> HttpResponse:
    from apps.entitas_bisnis.models import EntitasBisnis
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    if request.method == 'POST':
        form = PendapatanHeaderForm(request.POST)
        item_forms = [PendapatanItemForm(request.POST, prefix=f'item_{i}')
                      for i in range(int(request.POST.get('item_count', 1)))]
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None
        if form.is_valid() and all(f.is_valid() for f in item_forms):
            cd = form.cleaned_data
            items = [f.cleaned_data for f in item_forms]
            try:
                eb = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
                pay_acct = items[0].get('payment_account')
                header = create_pendapatan_header(
                    tanggal=cd['tanggal'], deskripsi=cd.get('deskripsi', ''),
                    payment_type=cd['payment_type'],
                    entitas_bisnis=eb, payment_account=pay_acct,
                    items=items, user=request.user,
                )
                dj_messages.success(request, f'Pendapatan {header.transaction_id} berhasil dibuat.')
                return redirect('pendapatan:detail', pk=header.pk)
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        form = PendapatanHeaderForm()
        item_forms = [PendapatanItemForm(prefix='item_0')]
    return render(request, 'pendapatan/form.html', {
        'form': form, 'item_forms': item_forms, 'mode': 'create',
        'eb_options': _get_eb_dropdown_options(),
    })


@login_required
def pendapatan_detail(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(
        PendapatanHeader.objects
        .prefetch_related('entitas_groups__items', 'event_logs__actor'),
        pk=pk,
    )
    return render(request, 'pendapatan/detail.html', {'header': header})


@login_required
def pendapatan_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            confirm_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} berhasil dikonfirmasi.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)


@login_required
def pendapatan_void(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            void_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} dibatalkan.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)
```

Also add to `services.py`:

```python
def get_pendapatan_dashboard_kpi() -> dict:
    from decimal import Decimal
    from django.db.models import Sum
    today = timezone.now().date()
    month_start = today.replace(day=1)
    prev_month_end = month_start.replace(day=1)
    import calendar
    prev_month_start = (month_start.replace(day=1) - timezone.timedelta(days=1)).replace(day=1)

    current_month = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__tanggal__gte=month_start,
                pendapatan_eb__pendapatan_header__status='confirmed')
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )
    prev_month = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__tanggal__gte=prev_month_start,
                pendapatan_eb__pendapatan_header__tanggal__lt=month_start,
                pendapatan_eb__pendapatan_header__status='confirmed')
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )
    cash_month = (
        PendapatanItem.objects
        .filter(pendapatan_eb__pendapatan_header__tanggal__gte=month_start,
                pendapatan_eb__pendapatan_header__status='confirmed',
                pendapatan_eb__pendapatan_header__payment_type='cash')
        .aggregate(s=Sum('jumlah_bruto'))['s'] or Decimal('0')
    )
    credit_month = current_month - cash_month
    return {
        'total_bulan_ini': current_month,
        'total_bulan_lalu': prev_month,
        'cash_bulan_ini': cash_month,
        'credit_bulan_ini': credit_month,
    }
```

- [ ] **Step 2: Complete urls.py**

```python
# apps/pendapatan/urls.py
from django.urls import path
from . import views

app_name = 'pendapatan'

urlpatterns = [
    path('', views.pendapatan_dashboard, name='dashboard'),
    path('list/', views.pendapatan_list, name='list'),
    path('create/', views.pendapatan_create, name='create'),
    path('<int:pk>/', views.pendapatan_detail, name='detail'),
    path('<int:pk>/confirm/', views.pendapatan_confirm, name='confirm'),
    path('<int:pk>/void/', views.pendapatan_void, name='void'),
    path('api/stt-defaults/', views.stt_defaults, name='stt_defaults'),
]
```

- [ ] **Step 3: Create templates**

```bash
mkdir -p templates/pendapatan
```

Create `templates/pendapatan/dashboard.html` — extend base template, show 4 KPI cards using `kpi` context.

Create `templates/pendapatan/list.html` — table of pendapatan with columns: ID Transaksi, Tanggal, Payment Type, Status, Actions. Filter bar: status + search.

Create `templates/pendapatan/form.html` — header form + dynamic item rows (JS to add/remove item forms). Item rows use `PendapatanItemForm` fields. `is_deferred` checkbox shows/hides deferred fields via JS. STT `change` event calls `/pendapatan/api/stt-defaults/?stt_id=X` and auto-fills `revenue_account`.

Create `templates/pendapatan/detail.html` — show header fields, EB groups + items table, event log timeline, confirm/void buttons.

- [ ] **Step 4: Smoke test**

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/pendapatan/`. Confirm dashboard loads. Create a cash transaction and confirm it. Verify journal created in admin.

- [ ] **Step 5: Commit**

```bash
git add apps/pendapatan/views.py apps/pendapatan/urls.py templates/pendapatan/
git commit -m "feat(pendapatan): add views, urls, and templates"
```

---

## Task 7: Full test run

- [ ] **Step 1: Run all pendapatan + piutang tests**

```bash
python manage.py test apps.pendapatan apps.piutang apps.sales -v 2
```

Expected: all PASS, 0 failures.

- [ ] **Step 2: Full project check**

```bash
python manage.py check && python manage.py test --failfast 2>&1 | tail -5
```
