from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone


JENIS_UTANG_CHOICES = [
    ('usaha', 'Utang Usaha'),
    ('bank', 'Pinjaman Bank'),
    ('leasing', 'Leasing'),
    ('pajak', 'Utang Pajak'),
    ('gaji', 'Utang Gaji'),
    ('pemegang_saham', 'Pinjaman Pemegang Saham'),
    ('antar_entitas', 'Utang Antar Entitas'),
    ('lainnya', 'Lainnya'),
]

JENIS_JANGKA_WAKTU_CHOICES = [
    ('short_term', 'Jangka Pendek'),
    ('long_term', 'Jangka Panjang'),
]

JENIS_DOKUMEN_CHOICES = [
    ('invoice', 'Invoice'),
    ('kontrak', 'Kontrak'),
    ('spk', 'SPK'),
    ('perjanjian', 'Perjanjian Kredit'),
    ('berita_acara', 'Berita Acara'),
    ('kuitansi', 'Kuitansi'),
    ('lainnya', 'Lainnya'),
]


class UtangHeader(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('waiting_approval', 'Menunggu Persetujuan'),
        ('open', 'Terbuka'),
        ('partial', 'Sebagian Dibayar'),
        ('paid', 'Lunas'),
        ('overdue', 'Jatuh Tempo'),
        ('cancelled', 'Dibatalkan'),
        ('written_off', 'Dihapusbukukan'),
    ]
    APPROVAL_STATUS_CHOICES = [
        ('', '-'),
        ('pending', 'Menunggu'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
    ]

    # ── Core (existing) ──────────────────────────────────────────────────────
    purchase_header = models.ForeignKey(
        'purchase.PurchaseHeader',
        on_delete=models.CASCADE,
        related_name='utang_headers',
        null=True, blank=True,
        verbose_name='Purchase Header',
    )
    nomor_utang = models.CharField(max_length=100, unique=True, editable=False, verbose_name='Nomor Utang')
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='utang_headers',
        verbose_name='Entitas Bisnis',
    )
    deskripsi = models.CharField(max_length=512, blank=True, default='', verbose_name='Deskripsi')
    total_amount = models.DecimalField(max_digits=19, decimal_places=4, default=0, verbose_name='Total Utang')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name='Status')
    tanggal_jatuh_tempo = models.DateField(null=True, blank=True, db_index=True, verbose_name='Tanggal Jatuh Tempo')
    is_locked = models.BooleanField(default=False, verbose_name='Terkunci')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── V1 New Fields ────────────────────────────────────────────────────────
    jenis_utang = models.CharField(
        max_length=30, choices=JENIS_UTANG_CHOICES, default='usaha',
        verbose_name='Jenis Utang',
    )
    kreditor = models.CharField(max_length=255, blank=True, default='', verbose_name='Kreditor')
    nomor_referensi = models.CharField(max_length=100, blank=True, default='', verbose_name='Nomor Referensi')
    kategori_jangka_waktu = models.CharField(
        max_length=20, choices=JENIS_JANGKA_WAKTU_CHOICES, default='short_term',
        verbose_name='Kategori Jangka Waktu',
    )
    coa_source_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='utang_sources',
        verbose_name='Akun Asal (Debet)',
    )
    requires_approval = models.BooleanField(default=False, verbose_name='Perlu Persetujuan')
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES, blank=True, default='',
        verbose_name='Status Persetujuan',
    )
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='utang_approved',
        verbose_name='Disetujui Oleh',
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Disetujui Pada')
    jurnal_pembentukan = models.ForeignKey(
        'jurnal.JurnalHeader',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='utang_pembentukan',
        verbose_name='Jurnal Pembentukan',
    )

    class Meta:
        verbose_name = 'Utang Header'
        verbose_name_plural = 'Utang Header'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='idx_utang_tanggal_status'),
            models.Index(fields=['jenis_utang', 'status'], name='idx_utang_jenis_status'),
        ]

    def __str__(self) -> str:
        return self.nomor_utang

    def save(self, *args, **kwargs):
        if not self.nomor_utang:
            self.nomor_utang = self._generate_nomor_utang()
        super().save(*args, **kwargs)

    def _generate_nomor_utang(self) -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                UtangHeader.objects
                .select_for_update()
                .filter(nomor_utang__startswith='UTG-')
                .order_by('-nomor_utang')
                .values_list('nomor_utang', flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f'UTG-{seq:04d}'

    @property
    def paid_amount(self) -> Decimal:
        result = self.pembayaran.aggregate(total=models.Sum('jumlah'))['total']
        return result or Decimal('0')

    @property
    def outstanding_amount(self) -> Decimal:
        return (self.total_amount - self.paid_amount).quantize(Decimal('0.0001'))

    @property
    def entitas_display(self) -> str:
        if self.kreditor:
            return self.kreditor
        return str(self.entitas_bisnis) if self.entitas_bisnis else '-'

    @property
    def is_overdue(self) -> bool:
        if not self.tanggal_jatuh_tempo or self.status in ('paid', 'cancelled', 'written_off'):
            return False
        return timezone.now().date() > self.tanggal_jatuh_tempo

    @property
    def days_overdue(self) -> int:
        if not self.tanggal_jatuh_tempo or self.status in ('paid', 'cancelled', 'written_off'):
            return 0
        return max(0, (timezone.now().date() - self.tanggal_jatuh_tempo).days)

    @property
    def can_edit(self) -> bool:
        return self.status in ('draft', 'waiting_approval') and not self.purchase_header_id

    @property
    def can_pay(self) -> bool:
        return self.status in ('open', 'partial', 'overdue') and not self.is_locked


class UtangDetail(models.Model):
    utang_header = models.ForeignKey(
        UtangHeader, on_delete=models.CASCADE, related_name='details',
        verbose_name='Utang Header',
    )
    purchase_item = models.ForeignKey(
        'purchase.PurchaseItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utang_details',
        verbose_name='Purchase Item',
    )
    coa_utang_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='utang_details', verbose_name='Akun Utang',
    )
    description = models.CharField(max_length=255, blank=True, default='', verbose_name='Keterangan')
    amount = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Utang')

    class Meta:
        verbose_name = 'Utang Detail'
        verbose_name_plural = 'Utang Detail'
        indexes = [
            models.Index(fields=['utang_header', 'coa_utang_account'], name='idx_ud_header_coa'),
        ]

    def __str__(self) -> str:
        return f'{self.utang_header.nomor_utang} — {self.description or self.coa_utang_account}'


class UtangPembayaran(models.Model):
    utang_header = models.ForeignKey(
        UtangHeader, on_delete=models.CASCADE, related_name='pembayaran',
        verbose_name='Utang Header',
    )
    utang_detail = models.ForeignKey(
        UtangDetail, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payments',
        verbose_name='Utang Detail',
    )
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal Pembayaran')
    coa_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='utang_payments', verbose_name='Akun Pembayaran',
    )
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Pembayaran')
    keterangan = models.CharField(max_length=512, blank=True, default='', verbose_name='Keterangan')
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utang_payments',
        verbose_name='Jurnal Pembayaran',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Utang Pembayaran'
        verbose_name_plural = 'Utang Pembayaran'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['utang_header', 'tanggal'], name='idx_up_header_tanggal'),
        ]

    def __str__(self) -> str:
        return f'Pembayaran {self.jumlah} untuk {self.utang_header.nomor_utang}'


class UtangAttachment(models.Model):
    utang_header = models.ForeignKey(
        UtangHeader, on_delete=models.CASCADE, related_name='attachments',
        verbose_name='Utang Header',
    )
    file = models.FileField(upload_to='utang/attachments/%Y/%m/', verbose_name='File')
    file_name = models.CharField(max_length=255, verbose_name='Nama File')
    jenis_dokumen = models.CharField(
        max_length=30, choices=JENIS_DOKUMEN_CHOICES, default='lainnya',
        verbose_name='Jenis Dokumen',
    )
    uploaded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utang_attachments',
        verbose_name='Diupload Oleh',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Diupload Pada')

    class Meta:
        verbose_name = 'Dokumen Utang'
        verbose_name_plural = 'Dokumen Utang'
        ordering = ['-uploaded_at']

    def __str__(self) -> str:
        return f'{self.file_name} ({self.utang_header.nomor_utang})'


class UtangAuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Dibuat'),
        ('EDIT', 'Diedit'),
        ('SUBMIT_APPROVAL', 'Diajukan Persetujuan'),
        ('APPROVE', 'Disetujui'),
        ('REJECT', 'Ditolak'),
        ('POST', 'Diposting'),
        ('PAYMENT', 'Pembayaran'),
        ('REVERSE_PAYMENT', 'Batalkan Pembayaran'),
        ('REVERSE', 'Dibalik/Dihapus'),
        ('UNLOCK', 'Dibuka Kunci'),
    ]

    utang_header = models.ForeignKey(
        UtangHeader, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_logs',
        verbose_name='Utang Header',
    )
    nomor_utang = models.CharField(max_length=100, blank=True, default='', verbose_name='Nomor Utang')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='Aksi')
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utang_audit_logs',
        verbose_name='User',
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Waktu')
    before_json = models.JSONField(default=dict, blank=True, verbose_name='Sebelum')
    after_json = models.JSONField(default=dict, blank=True, verbose_name='Sesudah')
    notes = models.CharField(max_length=512, blank=True, default='', verbose_name='Catatan')

    class Meta:
        verbose_name = 'Audit Log Utang'
        verbose_name_plural = 'Audit Log Utang'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['nomor_utang', 'timestamp'], name='idx_ual_nomor_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.action} — {self.nomor_utang} — {self.timestamp}'


class UtangTerhapus(models.Model):
    nomor_utang = models.CharField(max_length=100, verbose_name='Nomor Utang')
    uraian = models.CharField(max_length=512, blank=True, default='', verbose_name='Uraian')
    entitas_bisnis_nama = models.CharField(max_length=255, blank=True, verbose_name='Entitas Bisnis')
    tanggal = models.DateField(null=True, blank=True, verbose_name='Tanggal Utang')
    deleted_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Dihapus Pada')
    deleted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utang_terhapus',
        verbose_name='Dihapus Oleh',
    )
    snapshot = models.JSONField(default=dict, verbose_name='Snapshot Utang')

    class Meta:
        verbose_name = 'Utang Terhapus'
        verbose_name_plural = 'Utang Terhapus'
        ordering = ['-deleted_at']
        indexes = [
            models.Index(fields=['deleted_at'], name='idx_utang_terhapus_deleted'),
        ]

    def __str__(self) -> str:
        return f'{self.nomor_utang} (dihapus {self.deleted_at.date()})'
