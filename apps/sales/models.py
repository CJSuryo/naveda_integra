"""Sales models — Sales transactions with FIFO outflow, tax support, and automated journals."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class SalesHeader(models.Model):
    """Top-level sales transaction.

    Transaction ID format: TRX-SAL-XXX (auto-generated).
    """
    transaction_id = models.CharField(max_length=100, unique=True, editable=False)
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    deskripsi = models.TextField(blank=True, default='', verbose_name='Deskripsi')
    is_locked = models.BooleanField(
        default=False,
        verbose_name='Locked',
        help_text='True jika periode sudah tutup buku.',
    )
    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'Cash'), ('credit', 'Kredit')],
        default='cash',
        verbose_name='Tipe Pembayaran',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_created',
        verbose_name='Dibuat oleh',
    )

    class Meta:
        verbose_name = 'Sales Header'
        verbose_name_plural = 'Sales Headers'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'is_locked'], name='idx_nsh_tanggal_locked'),
        ]

    def __str__(self) -> str:
        return self.transaction_id

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = self._generate_transaction_id()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_transaction_id() -> str:
        from django.db import transaction as db_transaction
        prefix = 'TRX-SAL'
        with db_transaction.atomic():
            last = (
                SalesHeader.objects
                .select_for_update()
                .filter(transaction_id__startswith=f'{prefix}-')
                .order_by('-transaction_id')
                .values_list('transaction_id', flat=True)
                .first()
            )
            if last:
                try:
                    seq = int(last.rsplit('-', 1)[1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            return f'{prefix}-{seq:03d}'


class SalesEntitasBisnis(models.Model):
    """Links a sales header to a specific business entity (at any level)."""
    sales_header = models.ForeignKey(
        SalesHeader,
        on_delete=models.CASCADE,
        related_name='entitas_groups',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='sales_groups',
        verbose_name='Entitas Bisnis (Lv1)',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales_groups',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales_groups',
        verbose_name='Entitas Bisnis Lv3',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sales_eb_payment',
        verbose_name='Payment Account',
        help_text='Kas Tunai, Kas di Bank, dll. (Legacy — per-item payment_account di SalesItem lebih diutamakan).',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Sales Entitas Bisnis'
        verbose_name_plural = 'Sales Entitas Bisnis'
        indexes = [
            models.Index(fields=['sales_header', 'entitas_bisnis'], name='idx_seb_header_eb'),
            models.Index(fields=['entitas_bisnis_lv2'], name='idx_seb_lv2'),
            models.Index(fields=['entitas_bisnis_lv3'], name='idx_seb_lv3'),
        ]

    def __str__(self) -> str:
        if self.entitas_bisnis_lv3_id:
            return (
                f'{self.sales_header.transaction_id} → '
                f'{self.entitas_bisnis.nama} / {self.entitas_bisnis_lv2.nama} / {self.entitas_bisnis_lv3.nama}'
            )
        if self.entitas_bisnis_lv2_id:
            return (
                f'{self.sales_header.transaction_id} → '
                f'{self.entitas_bisnis.nama} / {self.entitas_bisnis_lv2.nama}'
            )
        return f'{self.sales_header.transaction_id} → {self.entitas_bisnis.nama}'


class SalesItem(models.Model):
    """Individual item line within a sales transaction."""
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
    sales_eb = models.ForeignKey(
        SalesEntitasBisnis,
        on_delete=models.CASCADE,
        related_name='items',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='sales_items',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType',
        on_delete=models.PROTECT,
        related_name='sales_items',
        verbose_name='Sub-Transaction Type',
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity')
    selling_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Harga Jual')
    total_sales = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        editable=False,
        default=0,
        verbose_name='Total Penjualan',
    )
    hpp_terpakai = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='HPP Terpakai (Bulk)',
        help_text='Untuk item bulk: mengurangi nilai persediaan bulk.',
    )
    # CoA accounts
    offset_coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sales_item_offset',
        verbose_name='Offset CoA (HPP)',
        help_text='HPP terkait — auto-fill dari Settings.',
    )
    revenue_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sales_item_revenue',
        verbose_name='Revenue Account',
        help_text='Pendapatan terkait item/tipe transaksi.',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sales_item_payment',
        verbose_name='Payment Account',
        null=True,
        blank=True,
    )
    # COGS computed from FIFO
    cogs_amount = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='HPP (COGS)',
        help_text='Dihitung otomatis dari FIFO outflow.',
    )
    inventory_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales_item_inventory',
        verbose_name='Inventory Account',
        help_text='Akun persediaan item (dari Item Master CoA).',
    )
    # Tax fields (optional)
    tax = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Tax (Nominal)',
    )
    tax_type = models.CharField(
        max_length=30,
        choices=TAX_TYPE_CHOICES,
        blank=True,
        default='',
        verbose_name='Tax Type',
    )
    tax_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales_item_tax',
        verbose_name='Tax Account',
    )
    tax_payment = models.CharField(
        max_length=20,
        choices=TAX_PAYMENT_CHOICES,
        blank=True,
        default='',
        verbose_name='Tax Payment Status',
    )
    tax_payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales_item_tax_payment',
        verbose_name='Tax Payment Account',
        help_text='Utang PPN Keluaran (jika belum transfer).',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse', on_delete=models.PROTECT,
        null=True, blank=True, related_name='sales_items',
        verbose_name='Gudang',
    )
    input_uom = models.ForeignKey(
        'uom.UnitOfMeasure', on_delete=models.PROTECT,
        null=True, blank=True, related_name='sales_items_input',
        verbose_name='Satuan Input',
    )
    input_qty = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name='Qty Input (satuan asli)',
    )

    class Meta:
        verbose_name = 'Sales Item'
        verbose_name_plural = 'Sales Items'
        indexes = [
            models.Index(fields=['sales_eb', 'item'], name='idx_nsi_eb_item'),
            models.Index(fields=['item'], name='idx_nsi_item'),
        ]

    def __str__(self) -> str:
        return f'{self.item.item_id} × {self.quantity}'

    def save(self, *args, **kwargs):
        BULK_TYPES = ('RMB', 'FGB', 'ITMB')
        if self.item.tipe_item in BULK_TYPES:
            # Bulk: selling_price is the total selling amount (not per-unit)
            self.total_sales = self.selling_price
        else:
            self.total_sales = self.quantity * self.selling_price
        super().save(*args, **kwargs)


# ── Tax Lines ─────────────────────────────────────────────────────────────────

TAX_TYPE_CHOICES_SALES = [
    ('ppn_keluaran', 'PPN Keluaran'),
    ('pph_23', 'PPh 23'),
    ('pph_21', 'PPh 21'),
    ('pph_4_2', 'PPh 4(2)'),
]


class SalesTaxLine(models.Model):
    sales_item = models.ForeignKey(
        SalesItem, on_delete=models.CASCADE, related_name='tax_lines',
        verbose_name='Sales Item',
    )
    tax_type = models.CharField(
        max_length=30, choices=TAX_TYPE_CHOICES_SALES, verbose_name='Tipe Pajak',
    )
    tax = models.DecimalField(
        max_digits=19, decimal_places=4, null=True, blank=True,
        verbose_name='Pajak (Nominal)',
        help_text='Nominal pajak. Hasil hitung otomatis atau override manual (lihat is_manual).',
    )
    is_manual = models.BooleanField(
        default=False, verbose_name='Override Manual',
        help_text='True jika nominal pajak diisi/diubah manual. False = dihitung ulang dari tarif.',
    )
    tax_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='sales_tax_lines_pajak', verbose_name='Akun Pajak',
    )
    tax_payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT,
        related_name='sales_tax_lines_lawan', verbose_name='Akun Lawan Pajak',
    )

    class Meta:
        verbose_name = 'Sales Tax Line'
        verbose_name_plural = 'Sales Tax Lines'
        ordering = ['id']

    def __str__(self) -> str:
        return f'SI-{self.sales_item_id} — {self.tax_type}'


class SalesItemFIFOAllocation(models.Model):
    """Per-batch FIFO allocation — records exactly which InventoryRecord batch
    was consumed by a SalesItem and in what quantity.

    Created by process_sales_fifo; cascades on SalesItem delete.
    """
    sales_item = models.ForeignKey(
        SalesItem,
        on_delete=models.CASCADE,
        related_name='fifo_allocations',
    )
    inventory_record = models.ForeignKey(
        'inventory.InventoryRecord',
        on_delete=models.CASCADE,
        related_name='sales_allocations',
    )
    quantity_consumed = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        verbose_name='Qty Consumed',
    )
    cogs_amount = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='COGS Amount',
    )

    class Meta:
        verbose_name = 'Sales FIFO Allocation'
        verbose_name_plural = 'Sales FIFO Allocations'
        indexes = [
            models.Index(fields=['sales_item'], name='idx_sfa_sales_item'),
            models.Index(fields=['inventory_record'], name='idx_sfa_inv_record'),
        ]

    def __str__(self) -> str:
        return f'{self.sales_item} → {self.inventory_record} × {self.quantity_consumed}'


class SalesEventLog(models.Model):
    EVENT_CHOICES = [
        ('CREATED', 'Dibuat'),
        ('EDITED', 'Diedit'),
        ('VOIDED', 'Dibatalkan'),
        ('FIFO_PROCESSED', 'FIFO Diproses'),
        ('JOURNAL_CREATED', 'Jurnal Dibuat'),
        ('PAYMENT_PROCESSED', 'Pembayaran Diproses'),
        ('LOCKED', 'Dikunci'),
    ]

    sales_header = models.ForeignKey(
        SalesHeader,
        on_delete=models.CASCADE,
        related_name='event_logs',
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    description = models.TextField(blank=True, default='')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_event_logs',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sales Event Log'
        verbose_name_plural = 'Sales Event Logs'
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['sales_header', 'timestamp'], name='idx_sel_header_ts'),
        ]

    def __str__(self) -> str:
        return f'{self.sales_header.transaction_id} — {self.event_type} @ {self.timestamp}'

