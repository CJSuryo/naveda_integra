"""Aset Lainnya (Other Assets) models."""
from django.db import models
from django.utils import timezone


class AsetLainnyaRecord(models.Model):
    """Other asset record — one entry per purchased other-asset item."""
    METODE_AMORTISASI_CHOICES = [
        ('straight_line', 'Garis Lurus (Straight Line)'),
        ('declining_balance', 'Saldo Menurun (Declining Balance)'),
        ('units_of_production', 'Unit Produksi (Units of Production)'),
        ('revenue_based', 'Berbasis Pendapatan (Revenue Based)'),
    ]

    aset_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name='Nomor Aset',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='aset_lainnya_records',
        verbose_name='Item Master',
        limit_choices_to={'tipe_item': 'ALL'},
    )
    purchase_item = models.ForeignKey(
        'purchase.PurchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='aset_lainnya_records',
        verbose_name='Purchase Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='aset_lainnya_records',
        verbose_name='Entitas Bisnis',
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=1,
        verbose_name='Quantity',
    )
    harga_perolehan = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Harga Perolehan',
    )
    total_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        editable=False,
        default=0,
        verbose_name='Nilai Perolehan',
    )
    akumulasi_amortisasi = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Akumulasi Amortisasi',
    )
    nilai_residu = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Nilai Residu',
        help_text='Nilai sisa aset di akhir masa manfaat.',
    )
    estimasi_unit_produksi = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Estimasi Total Unit Produksi',
        help_text='Total estimasi unit produksi selama masa manfaat (untuk metode Units of Production).',
    )
    tanggal_perolehan = models.DateField(
        db_index=True,
        default=timezone.now,
        verbose_name='Tanggal Perolehan',
    )
    masa_manfaat = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Masa Manfaat (Tahun)',
        help_text='Override masa manfaat dari item master. Kosongkan untuk menggunakan nilai item master.',
    )
    metode_amortisasi = models.CharField(
        max_length=30,
        choices=METODE_AMORTISASI_CHOICES,
        blank=True,
        default='',
        verbose_name='Metode Amortisasi',
        help_text='Override metode amortisasi dari item master.',
    )
    keterangan = models.TextField(
        blank=True,
        verbose_name='Keterangan',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Aset Lainnya Record'
        verbose_name_plural = 'Aset Lainnya Records'
        ordering = ['-tanggal_perolehan', '-created_at']
        indexes = [
            models.Index(fields=['item', 'tanggal_perolehan'], name='idx_alr_item_tanggal'),
            models.Index(fields=['entitas_bisnis', 'tanggal_perolehan'], name='idx_alr_eb_tanggal'),
            models.Index(fields=['aset_number'], name='idx_alr_number'),
        ]

    def __str__(self) -> str:
        return self.aset_number

    @property
    def nilai_buku(self):
        return self.total_value - self.akumulasi_amortisasi

    def save(self, *args, **kwargs):
        self.total_value = self.quantity * self.harga_perolehan
        if not self.aset_number:
            self.aset_number = self._generate_aset_number()
        super().save(*args, **kwargs)

    def _generate_aset_number(self) -> str:
        """Generate sequential aset number: ALL-XXXX-YYY."""
        item_suffix = self.item.item_id.split('-', 1)[1] if '-' in self.item.item_id else '0001'
        pattern = f'ALL-{item_suffix}-'

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                AsetLainnyaRecord.objects
                .select_for_update()
                .filter(aset_number__startswith=pattern)
                .order_by('-aset_number')
                .values_list('aset_number', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'{pattern}{seq:03d}'
