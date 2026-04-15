"""Sales models — Sales transactions with FIFO outflow, tax support, and automated journals."""
from decimal import Decimal

from django.db import models
from django.utils import timezone


class SalesHeader(models.Model):
    """Top-level sales transaction.

    Transaction ID format: TRX-SAL-XXX (auto-generated).
    """
    TAX_PAYMENT_CHOICES = [
        ('belum_transfer', 'Belum Transfer'),
        ('sudah_transfer', 'Sudah Transfer'),
    ]
    transaction_id = models.CharField(max_length=100, unique=True, editable=False)
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='new_sales_headers',
        verbose_name='Entitas Bisnis',
    )
    deskripsi = models.TextField(blank=True, default='', verbose_name='Deskripsi')
    payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sales_payment_headers',
        verbose_name='Payment Account',
        help_text='Kas Tunai, Kas di Bank, dll.',
    )
    is_locked = models.BooleanField(
        default=False,
        verbose_name='Locked',
        help_text='True jika periode sudah tutup buku.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sales Header'
        verbose_name_plural = 'Sales Headers'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'is_locked'], name='idx_nsh_tanggal_locked'),
            models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_nsh_eb_tanggal'),
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
    sales_header = models.ForeignKey(
        SalesHeader,
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

    class Meta:
        verbose_name = 'Sales Item'
        verbose_name_plural = 'Sales Items'
        indexes = [
            models.Index(fields=['sales_header', 'item'], name='idx_nsi_header_item'),
            models.Index(fields=['item'], name='idx_nsi_item'),
        ]

    def __str__(self) -> str:
        return f'{self.item.item_id} × {self.quantity}'

    def save(self, *args, **kwargs):
        self.total_sales = self.quantity * self.selling_price
        super().save(*args, **kwargs)

