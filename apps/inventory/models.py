"""Inventory models."""
from django.db import models


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
