from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


JENIS_JANGKA_WAKTU_CHOICES = [
    ('short_term', 'Jangka Pendek'),
    ('long_term', 'Jangka Panjang'),
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


class PiutangHeader(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Menunggu Approval'),
        ('open', 'Terbuka'),
        ('partial', 'Sebagian Diterima'),
        ('paid', 'Lunas'),
        ('overdue', 'Jatuh Tempo'),
        ('written_off', 'Dihapusbukukan'),
        ('cancelled', 'Dibatalkan'),
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
    coa_piutang_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='piutang_headers', verbose_name='Akun Piutang',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
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
    is_pv_adjusted = models.BooleanField(
        default=False, verbose_name='Disesuaikan Nilai Wajar (PV)',
    )
    pv_discount_rate = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        verbose_name='Market Rate untuk PV (%/tahun)',
    )
    nilai_wajar_awal = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Nilai Wajar Awal (PV)',
    )
    is_approval_required = models.BooleanField(
        default=False, verbose_name='Perlu Approval',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_approved', verbose_name='Disetujui Oleh',
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Disetujui Pada')
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
            return f'TRX-PIU-{seq:04d}'

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
    def can_edit(self) -> bool:
        return self.status == 'draft' and not self.is_locked

    @property
    def can_post(self) -> bool:
        return self.status == 'draft' and not self.is_locked and not self.is_approval_required

    @property
    def can_submit_approval(self) -> bool:
        return self.status == 'draft' and not self.is_locked and self.is_approval_required

    @property
    def can_approve(self) -> bool:
        return self.status == 'pending_approval' and not self.is_locked

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
    periode_bulan = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Periode Bulan',
    )
    periode_tahun = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Periode Tahun',
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=['piutang_header', 'periode_bulan', 'periode_tahun'],
                condition=models.Q(periode_bulan__isnull=False, periode_tahun__isnull=False),
                name='uniq_rkl_header_periode',
            ),
        ]

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
        ('PAYMENT', 'Penerimaan'),
        ('REVERSE_PAYMENT', 'Batalkan Penerimaan'),
        ('WRITE_OFF', 'Dihapusbukukan'),
        ('REKLASIFIKASI', 'Reklasifikasi'),
        ('CANCELLED', 'Dibatalkan'),
        ('PENYISIHAN', 'Penyisihan Piutang'),
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
    periode_label = models.CharField(
        max_length=20, blank=True, default='', db_index=True,
        verbose_name='Periode',
        help_text='YYYY-MM — diisi otomatis untuk jenis batch',
    )
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
