"""Inventory models."""
from django.db import models
from django.utils import timezone


class MutasiInventoryHeader(models.Model):
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='mutasi_inventory_headers',
    )
    dll = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Mutasi Inventory Header'
        verbose_name_plural = 'Mutasi Inventory Header'
        indexes = [
            # Per-entity inventory mutation lookups
            models.Index(fields=['entitas_bisnis'], name='idx_mih_entitas'),
        ]

    def __str__(self) -> str:
        return f'MutasiInventory {self.id} - {self.entitas_bisnis}'


class MutasiInventoryDetail(models.Model):
    mutasi_inventory_header = models.ForeignKey(MutasiInventoryHeader, on_delete=models.CASCADE, related_name='details')
    dll = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Mutasi Inventory Detail'
        verbose_name_plural = 'Mutasi Inventory Detail'

    def __str__(self) -> str:
        return f'Detail {self.id} - Header {self.mutasi_inventory_header_id}'


class InventoryRecord(models.Model):
    """Inventory record — one entry per purchase line item.

    Numbering: RM-XXX-YYY, FG-XXX-YYY, ITM-XXX-YYY
    where XXX = item_id suffix (4-digit), YYY = sequential inventory number.
    """
    METODE_ALOKASI_CHOICES = [
        ('fifo', 'FIFO (First In First Out)'),
        ('lifo', 'LIFO (Last In First Out)'),
        ('avg', 'Rata-Rata Tertimbang (Weighted Average)'),
        ('specific', 'Identifikasi Khusus (Specific Identification)'),
    ]
    inventory_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name='Inventory Number',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='inventory_records',
        verbose_name='Item Master',
    )
    purchase_item = models.ForeignKey(
        'purchase.PurchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_records',
        verbose_name='Purchase Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='inventory_records',
        verbose_name='Entitas Bisnis',
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity')
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Unit Price')
    total_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        editable=False,
        default=0,
        verbose_name='Total Value',
    )
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, verbose_name='Lead Time (Days)')
    ordering_cost = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True, verbose_name='Ordering Cost',
    )
    holding_cost_pct = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        verbose_name='Holding Cost %', help_text='Contoh: 0.1 = 10%',
    )
    moq = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name='MOQ',
    )
    metode_alokasi = models.CharField(
        max_length=50,
        choices=METODE_ALOKASI_CHOICES,
        blank=True,
        default='',
        verbose_name='Metode Alokasi Biaya',
    )
    tanggal_kadaluarsa = models.DateField(
        null=True,
        blank=True,
        verbose_name='Tanggal Kadaluarsa',
        help_text='Tanggal kadaluarsa item. Otomatis dihitung dari lama_kadaluarsa item master jika tidak diisi manual.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Inventory Record'
        verbose_name_plural = 'Inventory Records'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['item', 'tanggal'], name='idx_ir_item_tanggal'),
            models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_ir_eb_tanggal'),
            models.Index(fields=['inventory_number'], name='idx_ir_inv_number'),
        ]

    def __str__(self) -> str:
        return self.inventory_number

    def save(self, *args, **kwargs):
        self.total_value = self.quantity * self.unit_price
        if not self.inventory_number:
            self.inventory_number = self._generate_inventory_number()
        super().save(*args, **kwargs)

    def _generate_inventory_number(self) -> str:
        """Generate sequential inventory number: PREFIX-XXXX-YYY."""
        prefix = self.item.tipe_item  # RM, FG, ITM
        item_suffix = self.item.item_id.split('-', 1)[1] if '-' in self.item.item_id else '0001'
        pattern = f'{prefix}-{item_suffix}-'

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                InventoryRecord.objects
                .select_for_update()
                .filter(inventory_number__startswith=pattern)
                .order_by('-inventory_number')
                .values_list('inventory_number', flat=True)
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
