"""Unit of Measure master + per-item packaging conversion."""
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
