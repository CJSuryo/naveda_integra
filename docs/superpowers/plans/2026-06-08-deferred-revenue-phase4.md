# Deferred Revenue — Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `DeferredRevenueSchedule` and `DeferredRevenueEntry` models to `apps/pendapatan/`, implement period-by-period revenue recognition, and provide a management command for batch recognition.

**Architecture:** Deferred items already have all required fields stored on `PendapatanItem` (set during Phase 3 form). `confirm_pendapatan` already calls `create_deferred_schedule` via try/import. This phase implements `deferred_services.py` so those calls succeed.

**Tech Stack:** Django, `dateutil.relativedelta` for month iteration, `django.core.management.BaseCommand`.

**Spec:** `docs/superpowers/specs/2026-06-07-deferred-revenue-design.md`

**Prerequisite:** Phase 3 (Pendapatan Core) complete.

---

## File Map

| Action | File |
|---|---|
| Create | `apps/pendapatan/deferred_services.py` |
| Modify | `apps/pendapatan/models.py` (add 2 models) |
| Create | `apps/pendapatan/tests_deferred.py` |
| Create | `apps/pendapatan/management/__init__.py` |
| Create | `apps/pendapatan/management/commands/__init__.py` |
| Create | `apps/pendapatan/management/commands/recognize_deferred_entries.py` |
| Modify | `apps/pendapatan/views.py` (add deferred views) |
| Modify | `apps/pendapatan/urls.py` (add deferred URLs) |
| Create | `templates/pendapatan/deferred_list.html` |
| Create | `templates/pendapatan/deferred_detail.html` |

---

## Task 1: Add DeferredRevenueSchedule + DeferredRevenueEntry models

**Files:**
- Modify: `apps/pendapatan/models.py`

- [ ] **Step 1: Add models at bottom of models.py**

```python
# Append to apps/pendapatan/models.py

class DeferredRevenueSchedule(models.Model):
    pendapatan_item = models.OneToOneField(
        PendapatanItem, on_delete=models.CASCADE, related_name='deferred_schedule',
        verbose_name='Pendapatan Item',
    )
    jumlah_total = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Total')
    tanggal_mulai = models.DateField(verbose_name='Tanggal Mulai')
    tanggal_selesai = models.DateField(verbose_name='Tanggal Selesai')
    metode = models.CharField(
        max_length=20, choices=DEFERRED_METODE_CHOICES, default='straight_line',
        verbose_name='Metode',
    )
    recognition_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='deferred_recognition', verbose_name='Akun Pengakuan',
    )
    deferred_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='deferred_liability', verbose_name='Akun Deferred (Liability)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Jadwal Deferred Revenue'
        verbose_name_plural = 'Jadwal Deferred Revenue'

    def __str__(self) -> str:
        return f'Deferred {self.pendapatan_item.pk} — {self.tanggal_mulai} s/d {self.tanggal_selesai}'

    @property
    def total_recognized(self):
        from decimal import Decimal
        from django.db.models import Sum
        return self.entries.filter(status='recognized').aggregate(s=Sum('jumlah'))['s'] or Decimal('0')

    @property
    def total_remaining(self):
        return self.jumlah_total - self.total_recognized


class DeferredRevenueEntry(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Belum Diakui'),
        ('recognized', 'Sudah Diakui'),
        ('reversed', 'Dibalik'),
    ]

    schedule = models.ForeignKey(
        DeferredRevenueSchedule, on_delete=models.CASCADE, related_name='entries',
        verbose_name='Jadwal',
    )
    periode = models.DateField(verbose_name='Periode (1 = bulan)')
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Status',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deferred_entries', verbose_name='Jurnal',
    )

    class Meta:
        verbose_name = 'Entry Deferred Revenue'
        verbose_name_plural = 'Entry Deferred Revenue'
        unique_together = ('schedule', 'periode')
        ordering = ['periode']

    def __str__(self) -> str:
        return f'{self.schedule.pk} — {self.periode.strftime("%Y-%m")} — {self.status}'
```

- [ ] **Step 2: Run makemigrations**

```bash
python manage.py makemigrations pendapatan --name deferred_revenue_models
python manage.py migrate pendapatan
```

Expected: `Applying pendapatan.0002_deferred_revenue_models... OK`

- [ ] **Step 3: Commit**

```bash
git add apps/pendapatan/models.py apps/pendapatan/migrations/
git commit -m "feat(pendapatan): add DeferredRevenueSchedule and DeferredRevenueEntry models"
```

---

## Task 2: deferred_services.py — create_deferred_schedule

**Files:**
- Create: `apps/pendapatan/deferred_services.py`
- Create: `apps/pendapatan/tests_deferred.py`

- [ ] **Step 1: Write failing tests**

```python
# apps/pendapatan/tests_deferred.py
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType

from .models import (
    PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem,
    DeferredRevenueSchedule, DeferredRevenueEntry,
)
from .deferred_services import create_deferred_schedule, recognize_deferred_entry


def make_deferred_item():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT X', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1')
    coa_deferred = Akun.objects.create(kategori_id='kewajiban', nama='Pendapatan Diterima di Muka', kode_akun='2.5.1')
    stt = SubTransactionType.objects.create(
        nama='Sewa', module='pendapatan', direction='inflow', default_offset_account=coa_revenue,
    )
    header = PendapatanHeader.objects.create(tanggal=date(2026, 1, 1), payment_type='cash', status='draft')
    eb_group = PendapatanEntitasBisnis.objects.create(
        pendapatan_header=header, entitas_bisnis=eb, payment_account=coa_kas,
    )
    item = PendapatanItem.objects.create(
        pendapatan_eb=eb_group,
        deskripsi_item='Sewa 3 bulan',
        kategori='sewa',
        sub_transaction_type=stt,
        jumlah_bruto=Decimal('3000000'),
        revenue_account=coa_revenue,
        payment_account=coa_kas,
        is_deferred=True,
        deferred_account=coa_deferred,
        recognition_account=coa_revenue,
        deferred_tanggal_mulai=date(2026, 1, 1),
        deferred_tanggal_selesai=date(2026, 3, 31),
        deferred_metode='straight_line',
    )
    return item, coa_deferred, coa_revenue


class CreateDeferredScheduleTests(TestCase):
    def setUp(self):
        self.item, self.coa_deferred, self.coa_revenue = make_deferred_item()

    def test_creates_schedule(self):
        schedule = create_deferred_schedule(self.item)
        self.assertIsNotNone(schedule.pk)
        self.assertEqual(schedule.jumlah_total, Decimal('3000000'))

    def test_creates_3_entries_for_3_months(self):
        schedule = create_deferred_schedule(self.item)
        self.assertEqual(schedule.entries.count(), 3)

    def test_straight_line_equal_amounts(self):
        schedule = create_deferred_schedule(self.item)
        amounts = list(schedule.entries.values_list('jumlah', flat=True))
        self.assertEqual(amounts[0], amounts[1])

    def test_total_entries_equal_jumlah_total(self):
        schedule = create_deferred_schedule(self.item)
        total = sum(schedule.entries.values_list('jumlah', flat=True))
        self.assertEqual(total, Decimal('3000000'))

    def test_all_entries_pending(self):
        schedule = create_deferred_schedule(self.item)
        self.assertEqual(schedule.entries.filter(status='pending').count(), 3)

    def test_periode_keys_are_first_of_month(self):
        schedule = create_deferred_schedule(self.item)
        periodes = list(schedule.entries.values_list('periode', flat=True).order_by('periode'))
        self.assertEqual(periodes[0].day, 1)
        self.assertEqual(periodes[0].month, 1)
        self.assertEqual(periodes[1].month, 2)
        self.assertEqual(periodes[2].month, 3)


class RecognizeDeferredEntryTests(TestCase):
    def setUp(self):
        self.item, self.coa_deferred, self.coa_revenue = make_deferred_item()
        self.schedule = create_deferred_schedule(self.item)
        self.entry = self.schedule.entries.order_by('periode').first()

    def test_entry_status_becomes_recognized(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'recognized')

    def test_generates_journal(self):
        from apps.jurnal.models import JurnalHeader
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.jurnal_header)

    def test_journal_dr_deferred_cr_recognition(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        details = self.entry.jurnal_header.details.all()
        dr = next(d for d in details if d.debit > 0)
        cr = next(d for d in details if d.kredit > 0)
        self.assertEqual(dr.akun, self.coa_deferred)
        self.assertEqual(cr.akun, self.coa_revenue)

    def test_raises_if_already_recognized(self):
        recognize_deferred_entry(self.entry)
        self.entry.refresh_from_db()
        with self.assertRaises(ValueError):
            recognize_deferred_entry(self.entry)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test apps.pendapatan.tests_deferred -v 2
```

Expected: ImportError — `deferred_services` not found.

- [ ] **Step 3: Implement deferred_services.py**

```python
# apps/pendapatan/deferred_services.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import DeferredRevenueEntry, DeferredRevenueSchedule, PendapatanItem


def _iter_months(start: date, end: date):
    """Yield the 1st of each month from start through end (inclusive)."""
    current = start.replace(day=1)
    end_key = end.replace(day=1)
    while current <= end_key:
        yield current
        # Advance one month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def create_deferred_schedule(item: PendapatanItem) -> DeferredRevenueSchedule:
    if not item.is_deferred:
        raise ValueError('Item bukan deferred revenue.')
    if not item.deferred_tanggal_mulai or not item.deferred_tanggal_selesai:
        raise ValueError('Tanggal mulai dan selesai deferred harus diisi.')
    if not item.deferred_account or not item.recognition_account:
        raise ValueError('Akun deferred dan akun pengakuan harus diisi.')

    periods = list(_iter_months(item.deferred_tanggal_mulai, item.deferred_tanggal_selesai))
    if not periods:
        raise ValueError('Tidak ada periode yang valid antara tanggal mulai dan selesai.')

    n = len(periods)
    jumlah_total = item.jumlah_bruto
    metode = item.deferred_metode or 'straight_line'

    with transaction.atomic():
        schedule = DeferredRevenueSchedule.objects.create(
            pendapatan_item=item,
            jumlah_total=jumlah_total,
            tanggal_mulai=item.deferred_tanggal_mulai,
            tanggal_selesai=item.deferred_tanggal_selesai,
            metode=metode,
            recognition_account=item.recognition_account,
            deferred_account=item.deferred_account,
        )

        if metode == 'straight_line':
            base = (jumlah_total / n).quantize(Decimal('0.01'))
            remainder = jumlah_total - base * (n - 1)
            entries = [
                DeferredRevenueEntry(
                    schedule=schedule,
                    periode=p,
                    jumlah=remainder if i == n - 1 else base,
                    status='pending',
                )
                for i, p in enumerate(periods)
            ]
        else:
            # custom: create all entries with jumlah=0, user fills manually
            entries = [
                DeferredRevenueEntry(schedule=schedule, periode=p, jumlah=Decimal('0'), status='pending')
                for p in periods
            ]

        DeferredRevenueEntry.objects.bulk_create(entries)
    return schedule


def recognize_deferred_entry(entry: DeferredRevenueEntry, user=None) -> JurnalHeader:
    if entry.status != 'pending':
        raise ValueError(f'Entry status harus pending, bukan {entry.status}.')

    with transaction.atomic():
        from apps.pendapatan.services import _next_journal_number
        nomor = _next_journal_number('TRX-PND-DR')
        header = JurnalHeader.objects.create(
            tanggal=timezone.now().date(),
            nomor_transaksi=nomor,
            uraian_transaksi=(
                f'Pengakuan Deferred Revenue — '
                f'{entry.schedule.pendapatan_item.pendapatan_eb.pendapatan_header.transaction_id} '
                f'Periode {entry.periode.strftime("%Y-%m")}'
            ),
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=entry.schedule.deferred_account,
                debit=entry.jumlah,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=entry.schedule.recognition_account,
                debit=Decimal('0'),
                kredit=entry.jumlah,
            ),
        ])
        entry.status = 'recognized'
        entry.jurnal_header = header
        entry.save(update_fields=['status', 'jurnal_header'])
    return header


def reverse_deferred_entry(entry: DeferredRevenueEntry, user=None):
    if entry.status == 'pending':
        entry.status = 'reversed'
        entry.save(update_fields=['status'])
    # recognized entries are not reversed here — require manual adjustment journal
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.pendapatan.tests_deferred -v 2
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/pendapatan/deferred_services.py apps/pendapatan/tests_deferred.py
git commit -m "feat(pendapatan): add deferred revenue services — schedule creation and period recognition"
```

---

## Task 3: Management command

**Files:**
- Create: `apps/pendapatan/management/__init__.py`
- Create: `apps/pendapatan/management/commands/__init__.py`
- Create: `apps/pendapatan/management/commands/recognize_deferred_entries.py`

- [ ] **Step 1: Create management directory**

```bash
mkdir -p apps/pendapatan/management/commands
touch apps/pendapatan/management/__init__.py
touch apps/pendapatan/management/commands/__init__.py
```

- [ ] **Step 2: Write management command**

```python
# apps/pendapatan/management/commands/recognize_deferred_entries.py
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.pendapatan.deferred_services import recognize_deferred_entry
from apps.pendapatan.models import DeferredRevenueEntry


class Command(BaseCommand):
    help = 'Recognize all pending deferred revenue entries for a given period (YYYY-MM).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--period', type=str, required=True,
            help='Period in YYYY-MM format (e.g. 2026-01)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print entries that would be recognized without saving.',
        )

    def handle(self, *args, **options):
        period_str = options['period']
        try:
            year, month = period_str.split('-')
            period_date = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            raise CommandError(f'Format periode tidak valid: {period_str}. Gunakan YYYY-MM.')

        entries = DeferredRevenueEntry.objects.filter(
            periode=period_date, status='pending',
        ).select_related(
            'schedule__recognition_account', 'schedule__deferred_account',
            'schedule__pendapatan_item__pendapatan_eb__pendapatan_header',
        )

        if not entries.exists():
            self.stdout.write(f'Tidak ada entry pending untuk periode {period_str}.')
            return

        ok = 0
        err = 0
        for entry in entries:
            if options['dry_run']:
                self.stdout.write(
                    f'[DRY-RUN] Entry {entry.pk} — {entry.jumlah} — '
                    f'{entry.schedule.pendapatan_item.pendapatan_eb.pendapatan_header.transaction_id}'
                )
                continue
            try:
                recognize_deferred_entry(entry)
                ok += 1
            except Exception as e:
                self.stderr.write(f'Error entry {entry.pk}: {e}')
                err += 1

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Selesai: {ok} diakui, {err} error.'))
```

- [ ] **Step 3: Test the command**

```bash
python manage.py recognize_deferred_entries --period 2026-01 --dry-run
```

Expected: prints `[DRY-RUN]` lines or "Tidak ada entry pending."

- [ ] **Step 4: Commit**

```bash
git add apps/pendapatan/management/
git commit -m "feat(pendapatan): add recognize_deferred_entries management command"
```

---

## Task 4: Deferred views + URLs + templates

**Files:**
- Modify: `apps/pendapatan/views.py`
- Modify: `apps/pendapatan/urls.py`
- Create: `templates/pendapatan/deferred_list.html`
- Create: `templates/pendapatan/deferred_detail.html`

- [ ] **Step 1: Add deferred views**

Append to `apps/pendapatan/views.py`:

```python
@login_required
def deferred_list(request: HttpRequest) -> HttpResponse:
    from .models import DeferredRevenueSchedule
    schedules = DeferredRevenueSchedule.objects.select_related(
        'pendapatan_item__pendapatan_eb__pendapatan_header',
        'recognition_account', 'deferred_account',
    ).order_by('-pendapatan_item__pendapatan_eb__pendapatan_header__tanggal')
    return render(request, 'pendapatan/deferred_list.html', {'schedules': schedules})


@login_required
def deferred_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from .models import DeferredRevenueSchedule
    schedule = get_object_or_404(
        DeferredRevenueSchedule.objects.select_related(
            'recognition_account', 'deferred_account',
        ).prefetch_related('entries__jurnal_header'),
        pk=pk,
    )
    return render(request, 'pendapatan/deferred_detail.html', {'schedule': schedule})


@login_required
def deferred_recognize(request: HttpRequest, entry_pk: int) -> HttpResponse:
    from .models import DeferredRevenueEntry
    from .deferred_services import recognize_deferred_entry
    entry = get_object_or_404(DeferredRevenueEntry, pk=entry_pk)
    if request.method == 'POST':
        try:
            recognize_deferred_entry(entry, user=request.user)
            dj_messages.success(request, f'Periode {entry.periode.strftime("%Y-%m")} berhasil diakui.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:deferred_detail', pk=entry.schedule_id)
```

- [ ] **Step 2: Add deferred URLs**

In `apps/pendapatan/urls.py`, add:

```python
path('deferred/', views.deferred_list, name='deferred_list'),
path('deferred/<int:pk>/', views.deferred_detail, name='deferred_detail'),
path('deferred/entry/<int:entry_pk>/recognize/', views.deferred_recognize, name='deferred_recognize'),
```

- [ ] **Step 3: Create templates**

`templates/pendapatan/deferred_list.html` — table of schedules: Transaction ID, Tanggal Mulai, Tanggal Selesai, Jumlah Total, Recognized, Remaining, link to detail.

`templates/pendapatan/deferred_detail.html` — schedule info + table of entries with periode, jumlah, status, jurnal link. Pending entries have a "Akui" button that POSTs to `deferred_recognize`.

- [ ] **Step 4: Smoke test**

```bash
python manage.py runserver
```

Create a pendapatan with `is_deferred=True` item and confirm it. Visit `/pendapatan/deferred/` — schedule should appear. Click into schedule detail. Recognize one entry.

- [ ] **Step 5: Commit**

```bash
git add apps/pendapatan/views.py apps/pendapatan/urls.py templates/pendapatan/deferred_list.html templates/pendapatan/deferred_detail.html
git commit -m "feat(pendapatan): add deferred revenue views and templates"
```

---

## Task 5: Full test run

- [ ] **Step 1: Run all deferred tests**

```bash
python manage.py test apps.pendapatan.tests apps.pendapatan.tests_deferred -v 2
```

Expected: all PASS.

- [ ] **Step 2: Full project check**

```bash
python manage.py check && python manage.py test --failfast 2>&1 | tail -5
```
