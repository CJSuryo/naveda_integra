from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone


class UtangHeader(models.Model):
    STATUS_CHOICES = [
        ('open', 'Terbuka'),
        ('partial', 'Sebagian Dibayar'),
        ('paid', 'Lunas'),
    ]

    purchase_header = models.ForeignKey(
        'purchase.PurchaseHeader',
        on_delete=models.CASCADE,
        related_name='utang_headers',
        null=True,
        blank=True,
        verbose_name='Purchase Header',
    )
    nomor_utang = models.CharField(max_length=100, unique=True, editable=False, verbose_name='Nomor Utang')
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utang_headers',
        verbose_name='Entitas Bisnis',
    )
    deskripsi = models.CharField(max_length=512, blank=True, default='', verbose_name='Deskripsi')
    total_amount = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Total Utang',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open',
        verbose_name='Status',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Utang Header'
        verbose_name_plural = 'Utang Header'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='idx_utang_tanggal_status'),
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
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
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
        return str(self.entitas_bisnis) if self.entitas_bisnis else '-' 


class UtangDetail(models.Model):
    utang_header = models.ForeignKey(
        UtangHeader,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name='Utang Header',
    )
    purchase_item = models.ForeignKey(
        'purchase.PurchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utang_details',
        verbose_name='Purchase Item',
    )
    coa_utang_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='utang_details',
        verbose_name='Akun Utang',
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
        UtangHeader,
        on_delete=models.CASCADE,
        related_name='pembayaran',
        verbose_name='Utang Header',
    )
    utang_detail = models.ForeignKey(
        UtangDetail,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
        verbose_name='Utang Detail',
    )
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal Pembayaran')
    coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='utang_payments',
        verbose_name='Akun Pembayaran',
    )
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah Pembayaran')
    keterangan = models.CharField(max_length=512, blank=True, default='', verbose_name='Keterangan')
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utang_payments',
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


class UtangTerhapus(models.Model):
    nomor_utang = models.CharField(max_length=100, verbose_name='Nomor Utang')
    uraian = models.CharField(max_length=512, blank=True, default='', verbose_name='Uraian')
    entitas_bisnis_nama = models.CharField(max_length=255, blank=True, verbose_name='Entitas Bisnis')
    tanggal = models.DateField(null=True, blank=True, verbose_name='Tanggal Utang')
    deleted_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Dihapus Pada')
    deleted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='utang_terhapus',
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
