"""Purchase module models.

Includes: ItemMasterPurchase, SubTransactionType (settings),
PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, FIFOBatch.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone


# ── Item Master ──────────────────────────────────────────────────────────────

class KategoriItem(models.Model):
    """Free-form item category (Coffee, Tea, Snacks, Bahan Masak, etc.)."""
    nama = models.CharField(max_length=255, unique=True)
    entitas_bisnis = models.ManyToManyField(
        'entitas_bisnis.EntitasBisnis',
        blank=True,
        related_name='kategori_items',
        verbose_name='Entitas Bisnis',
    )

    class Meta:
        verbose_name = 'Kategori Item'
        verbose_name_plural = 'Kategori Item'

    def __str__(self) -> str:
        return self.nama


class ItemMasterPurchase(models.Model):
    """Item Master — shared by Purchase, Sales, Manufacturing.

    Item ID format: RM-XXXX (Raw Material), FG-XXXX (Finished Good), ITM-XXXX (other).
    """
    ITEM_TYPE_CHOICES = [
        ('RM', 'Raw Material'),
        ('FG', 'Finished Good'),
        ('ITM', 'Item Lainnya'),
        ('ATP', 'Aset Tetap'),
        ('ALL', 'Aset Lainnya'),
    ]
    VELOCITY_CHOICES = [
        ('fast', 'Fast Moving'),
        ('medium', 'Medium (B)'),
        ('slow', 'Slow (C)'),
        ('dead', 'Dead Stock'),
    ]
    item_id = models.CharField(max_length=50, unique=True, editable=False)
    nama = models.CharField(max_length=255, unique=True)
    tipe_item = models.CharField(max_length=10, choices=ITEM_TYPE_CHOICES, default='RM')
    kategori = models.ForeignKey(
        KategoriItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='items',
    )
    velocity_category = models.CharField(
        max_length=20,
        choices=VELOCITY_CHOICES,
        blank=True,
        default='',
        verbose_name='Velocity Category',
    )
    coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='item_masters',
        verbose_name='CoA Account',
    )
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Tanggal Kadaluarsa')
    threshold_days_outstanding = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Threshold Days Inv Outstanding',
        help_text='Batas hari sebelum item dianggap stok mati.',
    )
    unit_price = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Harga Satuan Default',
    )
    entitas_bisnis = models.ManyToManyField(
        'entitas_bisnis.EntitasBisnis',
        blank=True,
        related_name='item_masters',
        verbose_name='Entitas Bisnis',
    )

    class Meta:
        verbose_name = 'Item Master'
        verbose_name_plural = 'Item Master'
        indexes = [
            models.Index(fields=['tipe_item', 'nama'], name='idx_imp_tipe_nama'),
            models.Index(fields=['kategori'], name='idx_imp_kategori'),
        ]

    def __str__(self) -> str:
        return f'{self.item_id} - {self.nama}'

    def save(self, *args, **kwargs):
        if not self.item_id:
            self.item_id = self._generate_item_id()
        super().save(*args, **kwargs)

    def _generate_item_id(self) -> str:
        prefix = self.tipe_item  # RM, FG, or ITM
        last = (
            ItemMasterPurchase.objects
            .filter(item_id__startswith=f'{prefix}-')
            .order_by('-item_id')
            .values_list('item_id', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'{prefix}-{seq:04d}'


# ── Sub-Transaction Type (Settings) ─────────────────────────────────────────

class SubTransactionType(models.Model):
    """Settings: maps sub-transaction types to default offset CoA accounts.

    Examples: 'Stok Awal', 'Pembelian - Transfer', 'Pembelian - Tunai'.
    """
    DIRECTION_CHOICES = [
        ('inflow', 'Inflow'),
        ('outflow', 'Outflow'),
    ]
    nama = models.CharField(max_length=255, unique=True, verbose_name='Sub-Transaction Type')
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default='inflow',
        verbose_name='Transaction Type (Direction)',
    )
    default_offset_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='sub_transaction_types',
        verbose_name='Default Offset Account',
    )

    class Meta:
        verbose_name = 'Sub-Transaction Type'
        verbose_name_plural = 'Sub-Transaction Types'

    def __str__(self) -> str:
        return f'{self.nama} ({self.get_direction_display()})'


# ── Purchase Header ──────────────────────────────────────────────────────────

class PurchaseHeader(models.Model):
    """Top-level purchase transaction.

    Transaction ID format depends on item type group:
      PUR-INV-XXX (Raw Material / Finished Good / Item Lainnya)
      PUR-ATP-XXX (Aset Tetap)
      PUR-ALL-XXX (Aset Lainnya)
    """
    ITEM_TYPE_PREFIX_MAP = {
        'RM': 'PUR-INV',
        'FG': 'PUR-INV',
        'ITM': 'PUR-INV',
        'ATP': 'PUR-ATP',
        'ALL': 'PUR-ALL',
    }
    transaction_id = models.CharField(max_length=100, unique=True, editable=False)
    tanggal = models.DateField(db_index=True, default=timezone.now, verbose_name='Tanggal')
    deskripsi = models.TextField(blank=True, default='', verbose_name='Deskripsi')
    is_locked = models.BooleanField(
        default=False,
        verbose_name='Locked',
        help_text='True jika periode sudah tutup buku.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Purchase Header'
        verbose_name_plural = 'Purchase Headers'
        ordering = ['-tanggal', '-created_at']
        indexes = [
            models.Index(fields=['tanggal', 'is_locked'], name='idx_ph_tanggal_locked'),
        ]

    def __str__(self) -> str:
        return self.transaction_id

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            prefix = kwargs.pop('_trx_prefix', 'PUR-INV')
            self.transaction_id = self._generate_transaction_id(prefix)
        else:
            kwargs.pop('_trx_prefix', None)
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_transaction_id(prefix: str = 'PUR-INV') -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                PurchaseHeader.objects
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


# ── Purchase Entitas Bisnis (per-EB grouping inside a purchase) ──────────────

class PurchaseEntitasBisnis(models.Model):
    """Links a purchase header to a specific business entity (at any level).

    All three hierarchy levels are stored:
    - ``entitas_bisnis`` (lv1) is always populated.
    - ``entitas_bisnis_lv2`` is populated when a lv2 or lv3 entity was selected.
    - ``entitas_bisnis_lv3`` is populated only when a lv3 entity was selected.
    """
    purchase_header = models.ForeignKey(
        PurchaseHeader,
        on_delete=models.CASCADE,
        related_name='entitas_groups',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='purchase_groups',
        verbose_name='Entitas Bisnis (Lv1)',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_groups',
        verbose_name='Entitas Bisnis Lv2',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_groups',
        verbose_name='Entitas Bisnis Lv3',
    )

    class Meta:
        verbose_name = 'Purchase Entitas Bisnis'
        verbose_name_plural = 'Purchase Entitas Bisnis'
        indexes = [
            models.Index(fields=['purchase_header', 'entitas_bisnis'], name='idx_peb_header_eb'),
            models.Index(fields=['entitas_bisnis_lv2'], name='idx_peb_lv2'),
            models.Index(fields=['entitas_bisnis_lv3'], name='idx_peb_lv3'),
        ]

    def __str__(self) -> str:
        if self.entitas_bisnis_lv3_id:
            return (
                f'{self.purchase_header.transaction_id} → '
                f'{self.entitas_bisnis.nama} / {self.entitas_bisnis_lv2.nama} / {self.entitas_bisnis_lv3.nama}'
            )
        if self.entitas_bisnis_lv2_id:
            return (
                f'{self.purchase_header.transaction_id} → '
                f'{self.entitas_bisnis.nama} / {self.entitas_bisnis_lv2.nama}'
            )
        return f'{self.purchase_header.transaction_id} → {self.entitas_bisnis.nama}'


# ── Purchase Item (detail line within an EB group) ───────────────────────────

class PurchaseItem(models.Model):
    """Individual item line within a purchase for a specific entitas bisnis."""
    purchase_eb = models.ForeignKey(
        PurchaseEntitasBisnis,
        on_delete=models.CASCADE,
        related_name='items',
    )
    item = models.ForeignKey(
        ItemMasterPurchase,
        on_delete=models.PROTECT,
        related_name='purchase_items',
    )
    sub_transaction_type = models.ForeignKey(
        SubTransactionType,
        on_delete=models.PROTECT,
        related_name='purchase_items',
        verbose_name='Sub-Transaction Type',
    )
    coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='purchase_item_coa',
        verbose_name='CoA Account',
    )
    offset_coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='purchase_item_offset',
        verbose_name='Offset CoA Account',
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Quantity')
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Harga Satuan')
    total_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        editable=False,
        default=0,
        verbose_name='Total Nilai',
    )
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, verbose_name='Lead Time (Days)')
    ordering_cost = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Ordering Cost',
    )
    holding_cost_pct = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Holding Cost %',
        help_text='Contoh: 0.1 = 10%',
    )
    moq = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='MOQ',
    )
    target_turnover = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Target Turnover',
    )

    class Meta:
        verbose_name = 'Purchase Item'
        verbose_name_plural = 'Purchase Items'
        indexes = [
            models.Index(fields=['purchase_eb', 'item'], name='idx_pi_eb_item'),
            models.Index(fields=['item', 'sub_transaction_type'], name='idx_pi_item_stt'),
        ]

    def __str__(self) -> str:
        return f'{self.item.item_id} × {self.quantity}'

    def save(self, *args, **kwargs):
        self.total_value = self.quantity * self.unit_price
        super().save(*args, **kwargs)


# ── FIFO Batch (FIFO Engine) ────────────────────────────────────────────────

class FIFOBatch(models.Model):
    """FIFO Engine batch record — auto-created on purchase, consumed on sale/manufacturing."""
    purchase_item = models.ForeignKey(
        PurchaseItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fifo_batches',
    )
    item = models.ForeignKey(
        ItemMasterPurchase,
        on_delete=models.PROTECT,
        related_name='fifo_batches',
    )
    tanggal = models.DateField(db_index=True)
    quantity_in = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Qty Masuk')
    unit_price = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Harga Satuan')
    remaining_qty = models.DecimalField(max_digits=15, decimal_places=4, verbose_name='Sisa Qty')
    batch_value = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        default=0,
        verbose_name='Nilai Batch',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'FIFO Batch'
        verbose_name_plural = 'FIFO Batches'
        ordering = ['tanggal', 'created_at']
        indexes = [
            models.Index(fields=['item', 'tanggal'], name='idx_fb_item_tanggal'),
            models.Index(fields=['item', 'remaining_qty'], name='idx_fb_item_remaining'),
        ]

    def __str__(self) -> str:
        return f'FIFO {self.item.item_id} | {self.tanggal} | Sisa: {self.remaining_qty}'

    def save(self, *args, **kwargs):
        self.batch_value = self.remaining_qty * self.unit_price
        super().save(*args, **kwargs)
