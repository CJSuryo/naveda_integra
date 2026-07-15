"""Unit of Measure master + per-item packaging conversion."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


DIMENSION_CHOICES = [
    ('count', 'Count / Jumlah'),
    ('weight', 'Berat'),
    ('volume', 'Volume'),
    ('length', 'Panjang'),
    ('area', 'Luas'),
]


class UnitOfMeasure(models.Model):
    kode = models.CharField(max_length=20, unique=True, verbose_name='Kode')
    nama = models.CharField(max_length=100, verbose_name='Nama')
    dimension = models.CharField(
        max_length=10, choices=DIMENSION_CHOICES, db_index=True, verbose_name='Dimensi',
    )
    factor_to_base = models.DecimalField(
        max_digits=24, decimal_places=8, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        verbose_name='Faktor ke Base',
        help_text='Faktor universal ke satuan dasar dimensi. Kosongkan untuk '
                  'satuan kemasan yang berbeda tiap produk (carton, box, dus, dll).',
    )
    is_base = models.BooleanField(default=False, verbose_name='Satuan Dasar')
    is_system = models.BooleanField(default=False, verbose_name='Bawaan Sistem')
    is_active = models.BooleanField(default=True, verbose_name='Aktif')

    class Meta:
        verbose_name = 'Unit of Measure'
        verbose_name_plural = 'Units of Measure'
        ordering = ['dimension', 'kode']

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class ItemUOM(models.Model):
    """Per-item packaging conversion: 1 <uom> = qty_in_stock_uom <item.stock_uom>."""
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.CASCADE,
        related_name='item_uoms',
        verbose_name='Item',
    )
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name='item_uoms',
        verbose_name='Satuan',
    )
    qty_in_stock_uom = models.DecimalField(
        max_digits=24, decimal_places=8,
        validators=[MinValueValidator(Decimal('0.00000001'))],
        verbose_name='Jumlah dalam Stock UOM',
        help_text='Berapa banyak satuan stok dalam 1 satuan ini. Contoh: 1 carton = 24 pcs → 24.',
    )

    class Meta:
        verbose_name = 'Item UOM'
        verbose_name_plural = 'Item UOMs'
        unique_together = [('item', 'uom')]
        indexes = [
            models.Index(fields=['item', 'uom'], name='idx_itemuom_item_uom'),
        ]

    def __str__(self) -> str:
        return f'{self.item.nama}: 1 {self.uom.kode} = {self.qty_in_stock_uom}'
