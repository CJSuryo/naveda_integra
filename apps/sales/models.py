"""Sales models."""
from decimal import Decimal

from django.db import models


class ItemMaster(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)
    satuan = models.CharField(max_length=50, blank=True)
    harga_pokok = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Item Master'
        verbose_name_plural = 'Item Master'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class SalesHeader(models.Model):
    STATUS_PENGIRIMAN_CHOICES = [
        ('pending', 'Pending'),
        ('dikirim', 'Dikirim'),
        ('selesai', 'Selesai'),
        ('dibatalkan', 'Dibatalkan'),
    ]

    nomor_invoice = models.CharField(max_length=100, unique=True)
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='sales_headers',
    )
    tanggal_transaksi = models.DateField(db_index=True)
    termin_pembayaran = models.CharField(max_length=50, blank=True)
    status_pengiriman = models.CharField(max_length=50, choices=STATUS_PENGIRIMAN_CHOICES, blank=True, db_index=True)
    total_nilai = models.DecimalField(max_digits=19, decimal_places=4)

    class Meta:
        verbose_name = 'Sales Header'
        verbose_name_plural = 'Sales Header'
        ordering = ['-tanggal_transaksi']
        indexes = [
            # Per-customer date-range queries (e.g. "all invoices for entity X this month")
            models.Index(fields=['entitas_bisnis', 'tanggal_transaksi'], name='idx_sh_entitas_tanggal'),
            # Fulfilment dashboard: filter by status then sort by date
            models.Index(fields=['status_pengiriman', 'tanggal_transaksi'], name='idx_sh_status_tanggal'),
        ]

    def __str__(self) -> str:
        return self.nomor_invoice


class SalesDetail(models.Model):
    sales_header = models.ForeignKey(SalesHeader, on_delete=models.CASCADE, related_name='details')
    item_master = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name='sales_details')
    kuantitas = models.DecimalField(max_digits=10, decimal_places=2)
    harga_satuan = models.DecimalField(max_digits=19, decimal_places=4)
    diskon_persen = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)

    class Meta:
        verbose_name = 'Sales Detail'
        verbose_name_plural = 'Sales Detail'
        indexes = [
            # Header→detail join with item (invoice line items)
            models.Index(fields=['sales_header', 'item_master'], name='idx_sd_header_item'),
            # Per-item sales analysis
            models.Index(fields=['item_master'], name='idx_sd_item'),
        ]

    def __str__(self) -> str:
        return f'Detail {self.id} - {self.sales_header.nomor_invoice}'

    def save(self, *args, **kwargs):
        self.subtotal = self.kuantitas * self.harga_satuan * (1 - self.diskon_persen / Decimal('100'))
        super().save(*args, **kwargs)
