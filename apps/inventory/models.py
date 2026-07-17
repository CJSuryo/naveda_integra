"""Inventory models."""
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.utils import timezone


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
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_records_lv2',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_records_lv3',
        verbose_name='Entitas Bisnis Lv3',
    )
    selling_price = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Harga Jual',
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity')
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Unit Cost')
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
            models.Index(fields=['entitas_bisnis_lv3'], name='idx_ir_lv3'),
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


class Warehouse(models.Model):
    """Physical stock location, scoped to a business/tenant (EntitasBisnis lv1).

    Orthogonal to the accounting EB hierarchy: a warehouse belongs to exactly
    one business but may be used by any of that business's branches (lv2/lv3).
    """
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='warehouses', verbose_name='Bisnis (Entitas Bisnis Lv1)',
    )
    kode = models.CharField(max_length=30, editable=False, verbose_name='Kode Gudang')
    nama = models.CharField(max_length=255, verbose_name='Nama Gudang')
    alamat = models.TextField(blank=True, null=True, verbose_name='Alamat')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Gudang'
        verbose_name_plural = 'Gudang'
        unique_together = (('entitas_bisnis', 'kode'),)
        ordering = ['entitas_bisnis', 'kode']

    def __str__(self) -> str:
        return f'{self.kode} — {self.nama}'

    def save(self, *args, **kwargs):
        if not self.kode:
            self.kode = self._generate_kode()
        super().save(*args, **kwargs)

    def _generate_kode(self) -> str:
        """Generate sequential warehouse code: GDG-{entitas_bisnis_id}-{seq}."""
        pattern = f'GDG-{self.entitas_bisnis_id}-'

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                Warehouse.objects
                .select_for_update()
                .filter(entitas_bisnis_id=self.entitas_bisnis_id, kode__startswith=pattern)
                .order_by('-kode')
                .values_list('kode', flat=True)
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


class StockMovement(models.Model):
    """Append-only authoritative stock ledger.

    Inflow rows (qty > 0) carry remaining_qty (FIFO layer). Outflow rows
    (qty < 0) have remaining_qty = 0 and link to consumed inflow layers via
    StockConsumption. Isolated per Entitas Bisnis (hierarchical).
    """
    MOVEMENT_TYPE_CHOICES = [
        ('purchase_in', 'Pembelian Masuk'),
        ('sale_out', 'Penjualan Keluar'),
        ('production_in', 'Produksi Masuk (FG)'),
        ('production_out', 'Produksi Keluar (RM)'),
        ('saldo_awal', 'Saldo Awal'),
        ('adjustment_in', 'Penyesuaian Masuk'),
        ('adjustment_out', 'Penyesuaian Keluar'),
        ('opname_in', 'Opname Surplus'),
        ('opname_out', 'Opname Minus'),
        ('transfer_in', 'Transfer Masuk'),
        ('transfer_out', 'Transfer Keluar'),
        ('return_customer', 'Retur Pelanggan (Masuk)'),
        ('return_supplier', 'Retur Supplier (Keluar)'),
    ]
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase', on_delete=models.PROTECT,
        related_name='stock_movements', verbose_name='Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT,
        related_name='stock_movements', verbose_name='Entitas Bisnis',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements_lv2',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements_lv3',
        verbose_name='Entitas Bisnis Lv3',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movements',
        verbose_name='Gudang',
    )
    tanggal = models.DateField(db_index=True, verbose_name='Tanggal')
    movement_type = models.CharField(
        max_length=20, choices=MOVEMENT_TYPE_CHOICES, db_index=True,
        verbose_name='Jenis Pergerakan',
    )
    qty = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name='Qty (signed, base uom)',
    )
    unit_cost = models.DecimalField(
        max_digits=19, decimal_places=4, verbose_name='Biaya Satuan',
    )
    remaining_qty = models.DecimalField(
        max_digits=15, decimal_places=4, default=Decimal('0'),
        verbose_name='Sisa Qty (layer inflow)',
    )
    source_content_type = models.ForeignKey(
        'contenttypes.ContentType', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey('source_content_type', 'source_object_id')
    legacy_fifo_batch = models.ForeignKey(
        'purchase.FIFOBatch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='FIFOBatch (mirror)',
    )
    legacy_inventory_record = models.ForeignKey(
        'inventory.InventoryRecord', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements', verbose_name='InventoryRecord (mirror)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        ordering = ['tanggal', 'created_at']
        indexes = [
            models.Index(fields=['item', 'entitas_bisnis', 'remaining_qty'],
                         name='idx_sm_item_eb_remaining'),
            models.Index(fields=['item', 'entitas_bisnis_lv2', 'remaining_qty'],
                         name='idx_sm_item_lv2_remaining'),
            models.Index(fields=['item', 'entitas_bisnis_lv3', 'remaining_qty'],
                         name='idx_sm_item_lv3_remaining'),
            models.Index(fields=['item', 'tanggal'], name='idx_sm_item_tanggal'),
            models.Index(fields=['source_content_type', 'source_object_id'],
                         name='idx_sm_source'),
            models.Index(fields=['item', 'warehouse', 'remaining_qty'],
                         name='idx_sm_item_wh_remaining'),
        ]

    def __str__(self) -> str:
        return f'{self.item.item_id} | {self.movement_type} | {self.qty}'


class StockConsumption(models.Model):
    """Allocation linking an outflow movement to the inflow layer it consumed."""
    out_movement = models.ForeignKey(
        StockMovement, on_delete=models.CASCADE, related_name='consumptions_out',
        verbose_name='Movement Keluar',
    )
    in_movement = models.ForeignKey(
        StockMovement, on_delete=models.PROTECT, related_name='consumptions_in',
        verbose_name='Layer Inflow',
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Qty Dialokasikan')
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Biaya Layer')

    class Meta:
        verbose_name = 'Stock Consumption'
        verbose_name_plural = 'Stock Consumptions'
        indexes = [
            models.Index(fields=['out_movement'], name='idx_sc_out'),
            models.Index(fields=['in_movement'], name='idx_sc_in'),
        ]

    def __str__(self) -> str:
        return f'{self.out_movement_id} → {self.in_movement_id} × {self.qty}'


class _NomorMixin:
    """Helper penghasil nomor TRX-<PREFIX>-NNN, aman-konkuren."""
    NOMOR_PREFIX = ''

    def _generate_nomor(self):
        from django.db import transaction as _t
        with _t.atomic():
            last = (
                type(self).objects.select_for_update()
                .filter(nomor__startswith=self.NOMOR_PREFIX)
                .order_by('-nomor').values_list('nomor', flat=True).first()
            )
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
            except (ValueError, IndexError):
                seq = 1
            return f'{self.NOMOR_PREFIX}{seq:03d}'


class StockAdjustment(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-ADJ-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='stock_adjustments')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_adjustments')
    akun_selisih = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='stock_adjustments', verbose_name='Akun Selisih Persediaan')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Adjustment'
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockAdjustmentItem(models.Model):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4, help_text='Bertanda: + naik, - turun')
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0, help_text='Untuk kenaikan')
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def __str__(self):
        return f'{self.item.item_id} × {self.qty}'


class StockOpname(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-OPN-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='stock_opnames')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_opnames')
    akun_selisih = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='stock_opnames')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Opname'
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockOpnameItem(models.Model):
    opname = models.ForeignKey(StockOpname, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty_sistem = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    qty_fisik = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    selisih = models.DecimalField(max_digits=15, decimal_places=4, default=0, editable=False)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    def save(self, *args, **kwargs):
        self.selisih = (self.qty_fisik or 0) - (self.qty_sistem or 0)
        super().save(*args, **kwargs)


class StockTransfer(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-TRF-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    eb_asal = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='transfers_asal')
    eb_asal_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_asal_lv2')
    eb_asal_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_asal_lv3')
    warehouse_asal = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='transfers_out')
    eb_tujuan = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='transfers_tujuan')
    eb_tujuan_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_tujuan_lv2')
    eb_tujuan_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers_tujuan_lv3')
    warehouse_tujuan = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='transfers_in')
    akun_perantara = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, null=True, blank=True, related_name='transfers', help_text='Wajib bila lintas entitas (EB lv1 berbeda).')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header_asal = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    jurnal_header_tujuan = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Transfer'
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    @property
    def is_cross_entity(self):
        return self.eb_asal_id != self.eb_tujuan_id

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class StockTransferItem(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement_out = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    movement_in = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')


class ReturCustomer(_NomorMixin, models.Model):
    NOMOR_PREFIX = 'TRX-RTC-'
    STATUS_CHOICES = [('draft', 'Draft'), ('posted', 'Diposting')]
    nomor = models.CharField(max_length=30, unique=True, editable=False)
    tanggal = models.DateField()
    sales_header = models.ForeignKey('sales.SalesHeader', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers')
    entitas_bisnis = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.PROTECT, related_name='retur_customers')
    entitas_bisnis_lv2 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv2', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers_lv2')
    entitas_bisnis_lv3 = models.ForeignKey('entitas_bisnis.EntitasBisnisLv3', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers_lv3')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_customers')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    keterangan = models.TextField(blank=True)
    jurnal_header = models.ForeignKey('jurnal.JurnalHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Retur Pelanggan'
        ordering = ['-tanggal', '-created_at']

    def __str__(self):
        return self.nomor

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        super().save(*args, **kwargs)


class ReturCustomerItem(models.Model):
    retur = models.ForeignKey(ReturCustomer, on_delete=models.CASCADE, related_name='items')
    sales_item = models.ForeignKey('sales.SalesItem', on_delete=models.PROTECT, null=True, blank=True, related_name='retur_items')
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.PROTECT, related_name='+')
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0, help_text='Biaya HPP asli dari transaksi penjualan')
    harga_jual = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    movement = models.ForeignKey('inventory.StockMovement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
