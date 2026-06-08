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
            models.Index(fields=['pendapatan_header', 'entitas_bisnis'], name='idx_pend_eb_header_eb'),
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
            models.Index(fields=['pendapatan_eb'], name='idx_pend_pi_eb'),
            models.Index(fields=['sub_transaction_type'], name='idx_pend_pi_stt'),
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
