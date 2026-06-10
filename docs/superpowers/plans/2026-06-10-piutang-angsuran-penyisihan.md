# Piutang: Angsuran Jangka Panjang + Aging Fix + Penyisihan Piutang — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add installment schedule to long-term piutang (mirror utang module), fix aging to per-installment-row with 7 buckets, and add configurable allowance-for-doubtful-accounts with per-piutang manual and batch delta-adjustment journal modes.

**Architecture:** Schedule computed on-the-fly from `PiutangHeader` fields — no persisted rows. `get_piutang_aging()` expanded to iterate installment rows. `PenyisihanRateConfig` holds configurable rates per bucket. `PiutangPenyisihan` records each journal. Batch mode computes `target − saldo_existing` delta to avoid double-counting; `is_specifically_impaired` flag excludes manually-provisioned piutang from batch.

**Tech Stack:** Django 4.x, Python 3.11+, PostgreSQL, django.forms.modelformset_factory

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `apps/piutang/models.py` | Modify + extend | Add 4 fields to PiutangHeader; new PenyisihanRateConfig, PiutangPenyisihan models |
| `apps/piutang/migrations/0004_piutang_angsuran_fields.py` | Create | AddField migration |
| `apps/piutang/migrations/0005_piutang_penyisihan_models.py` | Create | CreateModel migration |
| `apps/piutang/migrations/0006_seed_penyisihan_rates.py` | Create | Data migration: seed 7 default rates |
| `apps/piutang/services.py` | Modify | Add schedule helpers, refactor aging, add penyisihan functions |
| `apps/piutang/forms.py` | Modify | Add bunga/angsuran fields; new PiutangPenyisihanForm, BatchPenyisihanForm, PenyisihanRateConfigFormSet |
| `apps/piutang/views.py` | Modify | Update create/update/detail; add 4 new views |
| `apps/piutang/urls.py` | Modify | Add 4 new URL patterns |
| `apps/piutang/tests.py` | Modify | Tests for schedule, aging, penyisihan service functions |
| `templates/piutang/form.html` | Modify | Add bunga/angsuran section with JS show/hide |
| `templates/piutang/detail.html` | Modify | Add angsuran table card + penyisihan card + penyisihan modal |
| `templates/piutang/report_aging.html` | Rewrite | Per-row detail table with 7 buckets + penyisihan estimate |
| `templates/piutang/report_penyisihan.html` | Create | Batch preview + form + history |
| `templates/piutang/settings_rates.html` | Create | Edit PenyisihanRateConfig formset |
| `templates/piutang/dashboard.html` | Modify | Show aging_summary + piutang_neto from KPI |

---

## Task 1: Add fields to PiutangHeader + migration 0004

**Files:**
- Modify: `apps/piutang/models.py`
- Create: `apps/piutang/migrations/0004_piutang_angsuran_fields.py`

- [ ] **Step 1: Add choice constants and fields to models.py**

In `apps/piutang/models.py`, after the existing `METODE_PENERIMAAN_CHOICES` constant block, add:

```python
JENIS_BUNGA_CHOICES = [
    ('tanpa_bunga', 'Tanpa Bunga'),
    ('flat', 'Flat'),
    ('anuitas', 'Anuitas (Efektif)'),
]

PERIODE_ANGSURAN_CHOICES = [
    ('bulanan', 'Bulanan'),
    ('triwulanan', 'Triwulanan (3 Bulan)'),
    ('semesteran', 'Semesteran (6 Bulan)'),
    ('tahunan', 'Tahunan'),
]
```

Inside `PiutangHeader`, after the `is_locked` field, add:

```python
jenis_bunga = models.CharField(
    max_length=20, choices=JENIS_BUNGA_CHOICES, default='tanpa_bunga',
    verbose_name='Jenis Bunga',
)
suku_bunga = models.DecimalField(
    max_digits=8, decimal_places=4, default=0,
    verbose_name='Suku Bunga (% per tahun)',
)
periode_angsuran = models.CharField(
    max_length=20, choices=PERIODE_ANGSURAN_CHOICES, default='bulanan',
    verbose_name='Periode Angsuran',
)
is_specifically_impaired = models.BooleanField(
    default=False, verbose_name='Sudah Disisihkan Khusus',
)
```

- [ ] **Step 2: Generate migration**

```bash
python manage.py makemigrations piutang --name piutang_angsuran_fields
```

Expected: creates `apps/piutang/migrations/0004_piutang_angsuran_fields.py`

- [ ] **Step 3: Apply migration**

```bash
python manage.py migrate piutang
```

Expected: OK

- [ ] **Step 4: Commit**

```bash
git add apps/piutang/models.py apps/piutang/migrations/0004_piutang_angsuran_fields.py
git commit -m "feat(piutang): add jenis_bunga, suku_bunga, periode_angsuran, is_specifically_impaired to PiutangHeader"
```

---

## Task 2: PenyisihanRateConfig + PiutangPenyisihan models + migrations 0005 + 0006

**Files:**
- Modify: `apps/piutang/models.py`
- Create: `apps/piutang/migrations/0005_piutang_penyisihan_models.py`
- Create: `apps/piutang/migrations/0006_seed_penyisihan_rates.py`

- [ ] **Step 1: Add PenyisihanRateConfig model to models.py**

At the end of `apps/piutang/models.py`, append:

```python
class PenyisihanRateConfig(models.Model):
    BUCKET_KEY_CHOICES = [
        ('current', 'Belum Jatuh Tempo'),
        ('1_30', 'Lewat 1–30 Hari'),
        ('31_60', 'Lewat 31–60 Hari'),
        ('61_90', 'Lewat 61–90 Hari'),
        ('91_180', 'Lewat 91–180 Hari'),
        ('181_365', 'Lewat 181–365 Hari'),
        ('over_365', 'Lewat > 365 Hari'),
    ]

    bucket_key = models.CharField(
        max_length=20, unique=True, choices=BUCKET_KEY_CHOICES, verbose_name='Bucket',
    )
    label = models.CharField(max_length=100, verbose_name='Label')
    rate_percent = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name='Rate Penyisihan (%)',
    )
    urutan = models.PositiveSmallIntegerField(default=0, verbose_name='Urutan')

    class Meta:
        verbose_name = 'Rate Penyisihan Piutang'
        verbose_name_plural = 'Rate Penyisihan Piutang'
        ordering = ['urutan']

    def __str__(self) -> str:
        return f'{self.label} — {self.rate_percent}%'


class PiutangPenyisihan(models.Model):
    JENIS_CHOICES = [
        ('manual', 'Manual (Per-Piutang)'),
        ('batch', 'Batch Akhir Periode'),
    ]

    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='penyisihan_entries',
        verbose_name='Piutang Header',
    )
    tanggal = models.DateField(verbose_name='Tanggal')
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES, verbose_name='Jenis')
    jumlah = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Jumlah',
        help_text='Positif = beban penyisihan, negatif = pemulihan',
    )
    allowance_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_penyisihan_allowance', verbose_name='Akun Cadangan',
    )
    expense_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_penyisihan_expense', verbose_name='Akun Beban',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_penyisihan', verbose_name='Jurnal',
    )
    catatan = models.CharField(max_length=512, blank=True, default='', verbose_name='Catatan')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_penyisihan_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Penyisihan Piutang'
        verbose_name_plural = 'Penyisihan Piutang'
        ordering = ['-tanggal', '-created_at']

    def __str__(self) -> str:
        return f'Penyisihan {self.jenis} — {self.tanggal} — {self.jumlah}'
```

Also add `'PENYISIHAN'` to `PiutangAuditLog.ACTION_CHOICES`:

```python
('PENYISIHAN', 'Penyisihan Piutang'),
```

- [ ] **Step 2: Generate schema migration**

```bash
python manage.py makemigrations piutang --name piutang_penyisihan_models
```

Expected: creates `0005_piutang_penyisihan_models.py`

- [ ] **Step 3: Create data migration for seed rates**

```bash
python manage.py makemigrations piutang --empty --name seed_penyisihan_rates
```

Edit `apps/piutang/migrations/0006_seed_penyisihan_rates.py`:

```python
from django.db import migrations

DEFAULT_RATES = [
    ('current',  'Belum Jatuh Tempo',  '0.00',  1),
    ('1_30',     'Lewat 1–30 Hari',    '5.00',  2),
    ('31_60',    'Lewat 31–60 Hari',   '15.00', 3),
    ('61_90',    'Lewat 61–90 Hari',   '25.00', 4),
    ('91_180',   'Lewat 91–180 Hari',  '50.00', 5),
    ('181_365',  'Lewat 181–365 Hari', '75.00', 6),
    ('over_365', 'Lewat > 365 Hari',   '100.00', 7),
]


def seed_rates(apps, schema_editor):
    PenyisihanRateConfig = apps.get_model('piutang', 'PenyisihanRateConfig')
    for key, label, rate, urutan in DEFAULT_RATES:
        PenyisihanRateConfig.objects.get_or_create(
            bucket_key=key,
            defaults={'label': label, 'rate_percent': rate, 'urutan': urutan},
        )


def reverse_seed(apps, schema_editor):
    PenyisihanRateConfig = apps.get_model('piutang', 'PenyisihanRateConfig')
    PenyisihanRateConfig.objects.filter(
        bucket_key__in=[r[0] for r in DEFAULT_RATES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('piutang', '0005_piutang_penyisihan_models'),
    ]
    operations = [
        migrations.RunPython(seed_rates, reverse_seed),
    ]
```

- [ ] **Step 4: Apply migrations**

```bash
python manage.py migrate piutang
```

Expected: OK — 7 PenyisihanRateConfig rows created.

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/models.py apps/piutang/migrations/0005_piutang_penyisihan_models.py apps/piutang/migrations/0006_seed_penyisihan_rates.py
git commit -m "feat(piutang): add PenyisihanRateConfig and PiutangPenyisihan models with default rates"
```

---

## Task 3: Service helpers + compute_angsuran_schedule()

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

In `apps/piutang/tests.py`, add:

```python
import calendar
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.piutang.services import _add_months, compute_angsuran_schedule
from apps.piutang.models import PiutangHeader


class AddMonthsTest(TestCase):
    def test_simple(self):
        assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_year_rollover(self):
        assert _add_months(date(2025, 11, 30), 3) == date(2026, 2, 28)


class ComputeAngsuranScheduleTest(TestCase):
    def _make_piutang(self, jumlah_pokok, jenis_bunga='tanpa_bunga', suku_bunga=0,
                      periode='bulanan', tanggal=None, jatuh_tempo=None):
        from apps.master_data.models import Akun
        from apps.accounts.models import User
        akun, _ = Akun.objects.get_or_create(
            kode_akun='1100', defaults={'nama': 'Piutang Usaha', 'kategori_id': 'aset'}
        )
        return PiutangHeader(
            nomor_piutang='TEST-001',
            tanggal=tanggal or date(2026, 1, 1),
            jatuh_tempo=jatuh_tempo or date(2026, 12, 31),
            jumlah_pokok=Decimal(str(jumlah_pokok)),
            jumlah_terbayar=Decimal('0'),
            jenis_jangka_waktu='long_term',
            jenis_bunga=jenis_bunga,
            suku_bunga=Decimal(str(suku_bunga)),
            periode_angsuran=periode,
            coa_piutang_account=akun,
            status='open',
        )

    def test_tanpa_bunga_12_bulan(self):
        p = self._make_piutang(12_000_000, tanggal=date(2026, 1, 1), jatuh_tempo=date(2026, 12, 31))
        rows = compute_angsuran_schedule(p)
        assert len(rows) == 11  # 11 monthly periods from Jan to Dec
        assert all(r['bunga'] == 0 for r in rows)
        total_pokok = sum(r['pokok'] for r in rows)
        assert total_pokok == Decimal('12000000')

    def test_no_schedule_without_jatuh_tempo(self):
        p = self._make_piutang(1_000_000, jatuh_tempo=None)
        p.jatuh_tempo = None
        assert compute_angsuran_schedule(p) == []

    def test_flat_interest(self):
        p = self._make_piutang(
            12_000_000, jenis_bunga='flat', suku_bunga=12,
            tanggal=date(2026, 1, 1), jatuh_tempo=date(2026, 12, 31),
        )
        rows = compute_angsuran_schedule(p)
        assert all(r['bunga'] > 0 for r in rows)

    def test_status_akan_datang(self):
        future = date.today().replace(year=date.today().year + 1)
        p = self._make_piutang(
            6_000_000, tanggal=date.today(), jatuh_tempo=future,
        )
        rows = compute_angsuran_schedule(p)
        assert all(r['status'] == 'akan_datang' for r in rows)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python manage.py test apps.piutang.tests.AddMonthsTest apps.piutang.tests.ComputeAngsuranScheduleTest -v 2
```

Expected: ImportError or AttributeError — `_add_months` and `compute_angsuran_schedule` not yet defined.

- [ ] **Step 3: Add helpers and compute_angsuran_schedule to services.py**

At the top of `apps/piutang/services.py`, add import:

```python
import calendar
from datetime import date
```

After the existing imports and before `_log()`, add:

```python
_PERIODE_MONTHS_MAP = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6, 'tahunan': 12}


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def compute_angsuran_schedule(piutang) -> list:
    """Returns installment schedule for a PiutangHeader. Empty list if no jatuh_tempo."""
    if not piutang.jatuh_tempo:
        return []
    periode_months = _PERIODE_MONTHS_MAP.get(piutang.periode_angsuran, 1)
    total_months = (
        (piutang.jatuh_tempo.year - piutang.tanggal.year) * 12
        + (piutang.jatuh_tempo.month - piutang.tanggal.month)
    )
    if total_months <= 0:
        return []
    n = max(1, round(total_months / periode_months))
    total = float(piutang.jumlah_pokok)
    jenis = piutang.jenis_bunga
    r = float(piutang.suku_bunga) / 100 / 12 * periode_months if jenis != 'tanpa_bunga' else 0.0

    rows = []
    sisa = total
    if jenis == 'anuitas' and r > 0:
        pmt = total * r / (1 - (1 + r) ** (-n))
        for i in range(n):
            bunga_i = sisa * r
            pokok_i = pmt - bunga_i
            if i == n - 1:
                pokok_i = sisa
            angsuran_i = pokok_i + bunga_i
            sisa -= pokok_i
            rows.append({
                'no': i + 1,
                'tanggal': _add_months(piutang.tanggal, (i + 1) * periode_months),
                'pokok': Decimal(str(round(pokok_i, 0))),
                'bunga': Decimal(str(round(bunga_i, 0))),
                'angsuran': Decimal(str(round(angsuran_i, 0))),
                'sisa_pokok': Decimal(str(round(max(0.0, sisa), 0))),
            })
    else:
        pk_unit = round(total / n, 0)
        bng_unit = round(total * r, 0) if jenis == 'flat' else 0.0
        cumulative_pk = 0.0
        for i in range(n):
            pk_i = round(total - cumulative_pk, 0) if i == n - 1 else pk_unit
            cumulative_pk += pk_i
            sisa -= pk_i
            ang_i = pk_i + bng_unit
            rows.append({
                'no': i + 1,
                'tanggal': _add_months(piutang.tanggal, (i + 1) * periode_months),
                'pokok': Decimal(str(int(pk_i))),
                'bunga': Decimal(str(int(bng_unit))),
                'angsuran': Decimal(str(int(ang_i))),
                'sisa_pokok': Decimal(str(int(round(max(0.0, sisa), 0)))),
            })

    # Payment matching: direct via angsuran_no; unallocated pool fills in order
    direct_paid: dict[int, float] = {}
    unallocated = 0.0
    for p in piutang.penerimaan.all():
        if p.angsuran_no:
            direct_paid[p.angsuran_no] = direct_paid.get(p.angsuran_no, 0.0) + float(p.jumlah_diterima)
        else:
            unallocated += float(p.jumlah_diterima)

    today = date.today()
    for row in rows:
        ang = float(row['angsuran'])
        no = row['no']
        paid = direct_paid.get(no, 0.0)
        if paid < ang - 1.0 and unallocated > 0:
            apply = min(unallocated, max(0.0, ang - paid))
            paid += apply
            unallocated = max(0.0, unallocated - apply)
        row['paid'] = Decimal(str(round(paid, 0)))
        row['sisa_bayar'] = Decimal(str(round(max(0.0, ang - paid), 0)))
        if paid >= ang - 1.0:
            row['status'] = 'lunas'
            row['sisa_bayar'] = Decimal('0')
        elif paid > 1.0:
            row['status'] = 'sebagian'
        elif row['tanggal'] < today:
            row['status'] = 'jatuh_tempo'
        else:
            row['status'] = 'akan_datang'
    return rows
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.AddMonthsTest apps.piutang.tests.ComputeAngsuranScheduleTest -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add compute_angsuran_schedule and _add_months helpers"
```

---

## Task 4: Refactor get_piutang_aging() — per-installment-row, 7 buckets

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

In `apps/piutang/tests.py`, add:

```python
from apps.piutang.services import _classify_bucket, get_piutang_aging


class ClassifyBucketTest(TestCase):
    def test_future(self):
        future = date(date.today().year + 1, 1, 1)
        assert _classify_bucket(future, date.today()) == 'current'

    def test_today(self):
        assert _classify_bucket(date.today(), date.today()) == 'current'

    def test_1_day_overdue(self):
        from datetime import timedelta
        assert _classify_bucket(date.today() - timedelta(days=1), date.today()) == '1_30'

    def test_31_days(self):
        from datetime import timedelta
        assert _classify_bucket(date.today() - timedelta(days=31), date.today()) == '31_60'

    def test_over_365(self):
        from datetime import timedelta
        assert _classify_bucket(date.today() - timedelta(days=400), date.today()) == 'over_365'

    def test_none_returns_current(self):
        assert _classify_bucket(None, date.today()) == 'current'


class GetPiutangAgingTest(TestCase):
    def test_returns_7_buckets(self):
        result = get_piutang_aging()
        expected_keys = {'current', '1_30', '31_60', '61_90', '91_180', '181_365', 'over_365'}
        assert set(result.keys()) == expected_keys

    def test_each_bucket_is_list(self):
        result = get_piutang_aging()
        for v in result.values():
            assert isinstance(v, list)
```

- [ ] **Step 2: Run to verify fail**

```bash
python manage.py test apps.piutang.tests.ClassifyBucketTest apps.piutang.tests.GetPiutangAgingTest -v 2
```

Expected: ImportError — `_classify_bucket` not defined.

- [ ] **Step 3: Add _classify_bucket and refactor get_piutang_aging in services.py**

Replace the existing `get_piutang_aging()` function with:

```python
_AGING_BUCKET_KEYS = ['current', '1_30', '31_60', '61_90', '91_180', '181_365', 'over_365']
_AGING_BUCKET_LABELS = {
    'current':  'Belum Jatuh Tempo',
    '1_30':     'Lewat 1–30 Hari',
    '31_60':    'Lewat 31–60 Hari',
    '61_90':    'Lewat 61–90 Hari',
    '91_180':   'Lewat 91–180 Hari',
    '181_365':  'Lewat 181–365 Hari',
    'over_365': 'Lewat > 365 Hari',
}


def _classify_bucket(tanggal, today) -> str:
    if tanggal is None:
        return 'current'
    delta = (today - tanggal).days
    if delta <= 0:
        return 'current'
    elif delta <= 30:
        return '1_30'
    elif delta <= 60:
        return '31_60'
    elif delta <= 90:
        return '61_90'
    elif delta <= 180:
        return '91_180'
    elif delta <= 365:
        return '181_365'
    else:
        return 'over_365'


def get_piutang_aging() -> dict:
    today = timezone.now().date()
    buckets = {k: [] for k in _AGING_BUCKET_KEYS}
    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .select_related('entitas_bisnis')
        .prefetch_related('penerimaan')
    )
    for piutang in qs:
        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            schedule = compute_angsuran_schedule(piutang)
            if schedule:
                for row in schedule:
                    if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                        key = _classify_bucket(row['tanggal'], today)
                        buckets[key].append({
                            'piutang': piutang,
                            'angsuran_no': row['no'],
                            'tanggal_angsuran': row['tanggal'],
                            'jumlah': row['sisa_bayar'],
                            'hari_lewat': max(0, (today - row['tanggal']).days),
                        })
                continue
        key = _classify_bucket(piutang.jatuh_tempo, today)
        buckets[key].append({
            'piutang': piutang,
            'angsuran_no': None,
            'tanggal_angsuran': piutang.jatuh_tempo,
            'jumlah': piutang.sisa_piutang,
            'hari_lewat': max(0, (today - piutang.jatuh_tempo).days) if piutang.jatuh_tempo else 0,
        })
    return buckets
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.ClassifyBucketTest apps.piutang.tests.GetPiutangAgingTest -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): refactor get_piutang_aging to per-installment-row 7-bucket aging"
```

---

## Task 5: compute_penyisihan_for_piutang()

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing test**

```python
from apps.piutang.services import compute_penyisihan_for_piutang
from apps.piutang.models import PenyisihanRateConfig


class ComputePenyisihanForPiutangTest(TestCase):
    def setUp(self):
        # Ensure rate config exists (seeded by migration, but add manually for tests)
        defaults = [
            ('current', 'Belum Jatuh Tempo', '0.00', 1),
            ('1_30', 'Lewat 1–30 Hari', '5.00', 2),
            ('31_60', 'Lewat 31–60 Hari', '15.00', 3),
            ('61_90', 'Lewat 61–90 Hari', '25.00', 4),
            ('91_180', 'Lewat 91–180 Hari', '50.00', 5),
            ('181_365', 'Lewat 181–365 Hari', '75.00', 6),
            ('over_365', 'Lewat > 365 Hari', '100.00', 7),
        ]
        for key, label, rate, urutan in defaults:
            PenyisihanRateConfig.objects.get_or_create(
                bucket_key=key, defaults={'label': label, 'rate_percent': rate, 'urutan': urutan}
            )

    def _make_piutang_db(self, jumlah_pokok, jatuh_tempo_delta_days):
        from datetime import timedelta
        from apps.master_data.models import Akun
        akun, _ = Akun.objects.get_or_create(
            kode_akun='1100', defaults={'nama': 'Piutang Usaha', 'kategori_id': 'aset'}
        )
        p = PiutangHeader.objects.create(
            tanggal=date.today(),
            jatuh_tempo=date.today() - timedelta(days=jatuh_tempo_delta_days),
            jumlah_pokok=Decimal(str(jumlah_pokok)),
            jumlah_terbayar=Decimal('0'),
            jenis_jangka_waktu='short_term',
            coa_piutang_account=akun,
            status='open',
        )
        return p

    def test_short_term_overdue_31_days(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=31)
        result = compute_penyisihan_for_piutang(p)
        assert result['total_penyisihan'] == Decimal('150000.00')  # 15% of 1_000_000

    def test_current_has_zero_penyisihan(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=-30)  # future
        result = compute_penyisihan_for_piutang(p)
        assert result['total_penyisihan'] == Decimal('0.00')

    def test_breakdown_has_7_entries(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=10)
        result = compute_penyisihan_for_piutang(p)
        assert len(result['breakdown']) == 7
```

- [ ] **Step 2: Run to verify fail**

```bash
python manage.py test apps.piutang.tests.ComputePenyisihanForPiutangTest -v 2
```

Expected: ImportError or AttributeError.

- [ ] **Step 3: Add compute_penyisihan_for_piutang to services.py**

Add after `get_piutang_aging()`:

```python
def _get_rate_config() -> dict:
    from .models import PenyisihanRateConfig
    return {r.bucket_key: r.rate_percent for r in PenyisihanRateConfig.objects.all()}


def compute_penyisihan_for_piutang(piutang) -> dict:
    rates = _get_rate_config()
    today = timezone.now().date()
    bucket_amounts = {k: Decimal('0') for k in _AGING_BUCKET_KEYS}

    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        schedule = compute_angsuran_schedule(piutang)
        if schedule:
            for row in schedule:
                if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                    key = _classify_bucket(row['tanggal'], today)
                    bucket_amounts[key] += row['sisa_bayar']
        else:
            key = _classify_bucket(piutang.jatuh_tempo, today)
            bucket_amounts[key] += piutang.sisa_piutang
    else:
        key = _classify_bucket(piutang.jatuh_tempo, today)
        bucket_amounts[key] += piutang.sisa_piutang

    breakdown = []
    total = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        amt = bucket_amounts[key]
        rate = rates.get(key, Decimal('0'))
        penyisihan = (amt * rate / 100).quantize(Decimal('0.01'))
        total += penyisihan
        breakdown.append({
            'bucket_key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'jumlah_piutang': amt,
            'rate': rate,
            'penyisihan': penyisihan,
        })
    return {'total_penyisihan': total, 'breakdown': breakdown}
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.ComputePenyisihanForPiutangTest -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add compute_penyisihan_for_piutang service function"
```

---

## Task 6: create_penyisihan_journal() + reverse_penyisihan_journal()

**Files:**
- Modify: `apps/piutang/services.py`

- [ ] **Step 1: Add journal number helper and create/reverse functions**

In `apps/piutang/services.py`, add after `compute_penyisihan_for_piutang()`:

```python
def _next_penyisihan_journal_number(prefix='TRX-PIU-PSH') -> str:
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


def create_penyisihan_journal(
    piutang, allowance_account, expense_account, tanggal, catatan='', user=None
):
    from .models import PiutangPenyisihan
    result = compute_penyisihan_for_piutang(piutang)
    total = result['total_penyisihan']
    if total <= 0:
        raise ValueError('Tidak ada penyisihan yang dapat dihitung untuk piutang ini.')
    with transaction.atomic():
        piutang = PiutangHeader.objects.select_for_update().get(pk=piutang.pk)
        nomor = _next_penyisihan_journal_number('TRX-PIU-PSH')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyisihan Piutang {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=expense_account, debit=total, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=allowance_account, debit=Decimal('0'), kredit=total),
        ])
        entry = PiutangPenyisihan.objects.create(
            piutang_header=piutang,
            tanggal=tanggal,
            jenis='manual',
            jumlah=total,
            allowance_account=allowance_account,
            expense_account=expense_account,
            jurnal_header=header,
            catatan=catatan,
            created_by=user,
        )
        piutang.is_specifically_impaired = True
        piutang.save(update_fields=['is_specifically_impaired'])
        _log(piutang, 'PENYISIHAN', user=user, after={'jumlah': str(total), 'nomor': nomor})
    return entry


def reverse_penyisihan_journal(entry, user=None) -> None:
    from .models import PiutangPenyisihan
    piutang = entry.piutang_header
    with transaction.atomic():
        if entry.jurnal_header_id:
            orig = entry.jurnal_header
            nomor = _next_penyisihan_journal_number('TRX-PIU-PSHR')
            rev = JurnalHeader.objects.create(
                tanggal=timezone.now().date(),
                nomor_transaksi=nomor,
                uraian_transaksi=f'Reversal Penyisihan {piutang.nomor_piutang if piutang else ""}',
                entitas_bisnis=piutang.entitas_bisnis if piutang else None,
                is_penyesuaian=True,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=rev, akun=d.akun, debit=d.kredit, kredit=d.debit)
                for d in orig.details.all()
            ])
        entry.delete()
        if piutang:
            remaining = PiutangPenyisihan.objects.filter(
                piutang_header=piutang, jenis='manual'
            ).exists()
            if not remaining:
                piutang.is_specifically_impaired = False
                piutang.save(update_fields=['is_specifically_impaired'])
            _log(piutang, 'PENYISIHAN', user=user, notes='Jurnal penyisihan dibatalkan')
```

- [ ] **Step 2: Run existing tests to ensure no regression**

```bash
python manage.py test apps.piutang -v 2
```

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add apps/piutang/services.py
git commit -m "feat(piutang): add create_penyisihan_journal and reverse_penyisihan_journal"
```

---

## Task 7: compute_batch_penyisihan() + create_batch_penyisihan_journal()

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing test**

```python
from apps.piutang.services import compute_batch_penyisihan


class ComputeBatchPenyisihanTest(TestCase):
    def setUp(self):
        from apps.piutang.models import PenyisihanRateConfig
        defaults = [
            ('current', 'Belum JT', '0.00', 1), ('1_30', '1-30', '5.00', 2),
            ('31_60', '31-60', '15.00', 3), ('61_90', '61-90', '25.00', 4),
            ('91_180', '91-180', '50.00', 5), ('181_365', '181-365', '75.00', 6),
            ('over_365', '>365', '100.00', 7),
        ]
        for key, label, rate, urutan in defaults:
            PenyisihanRateConfig.objects.get_or_create(
                bucket_key=key, defaults={'label': label, 'rate_percent': rate, 'urutan': urutan}
            )

    def test_returns_required_keys(self):
        from apps.master_data.models import Akun
        akun, _ = Akun.objects.get_or_create(
            kode_akun='2200', defaults={'nama': 'Cad Kerugian Piutang', 'kategori_id': 'kewajiban'}
        )
        result = compute_batch_penyisihan(date.today(), akun)
        assert 'target_saldo' in result
        assert 'saldo_existing' in result
        assert 'delta' in result
        assert 'breakdown' in result
        assert 'piutang_count' in result

    def test_delta_equals_target_minus_existing(self):
        from apps.master_data.models import Akun
        akun, _ = Akun.objects.get_or_create(
            kode_akun='2200', defaults={'nama': 'Cad Kerugian Piutang', 'kategori_id': 'kewajiban'}
        )
        result = compute_batch_penyisihan(date.today(), akun)
        assert result['delta'] == result['target_saldo'] - result['saldo_existing']
```

- [ ] **Step 2: Run to verify fail**

```bash
python manage.py test apps.piutang.tests.ComputeBatchPenyisihanTest -v 2
```

Expected: ImportError.

- [ ] **Step 3: Add batch functions to services.py**

Add after `reverse_penyisihan_journal()`:

```python
def compute_batch_penyisihan(tanggal, allowance_account) -> dict:
    from .models import PenyisihanRateConfig
    from apps.jurnal.models import JurnalDetail as JD
    from django.db.models import Sum as DSum

    rates = {r.bucket_key: r.rate_percent for r in PenyisihanRateConfig.objects.all()}
    today = tanggal
    bucket_amounts = {k: Decimal('0') for k in _AGING_BUCKET_KEYS}
    piutang_count = 0

    qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'), is_specifically_impaired=False)
        .prefetch_related('penerimaan')
    )
    for piutang in qs:
        piutang_count += 1
        if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
            schedule = compute_angsuran_schedule(piutang)
            if schedule:
                for row in schedule:
                    if row['status'] != 'lunas' and row['sisa_bayar'] > 0:
                        key = _classify_bucket(row['tanggal'], today)
                        bucket_amounts[key] += row['sisa_bayar']
                continue
        key = _classify_bucket(piutang.jatuh_tempo, today)
        bucket_amounts[key] += piutang.sisa_piutang

    breakdown = []
    target_saldo = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        amt = bucket_amounts[key]
        rate = rates.get(key, Decimal('0'))
        penyisihan = (amt * rate / 100).quantize(Decimal('0.01'))
        target_saldo += penyisihan
        breakdown.append({
            'bucket_key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'jumlah_piutang': amt,
            'rate': rate,
            'penyisihan': penyisihan,
        })

    # Saldo existing akun cadangan: kontra-aset, normal balance kredit
    agg = (
        JD.objects
        .filter(akun=allowance_account, jurnal_header__tanggal__lte=tanggal)
        .aggregate(total_kredit=DSum('kredit'), total_debit=DSum('debit'))
    )
    saldo_existing = (
        (agg['total_kredit'] or Decimal('0')) - (agg['total_debit'] or Decimal('0'))
    ).quantize(Decimal('0.01'))

    delta = (target_saldo - saldo_existing).quantize(Decimal('0.01'))
    return {
        'target_saldo': target_saldo,
        'saldo_existing': saldo_existing,
        'delta': delta,
        'breakdown': breakdown,
        'piutang_count': piutang_count,
    }


def create_batch_penyisihan_journal(
    batch_data: dict, allowance_account, expense_account, tanggal, catatan='', user=None
):
    from .models import PiutangPenyisihan
    delta = batch_data['delta']
    if delta == 0:
        raise ValueError('Delta penyisihan adalah 0, tidak perlu jurnal.')
    with transaction.atomic():
        nomor = _next_penyisihan_journal_number('TRX-PIU-PSH-B')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyisihan Piutang Batch — {tanggal}',
            is_penyesuaian=True,
        )
        abs_delta = abs(delta)
        if delta > 0:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=expense_account, debit=abs_delta, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=allowance_account, debit=Decimal('0'), kredit=abs_delta),
            ])
        else:
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=allowance_account, debit=abs_delta, kredit=Decimal('0')),
                JurnalDetail(jurnal_header=header, akun=expense_account, debit=Decimal('0'), kredit=abs_delta),
            ])
        entry = PiutangPenyisihan.objects.create(
            piutang_header=None,
            tanggal=tanggal,
            jenis='batch',
            jumlah=delta,
            allowance_account=allowance_account,
            expense_account=expense_account,
            jurnal_header=header,
            catatan=catatan,
            created_by=user,
        )
    return entry
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.ComputeBatchPenyisihanTest -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add compute_batch_penyisihan and create_batch_penyisihan_journal"
```

---

## Task 8: Update get_piutang_dashboard_kpi() + create_manual_piutang()

**Files:**
- Modify: `apps/piutang/services.py`

- [ ] **Step 1: Update get_piutang_dashboard_kpi() in services.py**

Replace the existing `get_piutang_dashboard_kpi()` function with:

```python
def get_piutang_dashboard_kpi() -> dict:
    today = timezone.now().date()
    month_start = today.replace(day=1)
    outstanding_qs = PiutangHeader.objects.filter(status__in=('open', 'partial', 'overdue'))
    total_outstanding = outstanding_qs.aggregate(s=Sum('jumlah_pokok'))['s'] or Decimal('0')
    total_terbayar = outstanding_qs.aggregate(s=Sum('jumlah_terbayar'))['s'] or Decimal('0')
    total_outstanding -= total_terbayar

    overdue_qs = outstanding_qs.filter(jatuh_tempo__lt=today)
    total_overdue = sum(p.sisa_piutang for p in overdue_qs)

    collected_this_month = (
        PiutangPenerimaan.objects
        .filter(tanggal_terima__gte=month_start)
        .aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
    )
    collection_rate = (
        collected_this_month / (collected_this_month + total_outstanding) * 100
        if (collected_this_month + total_outstanding) > 0 else Decimal('0')
    )

    # Compute aging summary for dashboard (calls get_piutang_aging once)
    aging_buckets = get_piutang_aging()
    rates = _get_rate_config()
    aging_summary = {}
    total_penyisihan_target = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        total_amt = sum(entry['jumlah'] for entry in aging_buckets[key])
        rate = rates.get(key, Decimal('0'))
        penyisihan = (Decimal(str(total_amt)) * rate / 100).quantize(Decimal('0.01'))
        total_penyisihan_target += penyisihan
        aging_summary[key] = {
            'label': _AGING_BUCKET_LABELS[key],
            'total_outstanding': Decimal(str(total_amt)),
            'rate': rate,
            'penyisihan': penyisihan,
        }
    piutang_neto = (total_outstanding - total_penyisihan_target).quantize(Decimal('0.01'))

    return {
        'total_outstanding': total_outstanding,
        'total_overdue': total_overdue,
        'collected_this_month': collected_this_month,
        'collection_rate': collection_rate.quantize(Decimal('0.01')),
        'total_penyisihan_target': total_penyisihan_target,
        'piutang_neto': piutang_neto,
        'aging_summary': aging_summary,
    }
```

- [ ] **Step 2: Update create_manual_piutang() signature**

Add 3 new keyword parameters to `create_manual_piutang()`:

```python
def create_manual_piutang(
    tanggal,
    entitas_bisnis,
    debitur: str,
    deskripsi: str,
    coa_piutang_account,
    jatuh_tempo,
    details: list,
    jenis_jangka_waktu: str = 'short_term',
    jenis_bunga: str = 'tanpa_bunga',
    suku_bunga: Decimal = Decimal('0'),
    periode_angsuran: str = 'bulanan',
    user=None,
) -> PiutangHeader:
```

Inside the function, in `PiutangHeader.objects.create(...)`, add:

```python
            jenis_bunga=jenis_bunga,
            suku_bunga=suku_bunga,
            periode_angsuran=periode_angsuran,
```

- [ ] **Step 3: Run all piutang tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add apps/piutang/services.py
git commit -m "feat(piutang): update dashboard KPI with aging_summary and piutang_neto; add bunga params to create_manual_piutang"
```

---

## Task 9: Update forms.py

**Files:**
- Modify: `apps/piutang/forms.py`

- [ ] **Step 1: Update PiutangHeaderForm and add new forms**

Replace the contents of `apps/piutang/forms.py` with:

```python
from django import forms
from django.forms import inlineformset_factory, modelformset_factory

from apps.master_data.models import Akun

from .models import (
    PiutangAttachment, PiutangDetail, PiutangHeader, PiutangPenerimaan,
    PenyisihanRateConfig,
)


class PiutangHeaderForm(forms.ModelForm):
    class Meta:
        model = PiutangHeader
        fields = [
            'tanggal', 'debitur', 'deskripsi', 'jatuh_tempo',
            'jenis_jangka_waktu', 'coa_piutang_account',
            'jenis_bunga', 'suku_bunga', 'periode_angsuran',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'debitur': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama debitur'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'jatuh_tempo': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jenis_jangka_waktu': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_jangka_waktu'}),
            'coa_piutang_account': forms.Select(attrs={'class': 'ni-input'}),
            'jenis_bunga': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_bunga'}),
            'suku_bunga': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'periode_angsuran': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['suku_bunga'].required = False
        self.fields['coa_piutang_account'].queryset = Akun.objects.filter(
            kategori_id='aset'
        ).order_by('kode_akun')
        self.fields['coa_piutang_account'].empty_label = '— Pilih Akun Piutang —'


class PiutangDetailForm(forms.ModelForm):
    class Meta:
        model = PiutangDetail
        fields = ['deskripsi', 'jumlah', 'revenue_account']
        widgets = {
            'deskripsi': forms.TextInput(attrs={'class': 'ni-input ni-input--sm', 'placeholder': 'Keterangan'}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input ni-input--sm amount-field', 'step': '0.01', 'min': '0.01'}),
            'revenue_account': forms.Select(attrs={'class': 'ni-input ni-input--sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revenue_account'].required = False
        self.fields['revenue_account'].queryset = Akun.objects.all().order_by('kode_akun')
        self.fields['revenue_account'].empty_label = '— Akun Pendapatan (opsional) —'


PiutangDetailFormSet = inlineformset_factory(
    PiutangHeader, PiutangDetail,
    form=PiutangDetailForm,
    fields=['deskripsi', 'jumlah', 'revenue_account'],
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


class PiutangPenerimaanForm(forms.ModelForm):
    class Meta:
        model = PiutangPenerimaan
        fields = ['tanggal_terima', 'jumlah_diterima', 'payment_account',
                  'metode_penerimaan', 'nomor_referensi', 'catatan']
        widgets = {
            'tanggal_terima': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jumlah_diterima': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'metode_penerimaan': forms.Select(attrs={'class': 'ni-input'}),
            'nomor_referensi': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'No. transfer / cek'}),
            'catatan': forms.TextInput(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, piutang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nomor_referensi'].required = False
        self.fields['catatan'].required = False
        self.fields['payment_account'].queryset = Akun.objects.filter(
            kategori_id='aset'
        ).order_by('kode_akun')
        self.fields['payment_account'].empty_label = '— Pilih Akun Kas/Bank —'


class PiutangAttachmentForm(forms.ModelForm):
    class Meta:
        model = PiutangAttachment
        fields = ['file', 'file_name', 'jenis_dokumen']
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'ni-input'}),
            'jenis_dokumen': forms.Select(attrs={'class': 'ni-input'}),
        }


class PiutangWriteOffForm(forms.Form):
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    metode = forms.ChoiceField(
        choices=[('langsung', 'Langsung'), ('cadangan', 'Cadangan Kerugian')],
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    bad_debt_account = forms.ModelChoiceField(
        queryset=Akun.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Piutang Tak Tertagih',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.all(), required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
    )
    alasan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
    )


class PiutangReklasifikasiForm(forms.Form):
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    dari_akun = forms.ModelChoiceField(
        queryset=Akun.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Dari Akun',
    )
    ke_akun = forms.ModelChoiceField(
        queryset=Akun.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Ke Akun',
    )
    jumlah = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
    )
    keterangan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
    )


class PiutangPenyisihanForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='kewajiban').order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
        empty_label='— Pilih Akun Cadangan —',
    )
    expense_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='beban').order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Penyisihan',
        empty_label='— Pilih Akun Beban —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Catatan (opsional)'}),
    )


class BatchPenyisihanForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Perhitungan',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='kewajiban').order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
        empty_label='— Pilih Akun Cadangan —',
    )
    expense_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='beban').order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Penyisihan',
        empty_label='— Pilih Akun Beban —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Catatan (opsional)'}),
    )


PenyisihanRateConfigFormSet = modelformset_factory(
    PenyisihanRateConfig,
    fields=['rate_percent'],
    extra=0,
    widgets={
        'rate_percent': forms.NumberInput(attrs={
            'class': 'ni-input ni-input--sm', 'step': '0.01', 'min': '0', 'max': '100',
        }),
    },
)
```

- [ ] **Step 2: Run tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: All PASS (forms don't break existing tests)

- [ ] **Step 3: Commit**

```bash
git add apps/piutang/forms.py
git commit -m "feat(piutang): add jenis_bunga/suku_bunga/periode_angsuran to PiutangHeaderForm; add PiutangPenyisihanForm, BatchPenyisihanForm, PenyisihanRateConfigFormSet"
```

---

## Task 10: Update piutang_create, piutang_update, piutang_detail views

**Files:**
- Modify: `apps/piutang/views.py`

- [ ] **Step 1: Update piutang_create view**

In `piutang_create`, inside the `if form.is_valid() and formset.is_valid():` block, update the `create_manual_piutang` call to pass new fields:

```python
                    piutang = create_manual_piutang(
                        tanggal=cd['tanggal'], entitas_bisnis=eb,
                        debitur=cd.get('debitur', ''), deskripsi=cd.get('deskripsi', ''),
                        coa_piutang_account=cd['coa_piutang_account'],
                        jatuh_tempo=cd.get('jatuh_tempo'),
                        details=details,
                        jenis_jangka_waktu=cd['jenis_jangka_waktu'],
                        jenis_bunga=cd.get('jenis_bunga', 'tanpa_bunga'),
                        suku_bunga=cd.get('suku_bunga') or Decimal('0'),
                        periode_angsuran=cd.get('periode_angsuran', 'bulanan'),
                        user=request.user,
                    )
```

Add `from decimal import Decimal` to the view imports if not already present (it is already imported at top of file).

- [ ] **Step 2: Update piutang_update view**

In `piutang_update`, inside the `if form.is_valid() and formset.is_valid():` block, after `formset.save()`, add saving bunga fields:

```python
            instance = form.save()
            formset.save()
            instance.entitas_bisnis = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
            instance.save(update_fields=['entitas_bisnis'])
```

This already calls `form.save()` which saves all form fields including the new ones — no additional change needed since `PiutangHeaderForm` now includes those fields.

- [ ] **Step 3: Update piutang_detail view**

Replace the `piutang_detail` function with:

```python
@login_required
def piutang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.master_data.models import Akun
    from .services import compute_angsuran_schedule, compute_penyisihan_for_piutang
    from .forms import PiutangPenyisihanForm
    from .models import PiutangPenyisihan

    piutang = get_object_or_404(
        PiutangHeader.objects
        .select_related('entitas_bisnis', 'coa_piutang_account', 'approved_by')
        .prefetch_related(
            'details', 'penerimaan__payment_account', 'penerimaan__jurnal_header',
            'attachments', 'audit_logs__user', 'reklasifikasi_entries__jurnal',
        ),
        pk=pk,
    )
    penerimaan_form = PiutangPenerimaanForm(piutang_header=piutang, initial={'tanggal_terima': piutang.tanggal})
    attachment_form = PiutangAttachmentForm()
    bagian_lancar = compute_bagian_lancar(piutang) if piutang.can_reklasifikasi else None
    akun_piutang_list = list(Akun.objects.filter(kategori_id='aset').order_by('kode_akun'))

    angsuran_schedule = []
    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        angsuran_schedule = compute_angsuran_schedule(piutang)

    penyisihan_preview = compute_penyisihan_for_piutang(piutang)
    penyisihan_form = PiutangPenyisihanForm(
        initial={'tanggal': timezone.now().date()}
    )
    penyisihan_history = (
        PiutangPenyisihan.objects
        .filter(piutang_header=piutang)
        .select_related('jurnal_header', 'allowance_account', 'expense_account', 'created_by')
        .order_by('-tanggal')
    )

    return render(request, 'piutang/detail.html', {
        'piutang': piutang,
        'penerimaan_form': penerimaan_form,
        'attachment_form': attachment_form,
        'bagian_lancar': bagian_lancar,
        'akun_piutang_list': akun_piutang_list,
        'write_off_form': PiutangWriteOffForm(initial={'tanggal': timezone.now().date()}),
        'reklasifikasi_form': PiutangReklasifikasiForm(initial={'tanggal': timezone.now().date()}),
        'angsuran_schedule': angsuran_schedule,
        'penyisihan_preview': penyisihan_preview,
        'penyisihan_form': penyisihan_form,
        'penyisihan_history': penyisihan_history,
    })
```

Also update the import at the top of views.py — add to existing imports:

```python
from .forms import (
    PiutangAttachmentForm, PiutangDetailFormSet, PiutangHeaderForm,
    PiutangPenerimaanForm, PiutangReklasifikasiForm, PiutangWriteOffForm,
    PiutangPenyisihanForm, BatchPenyisihanForm, PenyisihanRateConfigFormSet,
)
from .models import (
    PiutangAttachment, PiutangHeader, PiutangPenerimaan, PiutangReklasifikasi,
    PenyisihanRateConfig,
)
from .services import (
    compute_bagian_lancar,
    create_manual_piutang, create_piutang_payment,
    get_piutang_aging, get_piutang_dashboard_kpi,
    reverse_piutang_payment, write_off_piutang,
    compute_angsuran_schedule, compute_penyisihan_for_piutang,
    create_penyisihan_journal, reverse_penyisihan_journal,
    compute_batch_penyisihan, create_batch_penyisihan_journal,
)
```

Also update `piutang_dashboard` view to remove the separate `get_piutang_aging()` call (it's now inside KPI):

```python
@login_required
def piutang_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_piutang_dashboard_kpi()
    due_soon = list(
        PiutangHeader.objects
        .filter(status__in=('open', 'partial'), jatuh_tempo__lte=timezone.now().date())
        .order_by('jatuh_tempo')[:20]
    )
    return render(request, 'piutang/dashboard.html', {
        'kpi': kpi, 'due_soon': due_soon,
    })
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/views.py
git commit -m "feat(piutang): update piutang_detail with angsuran_schedule and penyisihan context; update create/update views for new fields"
```

---

## Task 11: Add new views + update URLs

**Files:**
- Modify: `apps/piutang/views.py`
- Modify: `apps/piutang/urls.py`

- [ ] **Step 1: Add 4 new views to views.py**

Append to `apps/piutang/views.py`:

```python
@login_required
def piutang_penyisihan_create(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        if piutang.is_specifically_impaired:
            dj_messages.error(request, 'Piutang ini sudah disisihkan secara khusus.')
            return redirect('piutang:detail', pk=pk)
        if piutang.status not in ('open', 'partial', 'overdue'):
            dj_messages.error(request, 'Penyisihan hanya bisa dibuat untuk piutang aktif.')
            return redirect('piutang:detail', pk=pk)
        form = PiutangPenyisihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                create_penyisihan_journal(
                    piutang=piutang,
                    allowance_account=cd['allowance_account'],
                    expense_account=cd['expense_account'],
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Jurnal penyisihan berhasil dibuat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_penyisihan_cancel(request: HttpRequest, pk: int, ppk: int) -> HttpResponse:
    from .models import PiutangPenyisihan
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    entry = get_object_or_404(PiutangPenyisihan, pk=ppk, piutang_header=piutang)
    if request.method == 'POST':
        try:
            reverse_penyisihan_journal(entry, user=request.user)
            dj_messages.success(request, 'Jurnal penyisihan berhasil dibatalkan.')
        except Exception as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_report_penyisihan(request: HttpRequest) -> HttpResponse:
    from .models import PiutangPenyisihan
    batch_preview = None
    form = BatchPenyisihanForm(initial={'tanggal': timezone.now().date()})
    history = (
        PiutangPenyisihan.objects
        .filter(jenis='batch')
        .select_related('jurnal_header', 'allowance_account', 'expense_account', 'created_by')
        .order_by('-tanggal')[:20]
    )

    if request.method == 'POST':
        action = request.POST.get('action', '')
        form = BatchPenyisihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if action == 'preview':
                batch_preview = compute_batch_penyisihan(cd['tanggal'], cd['allowance_account'])
            elif action == 'post':
                batch_data = compute_batch_penyisihan(cd['tanggal'], cd['allowance_account'])
                try:
                    create_batch_penyisihan_journal(
                        batch_data=batch_data,
                        allowance_account=cd['allowance_account'],
                        expense_account=cd['expense_account'],
                        tanggal=cd['tanggal'],
                        catatan=cd.get('catatan', ''),
                        user=request.user,
                    )
                    dj_messages.success(request, f'Jurnal penyisihan batch berhasil dibuat. Delta: {batch_data["delta"]}')
                    return redirect('piutang:report_penyisihan')
                except ValueError as exc:
                    dj_messages.error(request, str(exc))
                    batch_preview = batch_data

    return render(request, 'piutang/report_penyisihan.html', {
        'form': form, 'batch_preview': batch_preview, 'history': history,
    })


@login_required
def piutang_settings_rates(request: HttpRequest) -> HttpResponse:
    qs = PenyisihanRateConfig.objects.all().order_by('urutan')
    if request.method == 'POST':
        formset = PenyisihanRateConfigFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            dj_messages.success(request, 'Rate penyisihan berhasil disimpan.')
            return redirect('piutang:settings_rates')
        dj_messages.error(request, 'Terdapat kesalahan pada form.')
    else:
        formset = PenyisihanRateConfigFormSet(queryset=qs)
    return render(request, 'piutang/settings_rates.html', {'formset': formset, 'rates': qs})
```

- [ ] **Step 2: Update urls.py**

Replace `apps/piutang/urls.py` with:

```python
from django.urls import path
from . import views

app_name = 'piutang'

urlpatterns = [
    path('dashboard/', views.piutang_dashboard, name='dashboard'),
    path('', views.piutang_list, name='list'),
    path('create/', views.piutang_create, name='create'),
    path('<int:pk>/', views.piutang_detail, name='detail'),
    path('<int:pk>/edit/', views.piutang_update, name='update'),
    path('<int:pk>/delete/', views.piutang_delete, name='delete'),
    path('<int:pk>/terima/', views.piutang_terima, name='terima'),
    path('<int:pk>/penerimaan/<int:ppk>/cancel/', views.piutang_penerimaan_cancel, name='penerimaan_cancel'),
    path('<int:pk>/write-off/', views.piutang_write_off, name='write_off'),
    path('<int:pk>/reklasifikasi/', views.piutang_reklasifikasi_post, name='reklasifikasi_post'),
    path('<int:pk>/reklasifikasi/<int:rkl_pk>/reverse/', views.piutang_reklasifikasi_reverse, name='reklasifikasi_reverse'),
    path('<int:pk>/attachments/upload/', views.piutang_attachment_upload, name='attachment_upload'),
    path('<int:pk>/attachments/<int:apk>/delete/', views.piutang_attachment_delete, name='attachment_delete'),
    path('<int:pk>/penyisihan/', views.piutang_penyisihan_create, name='penyisihan_create'),
    path('<int:pk>/penyisihan/<int:ppk>/cancel/', views.piutang_penyisihan_cancel, name='penyisihan_cancel'),
    path('reports/aging/', views.piutang_report_aging, name='report_aging'),
    path('reports/subjek/', views.piutang_report_subjek, name='report_subjek'),
    path('reports/jatuh-tempo/', views.piutang_report_jatuh_tempo, name='report_jatuh_tempo'),
    path('reports/write-off/', views.piutang_report_write_off, name='report_write_off'),
    path('reports/penyisihan/', views.piutang_report_penyisihan, name='report_penyisihan'),
    path('settings/penyisihan-rates/', views.piutang_settings_rates, name='settings_rates'),
]
```

- [ ] **Step 3: Update piutang_report_aging view**

Replace the existing `piutang_report_aging` function:

```python
@login_required
def piutang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_piutang_aging()
    rates = {r.bucket_key: r.rate_percent for r in PenyisihanRateConfig.objects.all()}
    from .services import _AGING_BUCKET_KEYS, _AGING_BUCKET_LABELS
    bucket_summary = []
    grand_total_outstanding = Decimal('0')
    grand_total_penyisihan = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        entries = buckets[key]
        total = sum(e['jumlah'] for e in entries)
        rate = rates.get(key, Decimal('0'))
        penyisihan = (total * rate / 100).quantize(Decimal('0.01'))
        grand_total_outstanding += total
        grand_total_penyisihan += penyisihan
        bucket_summary.append({
            'key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'entries': entries,
            'total': total,
            'rate': rate,
            'penyisihan': penyisihan,
        })
    return render(request, 'piutang/report_aging.html', {
        'bucket_summary': bucket_summary,
        'grand_total_outstanding': grand_total_outstanding,
        'grand_total_penyisihan': grand_total_penyisihan,
    })
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/views.py apps/piutang/urls.py
git commit -m "feat(piutang): add penyisihan_create, penyisihan_cancel, report_penyisihan, settings_rates views and URLs"
```

---

## Task 12: Update piutang/form.html (bunga/angsuran section + JS)

**Files:**
- Modify: `templates/piutang/form.html`

- [ ] **Step 1: Add bunga/angsuran section to form.html**

After the closing `</div>` of the "Informasi Piutang" card body (before the "Detail Piutang" card), insert:

```html
  <div class="ni-card ni-animate-fade-in" id="bunga-angsuran-card" style="display:none">
    <div class="ni-card__header"><h2 class="ni-card__title">Bunga &amp; Angsuran</h2></div>
    <div class="ni-card__body">
      <div class="ni-form-grid ni-form-grid--3">
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.jenis_bunga.label }}</label>
          {{ form.jenis_bunga }}
          {% if form.jenis_bunga.errors %}<div class="ni-form-error">{{ form.jenis_bunga.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group" id="suku-bunga-group">
          <label class="ni-form-label">{{ form.suku_bunga.label }}</label>
          {{ form.suku_bunga }}
          {% if form.suku_bunga.errors %}<div class="ni-form-error">{{ form.suku_bunga.errors }}</div>{% endif %}
        </div>
        <div class="ni-form-group">
          <label class="ni-form-label">{{ form.periode_angsuran.label }}</label>
          {{ form.periode_angsuran }}
          {% if form.periode_angsuran.errors %}<div class="ni-form-error">{{ form.periode_angsuran.errors }}</div>{% endif %}
        </div>
      </div>
    </div>
  </div>
```

At the bottom of the `<script>` block, before the closing `})();`, add:

```javascript
  // ── Bunga & Angsuran show/hide ───────────────────────────────
  var jwtEl = document.getElementById('id_jenis_jangka_waktu');
  var bungaEl = document.getElementById('id_jenis_bunga');
  var bungaCard = document.getElementById('bunga-angsuran-card');
  var sukuBungaGroup = document.getElementById('suku-bunga-group');

  function toggleBungaCard() {
    if (jwtEl && jwtEl.value === 'long_term') {
      bungaCard.style.display = '';
    } else {
      bungaCard.style.display = 'none';
    }
  }

  function toggleSukuBunga() {
    if (bungaEl && bungaEl.value === 'tanpa_bunga') {
      sukuBungaGroup.style.display = 'none';
    } else {
      sukuBungaGroup.style.display = '';
    }
  }

  if (jwtEl) {
    jwtEl.addEventListener('change', function() { toggleBungaCard(); toggleSukuBunga(); });
    toggleBungaCard();
  }
  if (bungaEl) {
    bungaEl.addEventListener('change', toggleSukuBunga);
    toggleSukuBunga();
  }
```

- [ ] **Step 2: Commit**

```bash
git add templates/piutang/form.html
git commit -m "feat(piutang): add bunga/angsuran section to form.html with JS show/hide"
```

---

## Task 13: Update piutang/detail.html — angsuran table + penyisihan card

**Files:**
- Modify: `templates/piutang/detail.html`

- [ ] **Step 1: Add angsuran table card**

After the "Riwayat Penerimaan" card (after its closing `</div>`) and before the Write-Off card, insert:

```html
{% if angsuran_schedule %}
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header">
    <h2 class="ni-card__title">Tabel Angsuran</h2>
    <span class="ni-text-muted">{{ angsuran_schedule|length }} angsuran &mdash; {{ piutang.get_periode_angsuran_display }}</span>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>No</th><th>Tanggal</th>
          <th class="ni-text-right">Pokok</th>
          <th class="ni-text-right">Bunga</th>
          <th class="ni-text-right">Angsuran</th>
          <th class="ni-text-right">Sisa Pokok</th>
          <th class="ni-text-right">Dibayar</th>
          <th class="ni-text-right">Sisa Bayar</th>
          <th class="ni-text-center">Status</th>
        </tr>
      </thead>
      <tbody>
        {% for row in angsuran_schedule %}
        <tr class="{% if row.status == 'lunas' %}ni-row--success{% elif row.status == 'jatuh_tempo' %}ni-row--danger{% elif row.status == 'sebagian' %}ni-row--warning{% endif %}">
          <td>{{ row.no }}</td>
          <td>{{ row.tanggal }}</td>
          <td class="ni-text-right">{{ row.pokok|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.bunga|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.angsuran|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.sisa_pokok|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.paid|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ row.sisa_bayar|floatformat:0|intcomma }}</td>
          <td class="ni-text-center">
            {% if row.status == 'lunas' %}<span class="ni-badge ni-badge--success">Lunas</span>
            {% elif row.status == 'jatuh_tempo' %}<span class="ni-badge ni-badge--danger">Jatuh Tempo</span>
            {% elif row.status == 'sebagian' %}<span class="ni-badge ni-badge--warning">Sebagian</span>
            {% else %}<span class="ni-badge">Akan Datang</span>{% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: Add penyisihan card + modal**

After the angsuran card (or after the reklasifikasi card if no angsuran), before the Audit Log card, insert:

```html
{% if piutang.status in 'open,partial,overdue' %}
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header">
    <h2 class="ni-card__title">Penyisihan Piutang</h2>
    <div style="display:flex;align-items:center;gap:.5rem;">
      {% if piutang.is_specifically_impaired %}
        <span class="ni-badge ni-badge--warning">Sudah Disisihkan Khusus</span>
      {% else %}
        <button type="button" class="ni-btn ni-btn--sm ni-btn--primary" onclick="openModal('penyisihanModal')">+ Buat Jurnal Penyisihan</button>
      {% endif %}
    </div>
  </div>
  {% if penyisihan_preview.breakdown %}
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Bucket</th><th class="ni-text-right">Jumlah Piutang</th><th class="ni-text-right">Rate (%)</th><th class="ni-text-right">Estimasi Penyisihan</th></tr></thead>
      <tbody>
        {% for b in penyisihan_preview.breakdown %}
        {% if b.jumlah_piutang > 0 %}
        <tr>
          <td>{{ b.label }}</td>
          <td class="ni-text-right">{{ b.jumlah_piutang|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ b.rate }}%</td>
          <td class="ni-text-right">{{ b.penyisihan|floatformat:0|intcomma }}</td>
        </tr>
        {% endif %}
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="3"><strong>Total Estimasi Penyisihan</strong></td>
          <td class="ni-text-right"><strong>{{ penyisihan_preview.total_penyisihan|floatformat:0|intcomma }}</strong></td>
        </tr>
      </tfoot>
    </table>
  </div>
  {% endif %}
  {% if penyisihan_history %}
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Tanggal</th><th>Jenis</th><th class="ni-text-right">Jumlah</th><th>Jurnal</th><th>Dibuat Oleh</th><th></th></tr></thead>
      <tbody>
        {% for ps in penyisihan_history %}
        <tr>
          <td>{{ ps.tanggal }}</td>
          <td>{{ ps.get_jenis_display }}</td>
          <td class="ni-text-right">{{ ps.jumlah|floatformat:0|intcomma }}</td>
          <td>{% if ps.jurnal_header %}<a href="{% url 'jurnal:header_detail' ps.jurnal_header.pk %}">{{ ps.jurnal_header.nomor_transaksi }}</a>{% else %}-{% endif %}</td>
          <td>{{ ps.created_by|default:'-' }}</td>
          <td>
            <form method="post" action="{% url 'piutang:penyisihan_cancel' piutang.pk ps.pk %}" class="ni-form-inline">
              {% csrf_token %}
              <button type="submit" class="ni-btn ni-btn--xs ni-btn--danger" onclick="return confirm('Batalkan jurnal penyisihan ini?')">Batalkan</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
</div>
{% endif %}
```

- [ ] **Step 3: Add penyisihan modal**

Before the closing `</script>` tag, after the existing reklasifikasi modal, add:

```html
{% if piutang.status in 'open,partial,overdue' and not piutang.is_specifically_impaired %}
<div class="ni-modal-backdrop" id="penyisihanModal">
  <div class="ni-modal ni-modal--lg">
    <div class="ni-modal__header">
      <h3 class="ni-modal__title">Buat Jurnal Penyisihan — {{ piutang.nomor_piutang }}</h3>
      <button class="ni-modal__close" type="button" onclick="closeModal('penyisihanModal')">&times;</button>
    </div>
    <div class="ni-modal__body">
      <p class="ni-text-muted">Estimasi penyisihan: <strong>Rp {{ penyisihan_preview.total_penyisihan|floatformat:0|intcomma }}</strong></p>
      <form method="post" action="{% url 'piutang:penyisihan_create' piutang.pk %}">
        {% csrf_token %}
        <div class="ni-form-grid ni-form-grid--2">
          {% for field in penyisihan_form %}
          <div class="ni-form-group {% if field.name == 'catatan' %}ni-form-group--full{% endif %}">
            <label class="ni-form-label">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
          </div>
          {% endfor %}
        </div>
        <div class="ni-btn-row">
          <button type="submit" class="ni-btn ni-btn--primary">Buat Jurnal Penyisihan</button>
          <button type="button" class="ni-btn ni-btn--secondary" onclick="closeModal('penyisihanModal')">Batal</button>
        </div>
      </form>
    </div>
  </div>
</div>
{% endif %}
```

- [ ] **Step 4: Commit**

```bash
git add templates/piutang/detail.html
git commit -m "feat(piutang): add angsuran table and penyisihan card to detail.html"
```

---

## Task 14: Rewrite piutang/report_aging.html

**Files:**
- Modify: `templates/piutang/report_aging.html`

- [ ] **Step 1: Replace report_aging.html**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Aging Piutang{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Aging Piutang</h1>
    <p class="ni-page-header__subtitle">Klasifikasi keterlambatan per angsuran</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'piutang:report_penyisihan' %}" class="ni-btn ni-btn--primary">Buat Jurnal Penyisihan Batch</a>
  </div>
</div>

{% for bucket in bucket_summary %}
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header">
    <h2 class="ni-card__title">{{ bucket.label }}</h2>
    <div style="display:flex;gap:1rem;align-items:center;">
      <span class="ni-text-muted">Rate: {{ bucket.rate }}%</span>
      <span class="ni-text-muted">Estimasi Penyisihan: <strong>Rp {{ bucket.penyisihan|floatformat:0|intcomma }}</strong></span>
    </div>
  </div>
  {% if bucket.entries %}
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead>
        <tr>
          <th>Nomor Piutang</th>
          <th>Debitur</th>
          <th>No Angsuran</th>
          <th>Tanggal Angsuran</th>
          <th class="ni-text-right">Hari Lewat</th>
          <th class="ni-text-right">Jumlah</th>
        </tr>
      </thead>
      <tbody>
        {% for entry in bucket.entries %}
        <tr>
          <td><a href="{% url 'piutang:detail' entry.piutang.pk %}">{{ entry.piutang.nomor_piutang }}</a></td>
          <td>{{ entry.piutang.entitas_display }}</td>
          <td>{% if entry.angsuran_no %}{{ entry.angsuran_no }}{% else %}-{% endif %}</td>
          <td>{{ entry.tanggal_angsuran|default:'-' }}</td>
          <td class="ni-text-right">{% if bucket.key != 'current' %}{{ entry.hari_lewat }}{% else %}-{% endif %}</td>
          <td class="ni-text-right">{{ entry.jumlah|floatformat:0|intcomma }}</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="5"><strong>Subtotal</strong></td>
          <td class="ni-text-right"><strong>{{ bucket.total|floatformat:0|intcomma }}</strong></td>
        </tr>
      </tfoot>
    </table>
  </div>
  {% else %}
  <div class="ni-card__body"><p class="ni-text-muted">Tidak ada piutang di bucket ini.</p></div>
  {% endif %}
</div>
{% endfor %}

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">Ringkasan</h2></div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Bucket</th><th class="ni-text-right">Total Outstanding</th><th class="ni-text-right">Rate</th><th class="ni-text-right">Estimasi Penyisihan</th></tr></thead>
      <tbody>
        {% for bucket in bucket_summary %}
        <tr>
          <td>{{ bucket.label }}</td>
          <td class="ni-text-right">{{ bucket.total|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ bucket.rate }}%</td>
          <td class="ni-text-right">{{ bucket.penyisihan|floatformat:0|intcomma }}</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <td><strong>Grand Total</strong></td>
          <td class="ni-text-right"><strong>{{ grand_total_outstanding|floatformat:0|intcomma }}</strong></td>
          <td></td>
          <td class="ni-text-right"><strong>{{ grand_total_penyisihan|floatformat:0|intcomma }}</strong></td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/piutang/report_aging.html
git commit -m "feat(piutang): rewrite report_aging.html with per-row detail, 7 buckets, penyisihan estimate"
```

---

## Task 15: New piutang/report_penyisihan.html

**Files:**
- Create: `templates/piutang/report_penyisihan.html`

- [ ] **Step 1: Create report_penyisihan.html**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Penyisihan Piutang Batch{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Penyisihan Piutang — Batch</h1>
    <p class="ni-page-header__subtitle">Hitung dan buat jurnal penyisihan akhir periode</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'piutang:report_aging' %}" class="ni-btn ni-btn--secondary">&#8592; Aging</a>
    <a href="{% url 'piutang:settings_rates' %}" class="ni-btn ni-btn--secondary">Pengaturan Rate</a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">Parameter Perhitungan</h2></div>
  <div class="ni-card__body">
    <form method="post" id="batch-form">
      {% csrf_token %}
      <div class="ni-form-grid ni-form-grid--2">
        {% for field in form %}
        <div class="ni-form-group {% if field.name == 'catatan' %}ni-form-group--full{% endif %}">
          <label class="ni-form-label">{{ field.label }}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
        {% endfor %}
      </div>
      <div class="ni-btn-row">
        <button type="submit" name="action" value="preview" class="ni-btn ni-btn--secondary">Preview</button>
        {% if batch_preview and batch_preview.delta != 0 %}
        <button type="submit" name="action" value="post" class="ni-btn ni-btn--primary" onclick="return confirm('Buat jurnal penyisihan batch? Delta: Rp {{ batch_preview.delta|floatformat:0|intcomma }}')">Post Jurnal</button>
        {% endif %}
      </div>
    </form>
  </div>
</div>

{% if batch_preview %}
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">Preview Perhitungan</h2></div>
  <div class="ni-card__body">
    <dl class="ni-detail-grid">
      <dt>Jumlah Piutang Dihitung</dt><dd>{{ batch_preview.piutang_count }}</dd>
      <dt>Target Saldo Cadangan</dt><dd><strong>Rp {{ batch_preview.target_saldo|floatformat:0|intcomma }}</strong></dd>
      <dt>Saldo Existing Akun Cadangan</dt><dd>Rp {{ batch_preview.saldo_existing|floatformat:0|intcomma }}</dd>
      <dt>Delta (Jurnal yang Akan Dibuat)</dt>
      <dd>
        <strong>Rp {{ batch_preview.delta|floatformat:0|intcomma }}</strong>
        {% if batch_preview.delta > 0 %}<span class="ni-badge ni-badge--danger">Tambah Beban</span>
        {% elif batch_preview.delta < 0 %}<span class="ni-badge ni-badge--success">Pemulihan</span>
        {% else %}<span class="ni-badge">Tidak Ada Perubahan</span>{% endif %}
      </dd>
    </dl>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Bucket</th><th class="ni-text-right">Jumlah Piutang</th><th class="ni-text-right">Rate (%)</th><th class="ni-text-right">Penyisihan</th></tr></thead>
      <tbody>
        {% for b in batch_preview.breakdown %}
        <tr {% if b.jumlah_piutang == 0 %}class="ni-row--muted"{% endif %}>
          <td>{{ b.label }}</td>
          <td class="ni-text-right">{{ b.jumlah_piutang|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ b.rate }}%</td>
          <td class="ni-text-right">{{ b.penyisihan|floatformat:0|intcomma }}</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="3"><strong>Target Saldo</strong></td>
          <td class="ni-text-right"><strong>{{ batch_preview.target_saldo|floatformat:0|intcomma }}</strong></td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>
{% endif %}

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">Riwayat Batch Penyisihan</h2></div>
  {% if history %}
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Tanggal</th><th class="ni-text-right">Jumlah</th><th>Jurnal</th><th>Catatan</th><th>Dibuat Oleh</th></tr></thead>
      <tbody>
        {% for ps in history %}
        <tr>
          <td>{{ ps.tanggal }}</td>
          <td class="ni-text-right {% if ps.jumlah < 0 %}ni-text-success{% endif %}">{{ ps.jumlah|floatformat:0|intcomma }}</td>
          <td>{% if ps.jurnal_header %}<a href="{% url 'jurnal:header_detail' ps.jurnal_header.pk %}">{{ ps.jurnal_header.nomor_transaksi }}</a>{% else %}-{% endif %}</td>
          <td>{{ ps.catatan|default:'-' }}</td>
          <td>{{ ps.created_by|default:'-' }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="ni-card__body"><p class="ni-text-muted">Belum ada jurnal batch.</p></div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/piutang/report_penyisihan.html
git commit -m "feat(piutang): create report_penyisihan.html for batch allowance journal"
```

---

## Task 16: New piutang/settings_rates.html

**Files:**
- Create: `templates/piutang/settings_rates.html`

- [ ] **Step 1: Create settings_rates.html**

```html
{% extends 'base.html' %}
{% load humanize %}
{% block title %}Pengaturan Rate Penyisihan{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Pengaturan Rate Penyisihan Piutang</h1>
    <p class="ni-page-header__subtitle">Atur persentase penyisihan per bucket aging</p>
  </div>
  <div class="ni-page-header__actions">
    <a href="{% url 'piutang:report_penyisihan' %}" class="ni-btn ni-btn--secondary">&#8592; Kembali</a>
  </div>
</div>

<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header"><h2 class="ni-card__title">Rate per Bucket</h2></div>
  <form method="post">
    {% csrf_token %}
    {{ formset.management_form }}
    <div class="ni-table-wrapper">
      <table class="ni-table">
        <thead>
          <tr><th>Bucket</th><th>Label</th><th class="ni-text-right" style="width:160px">Rate (%)</th></tr>
        </thead>
        <tbody>
          {% for item_form, rate_obj in formset|zip:rates %}
          <tr>
            {{ item_form.id }}
            <td><code>{{ rate_obj.bucket_key }}</code></td>
            <td>{{ rate_obj.label }}</td>
            <td class="ni-text-right">{{ item_form.rate_percent }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="ni-card__body">
      <p class="ni-text-muted">Rate 0–100%. Bucket <code>over_365</code> sebaiknya 100% sesuai SAK.</p>
    </div>
    <div class="ni-btn-row" style="padding:1rem">
      <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
    </div>
  </form>
</div>
{% endblock %}
```

Note: The `zip` template filter is used above. If `zip` is not available as a Django template filter, replace the loop with:

```html
{% for item_form in formset %}
<tr>
  {{ item_form.id }}
  <td>{{ item_form.instance.bucket_key }}</td>
  <td>{{ item_form.instance.label }}</td>
  <td class="ni-text-right">{{ item_form.rate_percent }}</td>
</tr>
{% endfor %}
```

Use the second version (with `item_form.instance`) as it doesn't require a custom filter.

- [ ] **Step 2: Commit**

```bash
git add templates/piutang/settings_rates.html
git commit -m "feat(piutang): create settings_rates.html for PenyisihanRateConfig editing"
```

---

## Task 17: Update piutang/dashboard.html

**Files:**
- Modify: `templates/piutang/dashboard.html`

- [ ] **Step 1: Read current dashboard.html to see existing KPI cards**

Open `templates/piutang/dashboard.html`. Find the KPI section and:

1. Add `piutang_neto` and `total_penyisihan_target` to the KPI cards (after existing KPIs).
2. Replace the `buckets` usage (old format `{{ buckets.current }}`) with `kpi.aging_summary`.

Remove the `buckets` variable usage entirely (the dashboard view no longer passes it).

Add two new KPI cards after the existing ones:

```html
<div class="ni-card">
  <div class="ni-card__header"><h2 class="ni-card__title">Estimasi Penyisihan</h2></div>
  <div class="ni-card__body">
    <p class="ni-stat">Rp {{ kpi.total_penyisihan_target|floatformat:0|intcomma }}</p>
  </div>
</div>
<div class="ni-card">
  <div class="ni-card__header"><h2 class="ni-card__title">Piutang Neto</h2></div>
  <div class="ni-card__body">
    <p class="ni-stat">Rp {{ kpi.piutang_neto|floatformat:0|intcomma }}</p>
  </div>
</div>
```

Add an aging summary table using `kpi.aging_summary`:

```html
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__header">
    <h2 class="ni-card__title">Aging Summary</h2>
    <a href="{% url 'piutang:report_aging' %}" class="ni-btn ni-btn--sm ni-btn--secondary">Detail</a>
  </div>
  <div class="ni-table-wrapper">
    <table class="ni-table">
      <thead><tr><th>Bucket</th><th class="ni-text-right">Outstanding</th><th class="ni-text-right">Rate</th><th class="ni-text-right">Penyisihan</th></tr></thead>
      <tbody>
        {% for key, summary in kpi.aging_summary.items %}
        <tr>
          <td>{{ summary.label }}</td>
          <td class="ni-text-right">{{ summary.total_outstanding|floatformat:0|intcomma }}</td>
          <td class="ni-text-right">{{ summary.rate }}%</td>
          <td class="ni-text-right">{{ summary.penyisihan|floatformat:0|intcomma }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add templates/piutang/dashboard.html
git commit -m "feat(piutang): update dashboard with piutang_neto, total_penyisihan_target, aging summary table"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Task 1-2: PiutangHeader new fields + PenyisihanRateConfig + PiutangPenyisihan models
- [x] Task 3: compute_angsuran_schedule()
- [x] Task 4: get_piutang_aging() refactor (7-bucket per-row)
- [x] Task 5: compute_penyisihan_for_piutang()
- [x] Task 6: create_penyisihan_journal() + reverse
- [x] Task 7: compute_batch_penyisihan() + create_batch_penyisihan_journal()
- [x] Task 8: get_piutang_dashboard_kpi() update + create_manual_piutang() signature
- [x] Task 9: All new forms
- [x] Task 10-11: All views updated + new views + URL patterns
- [x] Tasks 12-17: All templates

**Type consistency:**
- `compute_angsuran_schedule` returns `list[dict]` with keys `{no, tanggal, pokok, bunga, angsuran, sisa_pokok, paid, sisa_bayar, status}` — used correctly in aging, detail view, templates
- `get_piutang_aging()` returns `{bucket_key: list[{piutang, angsuran_no, tanggal_angsuran, jumlah, hari_lewat}]}` — used correctly in report_aging view and dashboard KPI
- `compute_batch_penyisihan` returns `{target_saldo, saldo_existing, delta, breakdown, piutang_count}` — used correctly in `piutang_report_penyisihan` view and template
- `_AGING_BUCKET_KEYS` and `_AGING_BUCKET_LABELS` exported from services, imported in report_aging view ✓

**Potential issue:** `_AGING_BUCKET_KEYS` and `_AGING_BUCKET_LABELS` are module-level variables in services.py — they need to be importable. The `from .services import _AGING_BUCKET_KEYS, _AGING_BUCKET_LABELS` in the report_aging view is valid Python.
