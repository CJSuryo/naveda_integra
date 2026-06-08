# Piutang Module — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder `apps/piutang/` stub with a full accounts-receivable module mirroring `apps/utang/`.

**Architecture:** 7 models + service layer + views/templates. Piutang can be created manually or auto-created from sales/pendapatan (those callers don't exist yet — stub functions only). Mirrors utang architecture: header + detail + payment records + audit log.

**Tech Stack:** Django 4.x, Python 3.11+, `django.test.TestCase`, `Decimal`, utang templates as base.

**Spec:** `docs/superpowers/specs/2026-06-07-piutang-design.md`

---

## File Map

| Action | File |
|---|---|
| Rewrite | `apps/piutang/models.py` |
| Create | `apps/piutang/services.py` |
| Rewrite | `apps/piutang/tests.py` |
| Rewrite | `apps/piutang/forms.py` |
| Rewrite | `apps/piutang/views.py` |
| Rewrite | `apps/piutang/urls.py` |
| Rewrite | `apps/piutang/admin.py` |
| Rewrite | `apps/piutang/apps.py` |
| Modify | `naveda_integra/urls.py` |
| Create | `templates/piutang/dashboard.html` |
| Create | `templates/piutang/list.html` |
| Create | `templates/piutang/form.html` |
| Create | `templates/piutang/detail.html` |
| Create | `templates/piutang/delete.html` |
| Create | `templates/piutang/payment_form.html` |
| Create | `templates/piutang/write_off_form.html` |
| Create | `templates/piutang/reklasifikasi_form.html` |
| Create | `templates/piutang/report_aging.html` |
| Create | `templates/piutang/report_subjek.html` |
| Create | `templates/piutang/report_jatuh_tempo.html` |
| Create | `templates/piutang/report_write_off.html` |

---

## Task 1: Rewrite Models

**Files:**
- Rewrite: `apps/piutang/models.py`

- [ ] **Step 1: Rewrite models.py**

```python
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


JENIS_JANGKA_WAKTU_CHOICES = [
    ('short_term', 'Jangka Pendek'),
    ('long_term', 'Jangka Panjang'),
]

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

JENIS_DOKUMEN_CHOICES = [
    ('invoice', 'Invoice'),
    ('kontrak', 'Kontrak'),
    ('spk', 'SPK'),
    ('perjanjian', 'Perjanjian'),
    ('berita_acara', 'Berita Acara'),
    ('kuitansi', 'Kuitansi'),
    ('lainnya', 'Lainnya'),
]

METODE_PENERIMAAN_CHOICES = [
    ('transfer', 'Transfer'),
    ('tunai', 'Tunai'),
    ('giro', 'Giro'),
    ('cek', 'Cek'),
]


class PiutangHeader(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Terbuka'),
        ('partial', 'Sebagian Diterima'),
        ('paid', 'Lunas'),
        ('overdue', 'Jatuh Tempo'),
        ('written_off', 'Dihapusbukukan'),
        ('cancelled', 'Dibatalkan'),
    ]
    APPROVAL_STATUS_CHOICES = [
        ('', '-'),
        ('pending', 'Menunggu'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('from_sales', 'Dari Sales'),
        ('from_pendapatan', 'Dari Pendapatan'),
    ]

    nomor_piutang = models.CharField(max_length=100, unique=True, editable=False, verbose_name='Nomor Piutang')
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    jatuh_tempo = models.DateField(null=True, blank=True, db_index=True, verbose_name='Jatuh Tempo')
    debitur = models.CharField(max_length=255, blank=True, default='', verbose_name='Debitur')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_headers', verbose_name='Entitas Bisnis',
    )
    deskripsi = models.CharField(max_length=512, blank=True, default='', verbose_name='Deskripsi')
    source_type = models.CharField(
        max_length=20, choices=SOURCE_TYPE_CHOICES, default='manual', verbose_name='Sumber',
    )
    source_sales = models.ForeignKey(
        'sales.SalesHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_headers', verbose_name='Sales Header',
    )
    source_pendapatan = models.ForeignKey(
        'pendapatan.PendapatanHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_headers', verbose_name='Pendapatan Header',
    )
    jumlah_pokok = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Pokok')
    jumlah_terbayar = models.DecimalField(
        max_digits=19, decimal_places=4, default=0, verbose_name='Jumlah Terbayar',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Status',
    )
    jenis_jangka_waktu = models.CharField(
        max_length=20, choices=JENIS_JANGKA_WAKTU_CHOICES, default='short_term',
        verbose_name='Jenis Jangka Waktu',
    )
    requires_approval = models.BooleanField(default=False, verbose_name='Perlu Persetujuan')
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES, blank=True, default='',
        verbose_name='Status Persetujuan',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_approved', verbose_name='Disetujui Oleh',
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Disetujui Pada')
    coa_piutang_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_headers', verbose_name='Akun Piutang',
    )
    jenis_bunga = models.CharField(
        max_length=20, choices=JENIS_BUNGA_CHOICES, default='tanpa_bunga',
        verbose_name='Jenis Bunga',
    )
    bunga_persen = models.DecimalField(
        max_digits=8, decimal_places=4, default=0, verbose_name='Suku Bunga (% per tahun)',
    )
    jumlah_angsuran = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Jumlah Angsuran',
    )
    periode_angsuran = models.CharField(
        max_length=20, choices=PERIODE_ANGSURAN_CHOICES, default='bulanan',
        verbose_name='Periode Angsuran',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Piutang Header'
        verbose_name_plural = 'Piutang Header'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='idx_ph_tanggal_status'),
            models.Index(fields=['source_type', 'status'], name='idx_ph_source_status'),
            models.Index(fields=['jatuh_tempo'], name='idx_ph_jatuh_tempo'),
        ]

    def __str__(self) -> str:
        return self.nomor_piutang

    def save(self, *args, **kwargs):
        if not self.nomor_piutang:
            self.nomor_piutang = self._generate_nomor()
        super().save(*args, **kwargs)

    def _generate_nomor(self) -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                PiutangHeader.objects
                .select_for_update()
                .filter(nomor_piutang__startswith='TRX-PIU-')
                .order_by('-nomor_piutang')
                .values_list('nomor_piutang', flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f'TRX-PIU-{seq:03d}'

    @property
    def sisa_piutang(self) -> Decimal:
        return (self.jumlah_pokok - self.jumlah_terbayar).quantize(Decimal('0.0001'))

    @property
    def is_overdue(self) -> bool:
        if not self.jatuh_tempo or self.status in ('paid', 'cancelled', 'written_off'):
            return False
        return timezone.now().date() > self.jatuh_tempo

    @property
    def days_overdue(self) -> int:
        if not self.jatuh_tempo or self.status in ('paid', 'cancelled', 'written_off'):
            return 0
        return max(0, (timezone.now().date() - self.jatuh_tempo).days)

    @property
    def can_pay(self) -> bool:
        return self.status in ('open', 'partial', 'overdue') and not self.is_locked

    @property
    def can_reklasifikasi(self) -> bool:
        return (
            self.status in ('open', 'partial', 'overdue')
            and self.jenis_jangka_waktu == 'long_term'
            and self.jatuh_tempo is not None
        )

    @property
    def entitas_display(self) -> str:
        if self.debitur:
            return self.debitur
        return str(self.entitas_bisnis) if self.entitas_bisnis else '-'


class PiutangDetail(models.Model):
    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.CASCADE, related_name='details',
        verbose_name='Piutang Header',
    )
    deskripsi = models.CharField(max_length=255, blank=True, default='', verbose_name='Deskripsi')
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah')
    revenue_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='piutang_details', verbose_name='Akun Pendapatan',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_details', verbose_name='Sub-Tipe Transaksi',
    )

    class Meta:
        verbose_name = 'Piutang Detail'
        verbose_name_plural = 'Piutang Detail'

    def __str__(self) -> str:
        return f'{self.piutang_header.nomor_piutang} — {self.deskripsi or self.jumlah}'


class PiutangPenerimaan(models.Model):
    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.CASCADE, related_name='penerimaan',
        verbose_name='Piutang Header',
    )
    tanggal_terima = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal Terima')
    jumlah_diterima = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Diterima')
    angsuran_no = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='No. Angsuran')
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_penerimaan', verbose_name='Akun Penerimaan',
    )
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_penerimaan', verbose_name='Jurnal',
    )
    metode_penerimaan = models.CharField(
        max_length=20, choices=METODE_PENERIMAAN_CHOICES, default='transfer',
        verbose_name='Metode Penerimaan',
    )
    nomor_referensi = models.CharField(max_length=100, blank=True, default='', verbose_name='No. Referensi')
    catatan = models.CharField(max_length=512, blank=True, default='', verbose_name='Catatan')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_penerimaan_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Penerimaan Piutang'
        verbose_name_plural = 'Penerimaan Piutang'
        ordering = ['-tanggal_terima', '-created_at']
        indexes = [
            models.Index(fields=['piutang_header', 'tanggal_terima'], name='idx_pp_header_tanggal'),
        ]

    def __str__(self) -> str:
        return f'Penerimaan {self.jumlah_diterima} — {self.piutang_header.nomor_piutang}'


class PiutangReklasifikasi(models.Model):
    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.CASCADE, related_name='reklasifikasi_entries',
        verbose_name='Piutang Header',
    )
    tanggal = models.DateField(verbose_name='Tanggal')
    dari_akun = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_rkl_dari', verbose_name='Dari Akun',
    )
    ke_akun = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_rkl_ke', verbose_name='Ke Akun',
    )
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah')
    keterangan = models.CharField(max_length=255, blank=True, default='', verbose_name='Keterangan')
    jurnal = models.OneToOneField(
        'jurnal.JurnalHeader', on_delete=models.CASCADE,
        related_name='piutang_reklasifikasi', verbose_name='Jurnal',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_rkl_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Reklasifikasi Piutang'
        verbose_name_plural = 'Reklasifikasi Piutang'
        ordering = ['-tanggal', '-created_at']

    def __str__(self) -> str:
        return f'Reklasifikasi {self.piutang_header.nomor_piutang} — {self.tanggal}'


class PiutangWriteOff(models.Model):
    METODE_CHOICES = [
        ('langsung', 'Langsung'),
        ('cadangan', 'Cadangan Kerugian'),
    ]

    piutang_header = models.OneToOneField(
        PiutangHeader, on_delete=models.CASCADE, related_name='write_off',
        verbose_name='Piutang Header',
    )
    tanggal = models.DateField(verbose_name='Tanggal')
    jumlah_dihapus = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Dihapus')
    metode = models.CharField(max_length=20, choices=METODE_CHOICES, verbose_name='Metode')
    bad_debt_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_write_off_bad_debt', verbose_name='Akun Beban Piutang Tak Tertagih',
    )
    allowance_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        null=True, blank=True, related_name='piutang_write_off_allowance',
        verbose_name='Akun Cadangan Kerugian Piutang',
    )
    alasan = models.TextField(blank=True, default='', verbose_name='Alasan')
    jurnal = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_write_offs', verbose_name='Jurnal',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_write_off_created', verbose_name='Dibuat Oleh',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Write-Off Piutang'
        verbose_name_plural = 'Write-Off Piutang'

    def __str__(self) -> str:
        return f'Write-Off {self.piutang_header.nomor_piutang} — {self.tanggal}'


class PiutangAttachment(models.Model):
    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.CASCADE, related_name='attachments',
        verbose_name='Piutang Header',
    )
    file = models.FileField(upload_to='piutang/attachments/%Y/%m/', verbose_name='File')
    file_name = models.CharField(max_length=255, verbose_name='Nama File')
    jenis_dokumen = models.CharField(
        max_length=30, choices=JENIS_DOKUMEN_CHOICES, default='lainnya',
        verbose_name='Jenis Dokumen',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_attachments', verbose_name='Diupload Oleh',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Diupload Pada')

    class Meta:
        verbose_name = 'Lampiran Piutang'
        verbose_name_plural = 'Lampiran Piutang'
        ordering = ['-uploaded_at']

    def __str__(self) -> str:
        return f'{self.file_name} ({self.piutang_header.nomor_piutang})'


class PiutangAuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATED', 'Dibuat'),
        ('EDITED', 'Diedit'),
        ('SUBMIT_APPROVAL', 'Diajukan Persetujuan'),
        ('APPROVED', 'Disetujui'),
        ('REJECTED', 'Ditolak'),
        ('PAYMENT', 'Penerimaan'),
        ('REVERSE_PAYMENT', 'Batalkan Penerimaan'),
        ('WRITE_OFF', 'Dihapusbukukan'),
        ('REKLASIFIKASI', 'Reklasifikasi'),
        ('CANCELLED', 'Dibatalkan'),
    ]

    piutang_header = models.ForeignKey(
        PiutangHeader, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_logs', verbose_name='Piutang Header',
    )
    nomor_piutang = models.CharField(max_length=100, blank=True, default='', verbose_name='Nomor Piutang')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='Aksi')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_audit_logs', verbose_name='User',
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Waktu')
    before_json = models.JSONField(default=dict, blank=True, verbose_name='Sebelum')
    after_json = models.JSONField(default=dict, blank=True, verbose_name='Sesudah')
    notes = models.CharField(max_length=512, blank=True, default='', verbose_name='Catatan')

    class Meta:
        verbose_name = 'Audit Log Piutang'
        verbose_name_plural = 'Audit Log Piutang'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['nomor_piutang', 'timestamp'], name='idx_pal_nomor_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.action} — {self.nomor_piutang} — {self.timestamp}'
```

- [ ] **Step 2: Run makemigrations**

```bash
python manage.py makemigrations piutang
```

Expected: `Migrations for 'piutang': apps/piutang/migrations/0001_initial.py`

- [ ] **Step 3: Run migrate**

```bash
python manage.py migrate piutang
```

Expected: `Applying piutang.0001_initial... OK`

- [ ] **Step 4: Commit**

```bash
git add apps/piutang/models.py apps/piutang/migrations/
git commit -m "feat(piutang): add full model schema replacing placeholder stub"
```

---

## Task 2: apps.py

**Files:**
- Modify: `apps/piutang/apps.py`

- [ ] **Step 1: Update apps.py**

```python
from django.apps import AppConfig


class PiutangConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.piutang'
    verbose_name = 'Piutang'
```

---

## Task 3: Service — create_manual_piutang + audit helpers

**Files:**
- Create: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

```python
# apps/piutang/tests.py
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun

from .models import PiutangHeader, PiutangDetail, PiutangAuditLog
from .services import create_manual_piutang


def make_fixtures():
    tipe = TipeEntitas.objects.create(nama='Pelanggan')
    eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang', kode_akun='1.2.1')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Jasa', kode_akun='4.1.1')
    return {
        'tipe': tipe, 'eb': eb,
        'coa_piutang': coa_piutang, 'coa_kas': coa_kas, 'coa_pendapatan': coa_pendapatan,
    }


class CreateManualPiutangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_header_with_correct_fields(self):
        piutang = create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='PT Klien',
            deskripsi='Test piutang',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 7, 7),
            details=[{'deskripsi': 'Jasa konsultasi', 'jumlah': Decimal('1000000')}],
        )
        self.assertIsNotNone(piutang.pk)
        self.assertTrue(piutang.nomor_piutang.startswith('TRX-PIU-'))
        self.assertEqual(piutang.jumlah_pokok, Decimal('1000000'))
        self.assertEqual(piutang.status, 'draft')
        self.assertEqual(piutang.details.count(), 1)

    def test_creates_audit_log(self):
        create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='',
            deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=None,
            details=[{'deskripsi': 'Item', 'jumlah': Decimal('500000')}],
        )
        self.assertEqual(PiutangAuditLog.objects.filter(action='CREATED').count(), 1)

    def test_raises_if_no_details(self):
        with self.assertRaises(ValueError):
            create_manual_piutang(
                tanggal=date(2026, 6, 7), entitas_bisnis=self.f['eb'],
                debitur='', deskripsi='', coa_piutang_account=self.f['coa_piutang'],
                jatuh_tempo=None, details=[],
            )

    def test_auto_number_increments(self):
        p1 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='X',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'A', 'jumlah': Decimal('100')}],
        )
        p2 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='Y',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'B', 'jumlah': Decimal('200')}],
        )
        n1 = int(p1.nomor_piutang.rsplit('-', 1)[1])
        n2 = int(p2.nomor_piutang.rsplit('-', 1)[1])
        self.assertEqual(n2, n1 + 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.piutang.tests.CreateManualPiutangTests -v 2
```

Expected: ImportError or AttributeError — `services` module not found.

- [ ] **Step 3: Implement create_manual_piutang**

```python
# apps/piutang/services.py
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalDetail, JurnalHeader

from .models import (
    PiutangAuditLog, PiutangAttachment, PiutangDetail, PiutangHeader,
    PiutangPenerimaan, PiutangReklasifikasi, PiutangWriteOff,
)


# ── Audit Helper ──────────────────────────────────────────────────────────────

def _log(piutang: PiutangHeader, action: str, user=None, before=None, after=None, notes=''):
    PiutangAuditLog.objects.create(
        piutang_header=piutang,
        nomor_piutang=piutang.nomor_piutang,
        action=action,
        user=user,
        before_json=before or {},
        after_json=after or {},
        notes=notes,
    )


def _snapshot(piutang: PiutangHeader) -> dict:
    return {
        'status': piutang.status,
        'jumlah_pokok': str(piutang.jumlah_pokok),
        'jumlah_terbayar': str(piutang.jumlah_terbayar),
    }


def _next_piutang_journal_number(prefix: str) -> str:
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


# ── Create ────────────────────────────────────────────────────────────────────

def create_manual_piutang(
    tanggal,
    entitas_bisnis,
    debitur: str,
    deskripsi: str,
    coa_piutang_account,
    jatuh_tempo,
    details: list,  # [{'deskripsi': str, 'jumlah': Decimal, 'revenue_account': Akun (optional)}]
    jenis_jangka_waktu: str = 'short_term',
    requires_approval: bool = False,
    jenis_bunga: str = 'tanpa_bunga',
    bunga_persen: Decimal = Decimal('0'),
    jumlah_angsuran=None,
    periode_angsuran: str = 'bulanan',
    user=None,
) -> PiutangHeader:
    if not details:
        raise ValueError('Minimal satu detail piutang diperlukan.')
    total = sum(Decimal(str(d['jumlah'])) for d in details)
    if total <= 0:
        raise ValueError('Total piutang harus lebih besar dari 0.')

    with transaction.atomic():
        piutang = PiutangHeader.objects.create(
            tanggal=tanggal,
            entitas_bisnis=entitas_bisnis,
            debitur=debitur,
            deskripsi=deskripsi,
            coa_piutang_account=coa_piutang_account,
            jatuh_tempo=jatuh_tempo,
            jumlah_pokok=total,
            status='draft',
            jenis_jangka_waktu=jenis_jangka_waktu,
            requires_approval=requires_approval,
            approval_status='pending' if requires_approval else '',
            jenis_bunga=jenis_bunga,
            bunga_persen=bunga_persen,
            jumlah_angsuran=jumlah_angsuran,
            periode_angsuran=periode_angsuran,
            created_by=user,
        )
        PiutangDetail.objects.bulk_create([
            PiutangDetail(
                piutang_header=piutang,
                deskripsi=d.get('deskripsi', ''),
                jumlah=Decimal(str(d['jumlah'])),
                revenue_account=d.get('revenue_account'),
                sub_transaction_type=d.get('sub_transaction_type'),
            )
            for d in details
        ])
        _log(piutang, 'CREATED', user=user, after=_snapshot(piutang))
    return piutang


# ── Stubs for callers that will be implemented in later phases ─────────────────

def create_piutang_from_sales(sales_header, user=None) -> PiutangHeader:
    raise NotImplementedError('Implemented in Phase 2 after SalesHeader.payment_type is added.')


def create_piutang_from_pendapatan(pendapatan_header, user=None) -> PiutangHeader:
    raise NotImplementedError('Implemented in Phase 3 after apps/pendapatan/ is ready.')
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.CreateManualPiutangTests -v 2
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add create_manual_piutang service with audit log"
```

---

## Task 4: Service — create_piutang_payment

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `apps/piutang/tests.py`:

```python
from .services import create_manual_piutang, create_piutang_payment


class CreatePiutangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=self.f['eb'],
            debitur='PT Klien', deskripsi='', coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 7, 7),
            details=[{'deskripsi': 'Jasa', 'jumlah': Decimal('1000000')}],
        )
        self.piutang.status = 'open'
        self.piutang.save()

    def test_creates_penerimaan_record(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('400000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': 'TRF-001', 'catatan': ''},
        )
        self.assertEqual(self.piutang.penerimaan.count(), 1)

    def test_updates_jumlah_terbayar(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('400000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.jumlah_terbayar, Decimal('400000'))
        self.assertEqual(self.piutang.status, 'partial')

    def test_status_becomes_paid_when_fully_settled(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('1000000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'tunai',
             'nomor_referensi': '', 'catatan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.status, 'paid')

    def test_raises_if_exceeds_sisa(self):
        with self.assertRaises(ValueError):
            create_piutang_payment(
                self.piutang,
                {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('2000000'),
                 'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
                 'nomor_referensi': '', 'catatan': ''},
            )

    def test_generates_journal(self):
        from apps.jurnal.models import JurnalHeader
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('500000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        penerimaan = self.piutang.penerimaan.first()
        self.assertIsNotNone(penerimaan.jurnal_header)
        details = penerimaan.jurnal_header.details.all()
        debits = [d for d in details if d.debit > 0]
        credits = [d for d in details if d.kredit > 0]
        self.assertEqual(len(debits), 1)
        self.assertEqual(len(credits), 1)
        self.assertEqual(debits[0].akun, self.f['coa_kas'])
        self.assertEqual(credits[0].akun, self.f['coa_piutang'])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.piutang.tests.CreatePiutangPaymentTests -v 2
```

Expected: ImportError — `create_piutang_payment` not found.

- [ ] **Step 3: Implement create_piutang_payment**

Add to `apps/piutang/services.py`:

```python
def create_piutang_payment(piutang: PiutangHeader, data: dict, user=None) -> PiutangPenerimaan:
    jumlah = Decimal(str(data['jumlah_diterima']))
    if jumlah > piutang.sisa_piutang:
        raise ValueError(
            f'Jumlah diterima ({jumlah}) melebihi sisa piutang ({piutang.sisa_piutang}).'
        )
    with transaction.atomic():
        penerimaan = PiutangPenerimaan.objects.create(
            piutang_header=piutang,
            tanggal_terima=data['tanggal_terima'],
            jumlah_diterima=jumlah,
            angsuran_no=data.get('angsuran_no'),
            payment_account=data['payment_account'],
            metode_penerimaan=data.get('metode_penerimaan', 'transfer'),
            nomor_referensi=data.get('nomor_referensi', ''),
            catatan=data.get('catatan', ''),
            created_by=user,
        )
        jurnal = _create_payment_journal(piutang, penerimaan)
        penerimaan.jurnal_header = jurnal
        penerimaan.save(update_fields=['jurnal_header'])

        # Re-aggregate to avoid race condition
        from django.db.models import Sum
        total_paid = piutang.penerimaan.aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
        piutang.jumlah_terbayar = total_paid
        if total_paid >= piutang.jumlah_pokok:
            piutang.status = 'paid'
        elif total_paid > 0:
            piutang.status = 'partial'
        piutang.save(update_fields=['jumlah_terbayar', 'status'])

        _log(piutang, 'PAYMENT', user=user, after=_snapshot(piutang))
    return penerimaan


def _create_payment_journal(piutang: PiutangHeader, penerimaan: PiutangPenerimaan) -> JurnalHeader:
    nomor = _next_piutang_journal_number('TRX-PIU-P')
    header = JurnalHeader.objects.create(
        tanggal=penerimaan.tanggal_terima,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Penerimaan Piutang {piutang.nomor_piutang} — {piutang.entitas_display}',
        entitas_bisnis=piutang.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(
            jurnal_header=header,
            akun=penerimaan.payment_account,
            debit=penerimaan.jumlah_diterima,
            kredit=Decimal('0'),
        ),
        JurnalDetail(
            jurnal_header=header,
            akun=piutang.coa_piutang_account,
            debit=Decimal('0'),
            kredit=penerimaan.jumlah_diterima,
        ),
    ])
    return header
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.CreatePiutangPaymentTests -v 2
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add create_piutang_payment with journal generation"
```

---

## Task 5: Service — compute_angsuran_schedule + compute_bagian_lancar

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `apps/piutang/tests.py`:

```python
from .services import compute_angsuran_schedule, compute_bagian_lancar


class ComputeAngsuranScheduleTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def _make_piutang(self, jenis_bunga, bunga_persen, jumlah_angsuran, periode_angsuran):
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=date(2026, 12, 31),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('1200000')}],
            jenis_bunga=jenis_bunga, bunga_persen=bunga_persen,
            jumlah_angsuran=jumlah_angsuran, periode_angsuran=periode_angsuran,
        )
        return p

    def test_tanpa_bunga_equal_principal(self):
        p = self._make_piutang('tanpa_bunga', Decimal('0'), 3, 'bulanan')
        schedule = compute_angsuran_schedule(p)
        self.assertEqual(len(schedule), 3)
        self.assertEqual(schedule[0]['pokok'], Decimal('400000'))
        self.assertEqual(schedule[0]['bunga'], Decimal('0'))

    def test_flat_constant_installment(self):
        p = self._make_piutang('flat', Decimal('12'), 12, 'bulanan')
        schedule = compute_angsuran_schedule(p)
        self.assertEqual(len(schedule), 12)
        monthly_bunga = Decimal('1200000') * Decimal('12') / 100 / 12
        self.assertEqual(schedule[0]['bunga'], monthly_bunga)

    def test_total_pokok_equals_jumlah_pokok(self):
        p = self._make_piutang('tanpa_bunga', Decimal('0'), 4, 'bulanan')
        schedule = compute_angsuran_schedule(p)
        self.assertEqual(sum(r['pokok'] for r in schedule), p.jumlah_pokok)


class ComputeBagianLancarTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_full_amount_when_due_within_12_months(self):
        from datetime import timedelta
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 6, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        bagian = compute_bagian_lancar(p)
        self.assertEqual(bagian, Decimal('500000'))

    def test_zero_when_due_beyond_12_months(self):
        from datetime import date as d
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        bagian = compute_bagian_lancar(p)
        self.assertEqual(bagian, Decimal('0'))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.piutang.tests.ComputeAngsuranScheduleTests apps.piutang.tests.ComputeBagianLancarTests -v 2
```

- [ ] **Step 3: Implement schedule functions**

Add to `apps/piutang/services.py`:

```python
def compute_angsuran_schedule(piutang: PiutangHeader) -> list[dict]:
    if not piutang.jumlah_angsuran or piutang.jumlah_angsuran <= 0:
        return []
    n = piutang.jumlah_angsuran
    pokok = piutang.jumlah_pokok
    rate_annual = piutang.bunga_persen / Decimal('100')

    # Determine monthly rate based on periode_angsuran
    period_months = {'bulanan': 1, 'triwulanan': 3, 'semesteran': 6, 'tahunan': 12}
    m = period_months.get(piutang.periode_angsuran, 1)
    rate_period = rate_annual * m / Decimal('12')

    result = []
    if piutang.jenis_bunga == 'tanpa_bunga':
        base_pokok = (pokok / n).quantize(Decimal('0.01'))
        remainder = pokok - base_pokok * (n - 1)
        for i in range(1, n + 1):
            p = remainder if i == n else base_pokok
            result.append({'no': i, 'pokok': p, 'bunga': Decimal('0'), 'angsuran': p})

    elif piutang.jenis_bunga == 'flat':
        base_pokok = (pokok / n).quantize(Decimal('0.01'))
        bunga_period = (pokok * rate_period).quantize(Decimal('0.01'))
        remainder = pokok - base_pokok * (n - 1)
        for i in range(1, n + 1):
            p = remainder if i == n else base_pokok
            result.append({'no': i, 'pokok': p, 'bunga': bunga_period, 'angsuran': p + bunga_period})

    elif piutang.jenis_bunga == 'anuitas':
        if rate_period == 0:
            return compute_angsuran_schedule(
                type('obj', (), {
                    'jumlah_angsuran': n, 'jumlah_pokok': pokok, 'jenis_bunga': 'tanpa_bunga',
                    'bunga_persen': Decimal('0'), 'periode_angsuran': piutang.periode_angsuran,
                })()
            )
        # A = P * r(1+r)^n / ((1+r)^n - 1)
        factor = rate_period * (1 + rate_period) ** n / ((1 + rate_period) ** n - 1)
        angsuran_tetap = (pokok * factor).quantize(Decimal('0.01'))
        saldo = pokok
        for i in range(1, n + 1):
            bunga = (saldo * rate_period).quantize(Decimal('0.01'))
            p = (angsuran_tetap - bunga).quantize(Decimal('0.01'))
            if i == n:
                p = saldo  # last period cleans remainder
            result.append({'no': i, 'pokok': p, 'bunga': bunga, 'angsuran': p + bunga})
            saldo -= p

    return result


def compute_bagian_lancar(piutang: PiutangHeader) -> Decimal:
    if not piutang.jatuh_tempo:
        return Decimal('0')
    today = timezone.now().date()
    cutoff = today.replace(year=today.year + 1)
    if piutang.jatuh_tempo <= cutoff:
        return piutang.sisa_piutang
    return Decimal('0')
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test apps.piutang.tests.ComputeAngsuranScheduleTests apps.piutang.tests.ComputeBagianLancarTests -v 2
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add angsuran schedule and bagian lancar computation"
```

---

## Task 6: Service — write_off + reverse_payment + aging + KPI

**Files:**
- Modify: `apps/piutang/services.py`
- Modify: `apps/piutang/tests.py`

- [ ] **Step 1: Write failing tests**

Add to `apps/piutang/tests.py`:

```python
from .services import write_off_piutang, reverse_piutang_payment, get_piutang_aging


class WriteOffPiutangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_beban = Akun.objects.create(
            kategori_id='beban', nama='Beban Piutang Tak Tertagih', kode_akun='6.1.1',
        )
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=self.f['eb'], debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=date(2026, 3, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        self.piutang.status = 'overdue'
        self.piutang.save()

    def test_creates_write_off_record(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': 'Tidak tertagih'},
        )
        self.assertTrue(hasattr(self.piutang, 'write_off'))

    def test_status_becomes_written_off(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.status, 'written_off')

    def test_langsung_journal_dr_bad_debt_cr_piutang(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': ''},
        )
        wo = self.piutang.write_off
        details = wo.jurnal.details.all()
        dr = next(d for d in details if d.debit > 0)
        cr = next(d for d in details if d.kredit > 0)
        self.assertEqual(dr.akun, self.coa_beban)
        self.assertEqual(cr.akun, self.f['coa_piutang'])


class ReversePiutangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 6, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'X', 'jumlah': Decimal('1000000')}],
        )
        self.piutang.status = 'open'
        self.piutang.save()
        self.penerimaan = create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 7), 'jumlah_diterima': Decimal('600000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )

    def test_reversal_creates_counter_journal(self):
        from apps.jurnal.models import JurnalHeader
        initial_count = JurnalHeader.objects.count()
        reverse_piutang_payment(self.penerimaan)
        self.assertEqual(JurnalHeader.objects.count(), initial_count + 1)

    def test_jumlah_terbayar_reverts(self):
        reverse_piutang_payment(self.penerimaan)
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.jumlah_terbayar, Decimal('0'))
        self.assertEqual(self.piutang.status, 'open')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test apps.piutang.tests.WriteOffPiutangTests apps.piutang.tests.ReversePiutangPaymentTests -v 2
```

- [ ] **Step 3: Implement write_off + reverse + aging + KPI**

Add to `apps/piutang/services.py`:

```python
def write_off_piutang(piutang: PiutangHeader, data: dict, user=None) -> PiutangWriteOff:
    with transaction.atomic():
        jumlah = piutang.sisa_piutang
        nomor = _next_piutang_journal_number('TRX-PIU-WO')
        metode = data['metode']
        bad_debt = data['bad_debt_account']
        allowance = data.get('allowance_account')

        dr_akun = allowance if metode == 'cadangan' and allowance else bad_debt

        header = JurnalHeader.objects.create(
            tanggal=data['tanggal'],
            nomor_transaksi=nomor,
            uraian_transaksi=f'Write-Off Piutang {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=dr_akun, debit=jumlah, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=piutang.coa_piutang_account, debit=Decimal('0'), kredit=jumlah),
        ])

        wo = PiutangWriteOff.objects.create(
            piutang_header=piutang,
            tanggal=data['tanggal'],
            jumlah_dihapus=jumlah,
            metode=metode,
            bad_debt_account=bad_debt,
            allowance_account=allowance,
            alasan=data.get('alasan', ''),
            jurnal=header,
            created_by=user,
        )
        piutang.status = 'written_off'
        piutang.is_locked = True
        piutang.save(update_fields=['status', 'is_locked'])
        _log(piutang, 'WRITE_OFF', user=user, after=_snapshot(piutang))
    return wo


def reverse_piutang_payment(penerimaan: PiutangPenerimaan, user=None) -> JurnalHeader:
    with transaction.atomic():
        piutang = penerimaan.piutang_header
        orig = penerimaan.jurnal_header
        nomor = _next_piutang_journal_number('TRX-PIU-PR')
        rev_header = JurnalHeader.objects.create(
            tanggal=timezone.now().date(),
            nomor_transaksi=nomor,
            uraian_transaksi=f'Reversal Penerimaan {piutang.nomor_piutang}',
            entitas_bisnis=piutang.entitas_bisnis,
            is_penyesuaian=True,
        )
        if orig:
            reverse_lines = [
                JurnalDetail(
                    jurnal_header=rev_header,
                    akun=d.akun,
                    debit=d.kredit,
                    kredit=d.debit,
                )
                for d in orig.details.all()
            ]
            JurnalDetail.objects.bulk_create(reverse_lines)

        penerimaan.delete()

        from django.db.models import Sum
        total_paid = piutang.penerimaan.aggregate(s=Sum('jumlah_diterima'))['s'] or Decimal('0')
        piutang.jumlah_terbayar = total_paid
        if total_paid <= 0:
            piutang.status = 'open' if piutang.status not in ('draft', 'cancelled', 'written_off') else piutang.status
        elif total_paid < piutang.jumlah_pokok:
            piutang.status = 'partial'
        piutang.save(update_fields=['jumlah_terbayar', 'status'])
        _log(piutang, 'REVERSE_PAYMENT', user=user, after=_snapshot(piutang))
    return rev_header


def get_piutang_aging() -> dict:
    from datetime import timedelta
    from django.db.models import Sum
    today = timezone.now().date()
    qs = PiutangHeader.objects.filter(status__in=('open', 'partial', 'overdue'))
    buckets = {'current': Decimal('0'), '1_30': Decimal('0'), '31_60': Decimal('0'),
               '61_90': Decimal('0'), 'over_90': Decimal('0')}
    for p in qs:
        sisa = p.sisa_piutang
        if not p.jatuh_tempo or p.jatuh_tempo >= today:
            buckets['current'] += sisa
        else:
            days = (today - p.jatuh_tempo).days
            if days <= 30:
                buckets['1_30'] += sisa
            elif days <= 60:
                buckets['31_60'] += sisa
            elif days <= 90:
                buckets['61_90'] += sisa
            else:
                buckets['over_90'] += sisa
    return buckets


def get_piutang_dashboard_kpi() -> dict:
    from django.db.models import Sum
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
    return {
        'total_outstanding': total_outstanding,
        'total_overdue': total_overdue,
        'collected_this_month': collected_this_month,
        'collection_rate': collection_rate.quantize(Decimal('0.01')),
    }
```

- [ ] **Step 4: Run all piutang tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/services.py apps/piutang/tests.py
git commit -m "feat(piutang): add write_off, reverse_payment, aging, and KPI services"
```

---

## Task 7: Admin

**Files:**
- Rewrite: `apps/piutang/admin.py`

- [ ] **Step 1: Rewrite admin.py**

```python
from django.contrib import admin

from .models import (
    PiutangAttachment, PiutangAuditLog, PiutangDetail, PiutangHeader,
    PiutangPenerimaan, PiutangReklasifikasi, PiutangWriteOff,
)


class PiutangDetailInline(admin.TabularInline):
    model = PiutangDetail
    extra = 0


class PiutangPenerimaanInline(admin.TabularInline):
    model = PiutangPenerimaan
    extra = 0
    readonly_fields = ('jurnal_header',)


@admin.register(PiutangHeader)
class PiutangHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_piutang', 'tanggal', 'debitur', 'entitas_bisnis', 'jumlah_pokok', 'status')
    list_filter = ('status', 'source_type', 'jenis_jangka_waktu')
    search_fields = ('nomor_piutang', 'debitur', 'deskripsi')
    readonly_fields = ('nomor_piutang', 'created_at', 'updated_at')
    inlines = [PiutangDetailInline, PiutangPenerimaanInline]


@admin.register(PiutangAuditLog)
class PiutangAuditLogAdmin(admin.ModelAdmin):
    list_display = ('nomor_piutang', 'action', 'user', 'timestamp')
    list_filter = ('action',)
    readonly_fields = ('timestamp',)
```

- [ ] **Step 2: Verify admin loads**

```bash
python manage.py check
```

Expected: `System check identified no issues`

- [ ] **Step 3: Commit**

```bash
git add apps/piutang/admin.py
git commit -m "feat(piutang): register models in admin"
```

---

## Task 8: Forms

**Files:**
- Rewrite: `apps/piutang/forms.py`

- [ ] **Step 1: Write forms.py**

```python
from django import forms
from django.forms import inlineformset_factory

from apps.master_data.models import Akun

from .models import PiutangAttachment, PiutangDetail, PiutangHeader, PiutangPenerimaan


class PiutangHeaderForm(forms.ModelForm):
    class Meta:
        model = PiutangHeader
        fields = [
            'tanggal', 'debitur', 'deskripsi', 'jatuh_tempo',
            'jenis_jangka_waktu', 'coa_piutang_account', 'requires_approval',
            'jenis_bunga', 'bunga_persen', 'jumlah_angsuran', 'periode_angsuran',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'debitur': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama debitur'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'jatuh_tempo': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jenis_jangka_waktu': forms.Select(attrs={'class': 'ni-input'}),
            'coa_piutang_account': forms.Select(attrs={'class': 'ni-input'}),
            'requires_approval': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
            'jenis_bunga': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_bunga'}),
            'bunga_persen': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
            'jumlah_angsuran': forms.NumberInput(attrs={'class': 'ni-input', 'min': '1'}),
            'periode_angsuran': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['requires_approval'].required = False
        self.fields['jumlah_angsuran'].required = False
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
                  'metode_penerimaan', 'nomor_referensi', 'catatan', 'angsuran_no']
        widgets = {
            'tanggal_terima': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jumlah_diterima': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'metode_penerimaan': forms.Select(attrs={'class': 'ni-input'}),
            'nomor_referensi': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'No. transfer / cek'}),
            'catatan': forms.TextInput(attrs={'class': 'ni-input'}),
            'angsuran_no': forms.NumberInput(attrs={'class': 'ni-input', 'min': '1'}),
        }

    def __init__(self, *args, piutang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nomor_referensi'].required = False
        self.fields['catatan'].required = False
        self.fields['angsuran_no'].required = False
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
```

- [ ] **Step 2: Run check**

```bash
python manage.py check
```

- [ ] **Step 3: Commit**

```bash
git add apps/piutang/forms.py
git commit -m "feat(piutang): add forms"
```

---

## Task 9: URLs + Views skeleton

**Files:**
- Rewrite: `apps/piutang/urls.py`
- Rewrite: `apps/piutang/views.py`
- Modify: `naveda_integra/urls.py`

- [ ] **Step 1: Write urls.py**

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
    path('<int:pk>/submit-approval/', views.piutang_submit_approval, name='submit_approval'),
    path('<int:pk>/approve/', views.piutang_approve, name='approve'),
    path('<int:pk>/reject/', views.piutang_reject, name='reject'),
    path('<int:pk>/penerimaan/<int:ppk>/cancel/', views.piutang_penerimaan_cancel, name='penerimaan_cancel'),
    path('<int:pk>/write-off/', views.piutang_write_off, name='write_off'),
    path('<int:pk>/reklasifikasi/', views.piutang_reklasifikasi_post, name='reklasifikasi_post'),
    path('<int:pk>/reklasifikasi/<int:rkl_pk>/reverse/', views.piutang_reklasifikasi_reverse, name='reklasifikasi_reverse'),
    path('<int:pk>/attachments/upload/', views.piutang_attachment_upload, name='attachment_upload'),
    path('<int:pk>/attachments/<int:apk>/delete/', views.piutang_attachment_delete, name='attachment_delete'),
    path('reports/aging/', views.piutang_report_aging, name='report_aging'),
    path('reports/subjek/', views.piutang_report_subjek, name='report_subjek'),
    path('reports/jatuh-tempo/', views.piutang_report_jatuh_tempo, name='report_jatuh_tempo'),
    path('reports/write-off/', views.piutang_report_write_off, name='report_write_off'),
]
```

- [ ] **Step 2: Write views.py** (full implementation below — mirrors utang views pattern)

```python
from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    PiutangAttachmentForm, PiutangDetailFormSet, PiutangHeaderForm,
    PiutangPenerimaanForm, PiutangReklasifikasiForm, PiutangWriteOffForm,
)
from .models import PiutangAttachment, PiutangHeader, PiutangPenerimaan, PiutangReklasifikasi
from .services import (
    compute_angsuran_schedule, compute_bagian_lancar,
    create_manual_piutang, create_piutang_payment,
    get_piutang_aging, get_piutang_dashboard_kpi,
    reverse_piutang_payment, write_off_piutang,
)


@login_required
def piutang_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_piutang_dashboard_kpi()
    buckets = get_piutang_aging()
    due_soon = list(
        PiutangHeader.objects
        .filter(status__in=('open', 'partial'), jatuh_tempo__lte=timezone.now().date())
        .order_by('jatuh_tempo')[:20]
    )
    return render(request, 'piutang/dashboard.html', {
        'kpi': kpi, 'buckets': buckets, 'due_soon': due_soon,
    })


@login_required
def piutang_list(request: HttpRequest) -> HttpResponse:
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

    qs = PiutangHeader.objects.select_related('entitas_bisnis').order_by('-tanggal', '-created_at')
    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(nomor_piutang__icontains=search) | Q(debitur__icontains=search) | Q(deskripsi__icontains=search)
        )
    return render(request, 'piutang/list.html', {
        'piutangs': list(qs),
        'tanggal_dari': tanggal_dari, 'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter, 'search': search,
        'status_choices': PiutangHeader.STATUS_CHOICES,
    })


@login_required
def piutang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST)
        formset = PiutangDetailFormSet(request.POST, prefix='details')
        if form.is_valid() and formset.is_valid():
            details = [
                {'deskripsi': f.cleaned_data.get('deskripsi', ''),
                 'jumlah': f.cleaned_data['jumlah'],
                 'revenue_account': f.cleaned_data.get('revenue_account')}
                for f in formset
                if f.cleaned_data and not f.cleaned_data.get('DELETE', False)
            ]
            if not details:
                form.add_error(None, 'Minimal satu detail diperlukan.')
            else:
                try:
                    cd = form.cleaned_data
                    piutang = create_manual_piutang(
                        tanggal=cd['tanggal'], entitas_bisnis=None,
                        debitur=cd.get('debitur', ''), deskripsi=cd.get('deskripsi', ''),
                        coa_piutang_account=cd['coa_piutang_account'],
                        jatuh_tempo=cd.get('jatuh_tempo'),
                        details=details,
                        jenis_jangka_waktu=cd['jenis_jangka_waktu'],
                        requires_approval=cd.get('requires_approval', False),
                        jenis_bunga=cd.get('jenis_bunga', 'tanpa_bunga'),
                        bunga_persen=cd.get('bunga_persen') or Decimal('0'),
                        jumlah_angsuran=cd.get('jumlah_angsuran'),
                        periode_angsuran=cd.get('periode_angsuran', 'bulanan'),
                        user=request.user,
                    )
                    dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil dibuat.')
                    return redirect('piutang:detail', pk=piutang.pk)
                except ValueError as exc:
                    form.add_error(None, str(exc))
        return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'create'})
    form = PiutangHeaderForm()
    formset = PiutangDetailFormSet(prefix='details', queryset=PiutangHeader.objects.none())
    return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'create'})


@login_required
def piutang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.master_data.models import Akun
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
    angsuran_schedule = compute_angsuran_schedule(piutang) if piutang.jumlah_angsuran else []
    bagian_lancar = compute_bagian_lancar(piutang) if piutang.can_reklasifikasi else None
    akun_piutang_list = list(Akun.objects.filter(kategori_id='aset').order_by('kode_akun'))
    return render(request, 'piutang/detail.html', {
        'piutang': piutang,
        'penerimaan_form': penerimaan_form,
        'attachment_form': attachment_form,
        'angsuran_schedule': angsuran_schedule,
        'bagian_lancar': bagian_lancar,
        'akun_piutang_list': akun_piutang_list,
        'write_off_form': PiutangWriteOffForm(initial={'tanggal': timezone.now().date()}),
        'reklasifikasi_form': PiutangReklasifikasiForm(initial={'tanggal': timezone.now().date()}),
    })


@login_required
def piutang_update(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if piutang.status != 'draft':
        dj_messages.error(request, 'Hanya piutang berstatus Draft yang dapat diedit.')
        return redirect('piutang:detail', pk=pk)
    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST, instance=piutang)
        formset = PiutangDetailFormSet(request.POST, prefix='details', instance=piutang)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            dj_messages.success(request, 'Piutang berhasil diperbarui.')
            return redirect('piutang:detail', pk=pk)
        return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang})
    form = PiutangHeaderForm(instance=piutang)
    formset = PiutangDetailFormSet(prefix='details', instance=piutang)
    return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang})


@login_required
def piutang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        nomor = piutang.nomor_piutang
        piutang.delete()
        dj_messages.success(request, f'Piutang {nomor} dihapus.')
        return redirect('piutang:list')
    return render(request, 'piutang/delete.html', {'piutang': piutang})


@login_required
def piutang_terima(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangPenerimaanForm(request.POST, piutang_header=piutang)
        if form.is_valid():
            try:
                create_piutang_payment(piutang, form.cleaned_data, user=request.user)
                dj_messages.success(request, 'Penerimaan berhasil dicatat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_penerimaan_cancel(request: HttpRequest, pk: int, ppk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    penerimaan = get_object_or_404(PiutangPenerimaan, pk=ppk, piutang_header=piutang)
    if request.method == 'POST':
        reverse_piutang_payment(penerimaan, user=request.user)
        dj_messages.success(request, 'Penerimaan berhasil dibatalkan.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_write_off(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangWriteOffForm(request.POST)
        if form.is_valid():
            try:
                write_off_piutang(piutang, form.cleaned_data, user=request.user)
                dj_messages.success(request, f'Piutang {piutang.nomor_piutang} dihapusbukukan.')
                return redirect('piutang:detail', pk=pk)
            except ValueError as exc:
                dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_submit_approval(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        if piutang.status != 'draft' or not piutang.requires_approval:
            dj_messages.error(request, 'Tidak dapat diajukan.')
        else:
            piutang.approval_status = 'pending'
            piutang.save(update_fields=['approval_status'])
            dj_messages.success(request, 'Diajukan untuk persetujuan.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_approve(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        piutang.approval_status = 'approved'
        piutang.approved_by = request.user
        piutang.approved_at = timezone.now()
        piutang.status = 'open'
        piutang.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'status'])
        dj_messages.success(request, 'Piutang disetujui.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reject(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        piutang.approval_status = 'rejected'
        piutang.save(update_fields=['approval_status'])
        dj_messages.warning(request, 'Piutang ditolak.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_post(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangReklasifikasiForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            from apps.jurnal.models import JurnalDetail, JurnalHeader
            nomor = f'TRX-PIU-RKL-{piutang.pk}'
            jurnal = JurnalHeader.objects.create(
                tanggal=cd['tanggal'],
                nomor_transaksi=nomor,
                uraian_transaksi=f'Reklasifikasi Piutang {piutang.nomor_piutang}',
                entitas_bisnis=piutang.entitas_bisnis,
                is_penyesuaian=False,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=jurnal, akun=cd['dari_akun'], debit=Decimal('0'), kredit=cd['jumlah']),
                JurnalDetail(jurnal_header=jurnal, akun=cd['ke_akun'], debit=cd['jumlah'], kredit=Decimal('0')),
            ])
            PiutangReklasifikasi.objects.create(
                piutang_header=piutang, tanggal=cd['tanggal'],
                dari_akun=cd['dari_akun'], ke_akun=cd['ke_akun'],
                jumlah=cd['jumlah'], keterangan=cd.get('keterangan', ''),
                jurnal=jurnal, created_by=request.user,
            )
            dj_messages.success(request, 'Reklasifikasi berhasil dicatat.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_reverse(request: HttpRequest, pk: int, rkl_pk: int) -> HttpResponse:
    rkl = get_object_or_404(PiutangReklasifikasi, pk=rkl_pk, piutang_header_id=pk)
    if request.method == 'POST':
        from apps.jurnal.models import JurnalDetail, JurnalHeader
        orig = rkl.jurnal
        rev = JurnalHeader.objects.create(
            tanggal=timezone.now().date(),
            nomor_transaksi=f'TRX-PIU-RKLR-{rkl.pk}',
            uraian_transaksi=f'Reversal Reklasifikasi {rkl.piutang_header.nomor_piutang}',
            entitas_bisnis=rkl.piutang_header.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=rev, akun=d.akun, debit=d.kredit, kredit=d.debit)
            for d in orig.details.all()
        ])
        dj_messages.success(request, 'Reklasifikasi dibalik.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_attachment_upload(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.piutang_header = piutang
            att.uploaded_by = request.user
            att.save()
            dj_messages.success(request, 'Lampiran berhasil diunggah.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_attachment_delete(request: HttpRequest, pk: int, apk: int) -> HttpResponse:
    att = get_object_or_404(PiutangAttachment, pk=apk, piutang_header_id=pk)
    if request.method == 'POST':
        att.delete()
        dj_messages.success(request, 'Lampiran dihapus.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_piutang_aging()
    return render(request, 'piutang/report_aging.html', {'buckets': buckets})


@login_required
def piutang_report_subjek(request: HttpRequest) -> HttpResponse:
    from django.db.models import Sum
    rows = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .values('debitur', 'entitas_bisnis__nama')
        .annotate(total=Sum('jumlah_pokok'), terbayar=Sum('jumlah_terbayar'))
        .order_by('-total')
    )
    return render(request, 'piutang/report_subjek.html', {'rows': rows})


@login_required
def piutang_report_jatuh_tempo(request: HttpRequest) -> HttpResponse:
    from datetime import timedelta
    today = timezone.now().date()
    due_30 = list(PiutangHeader.objects.filter(
        status__in=('open', 'partial'), jatuh_tempo__range=(today, today + timedelta(days=30))
    ).order_by('jatuh_tempo'))
    return render(request, 'piutang/report_jatuh_tempo.html', {'due_30': due_30, 'today': today})


@login_required
def piutang_report_write_off(request: HttpRequest) -> HttpResponse:
    from .models import PiutangWriteOff
    write_offs = PiutangWriteOff.objects.select_related('piutang_header', 'created_by').order_by('-tanggal')
    return render(request, 'piutang/report_write_off.html', {'write_offs': write_offs})
```

- [ ] **Step 3: Register in root urls.py**

In `naveda_integra/urls.py`, add before the dashboard line:

```python
path('piutang/', include('apps.piutang.urls', namespace='piutang')),
```

- [ ] **Step 4: Run check**

```bash
python manage.py check
```

Expected: `System check identified no issues`

- [ ] **Step 5: Commit**

```bash
git add apps/piutang/urls.py apps/piutang/views.py apps/piutang/forms.py naveda_integra/urls.py
git commit -m "feat(piutang): add urls, views, and forms"
```

---

## Task 10: Templates

**Files:**
- Create: all `templates/piutang/*.html`

The piutang templates mirror the utang templates. For each file, copy the corresponding utang template and adapt as follows:

- [ ] **Step 1: Create template directory**

```bash
mkdir -p templates/piutang
```

- [ ] **Step 2: Create templates/piutang/list.html**

Copy `templates/utang/list.html`. Adapt:
- Replace all `utang` → `piutang`
- Replace `Utang` → `Piutang`
- Replace `Kreditor` → `Debitur`
- Replace `nomor_utang` → `nomor_piutang`
- Table columns: Nomor Piutang, Tanggal, Debitur, Jumlah Pokok, Sisa, Jatuh Tempo, Status

- [ ] **Step 3: Create templates/piutang/form.html**

Copy `templates/utang/form.html`. Adapt:
- Replace field names to match `PiutangHeaderForm` and `PiutangDetailFormSet`
- Title: "Buat Piutang" / "Edit Piutang"
- Detail columns: Deskripsi, Jumlah, Akun Pendapatan (opsional)

- [ ] **Step 4: Create templates/piutang/detail.html**

Copy `templates/utang/detail.html`. Adapt:
- Replace payment section label: "Penerimaan" instead of "Pembayaran"
- Add Write-Off section (modal/section with `PiutangWriteOffForm` — rendered after penerimaan section)
- Add Reklasifikasi section (same structure as utang)
- Source badge: show source_type (manual/from_sales/from_pendapatan) with linked nomor if available

- [ ] **Step 5: Create remaining templates**

For each remaining template, copy utang equivalent and do text substitution:
- `templates/piutang/dashboard.html` — from `templates/utang/dashboard.html`, adapt KPI card labels (Outstanding/Overdue/Collected/Collection Rate)
- `templates/piutang/delete.html` — from `templates/utang/delete.html`
- `templates/piutang/report_aging.html` — from `templates/utang/report_aging.html`
- `templates/piutang/report_subjek.html` — from `templates/utang/report_subjek.html`, rename "Kreditor" → "Debitur"
- `templates/piutang/report_jatuh_tempo.html` — from `templates/utang/report_jatuh_tempo.html`
- `templates/piutang/report_write_off.html` — new table: Date, Nomor Piutang, Debitur, Jumlah, Metode, Alasan

- [ ] **Step 6: Smoke test — start server and visit /piutang/**

```bash
python manage.py runserver
```

Navigate to `http://127.0.0.1:8000/piutang/`. Verify: list page loads, create form loads, no 500 errors.

- [ ] **Step 7: Commit**

```bash
git add templates/piutang/
git commit -m "feat(piutang): add templates"
```

---

## Task 11: Full test suite run

- [ ] **Step 1: Run all piutang tests**

```bash
python manage.py test apps.piutang -v 2
```

Expected: all tests PASS, 0 failures.

- [ ] **Step 2: Run full project check**

```bash
python manage.py test --failfast 2>&1 | tail -5
```

Expected: no regressions.
