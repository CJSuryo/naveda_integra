"""Manufacturing models — Bill of Materials and Production Orders."""
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone


class BillOfMaterials(models.Model):
    """Bill of Materials header — one per Finished Good item."""
    bom_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name='BOM ID',
    )
    finished_good = models.OneToOneField(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='bom',
        limit_choices_to={'tipe_item__in': ['FG', 'FGB']},
        verbose_name='Finished Good',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='bills_of_materials',
        verbose_name='Entitas Bisnis',
    )
    tanggal_dibuat = models.DateField(
        default=timezone.now,
        verbose_name='Tanggal BOM Dibuat',
    )
    catatan = models.TextField(blank=True, default='', verbose_name='Catatan')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Bill of Materials'
        verbose_name_plural = 'Bill of Materials'
        indexes = [
            models.Index(fields=['entitas_bisnis', 'tanggal_dibuat'], name='idx_bom_eb_tanggal'),
        ]

    def __str__(self) -> str:
        return self.bom_id

    def save(self, *args, **kwargs):
        if not self.bom_id:
            self.bom_id = f'BOM-{self.finished_good.item_id}'
        super().save(*args, **kwargs)


class BOMLine(models.Model):
    """A single raw material entry inside a BOM."""
    bom = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='BOM',
    )
    raw_material = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='bom_lines',
        limit_choices_to={'tipe_item__in': ['RM', 'RMB']},
        verbose_name='Raw Material',
    )
    qty_required = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name='Qty per Unit FG',
    )

    class Meta:
        verbose_name = 'BOM Line'
        verbose_name_plural = 'BOM Lines'
        unique_together = [('bom', 'raw_material')]
        indexes = [
            models.Index(fields=['bom', 'raw_material'], name='idx_bomline_bom_rm'),
        ]

    def __str__(self) -> str:
        return f'{self.bom.bom_id} → {self.raw_material.item_id} × {self.qty_required}'


class ProductionOrder(models.Model):
    """A manufacturing production order."""
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Dibatalkan'),
    ]

    production_id = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
        verbose_name='Production ID',
    )
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal Produksi')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='production_orders',
        verbose_name='Entitas Bisnis',
    )
    bom = models.ForeignKey(
        BillOfMaterials,
        on_delete=models.PROTECT,
        related_name='production_orders',
        verbose_name='BOM (Finished Good)',
    )
    qty_produced = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name='Qty Diproduksi',
    )
    overhead_cost = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=Decimal('0'),
        blank=True,
        verbose_name='Overhead Cost',
    )
    rm_cost = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=Decimal('0'),
        editable=False,
        verbose_name='RM Cost',
    )
    total_cost = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=Decimal('0'),
        editable=False,
        verbose_name='Total Cost',
    )
    unit_cost = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=Decimal('0'),
        editable=False,
        verbose_name='Unit Cost FG',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name='Status',
    )
    coa_produksi = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='production_orders_wip',
        verbose_name='Akun Biaya Produksi (WIP)',
        help_text='Akun WIP yang menampung biaya produksi sementara.',
    )
    coa_overhead = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='production_orders_overhead',
        null=True,
        blank=True,
        verbose_name='Akun Overhead',
        help_text='Wajib diisi jika ada Overhead Cost.',
    )
    lead_time_days = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Lead Time (Hari)',
    )
    ordering_cost = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Ordering Cost',
    )
    holding_cost_pct = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        verbose_name='Holding Cost %',
        help_text='Contoh: 0.1 = 10%',
    )
    moq = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='MOQ',
    )
    target_turnover = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Target Turnover',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Catatan')
    is_processed = models.BooleanField(
        default=False, verbose_name='Sudah Diproses',
    )
    lama_pengerjaan = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name='Lama Pengerjaan Estimasi (Hari)',
        help_text='Opsional (WIP): estimasi jumlah hari penyelesaian sejak tanggal produksi.',
    )
    fg_inventory_record = models.OneToOneField(
        'inventory.InventoryRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_order',
        verbose_name='Inventory Record FG',
        help_text='InventoryRecord yang dibuat saat produksi diproses.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Order'
        verbose_name_plural = 'Production Orders'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_po_eb_tanggal'),
            models.Index(fields=['bom', 'tanggal'], name='idx_po_bom_tanggal'),
            models.Index(fields=['status'], name='idx_po_status'),
        ]

    def __str__(self) -> str:
        return self.production_id

    @property
    def estimated_completion_date(self):
        """Return the estimated completion date if lama_pengerjaan is set."""
        if self.lama_pengerjaan and self.tanggal:
            return self.tanggal + timedelta(days=self.lama_pengerjaan)
        return None

    @property
    def is_past_estimated_completion(self) -> bool:
        """True if the WIP order is past its estimated completion date."""
        ec = self.estimated_completion_date
        if ec is None:
            return False
        return ec <= timezone.now().date()

    def save(self, *args, **kwargs):
        if not self.production_id:
            self.production_id = self._generate_production_id()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_production_id() -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                ProductionOrder.objects
                .select_for_update()
                .filter(production_id__startswith='PROD-')
                .order_by('-production_id')
                .values_list('production_id', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'PROD-{seq:04d}'


class ProductionRMConsumption(models.Model):
    """Records FIFO batch allocations consumed per RM during a production run."""
    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name='rm_consumptions',
        verbose_name='Production Order',
    )
    bom_line = models.ForeignKey(
        BOMLine,
        on_delete=models.PROTECT,
        related_name='consumption_records',
        verbose_name='BOM Line',
    )
    fifo_batch = models.ForeignKey(
        'purchase.FIFOBatch',
        on_delete=models.PROTECT,
        related_name='production_consumptions',
        verbose_name='FIFO Batch',
    )
    qty_consumed = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name='Qty Dikonsumsi',
    )
    unit_cost = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Harga Satuan FIFO',
    )
    total_cost = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Total Biaya', editable=False,
    )

    class Meta:
        verbose_name = 'Production RM Consumption'
        verbose_name_plural = 'Production RM Consumptions'
        indexes = [
            models.Index(fields=['production_order', 'bom_line'], name='idx_prmc_po_bom'),
        ]

    def __str__(self) -> str:
        return (
            f'{self.production_order.production_id}'
            f' — {self.bom_line.raw_material.item_id} × {self.qty_consumed}'
        )

    def save(self, *args, **kwargs):
        self.total_cost = self.qty_consumed * self.unit_cost
        super().save(*args, **kwargs)
