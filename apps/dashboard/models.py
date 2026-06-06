from django.db import models


class DashboardInventoryTag(models.Model):
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.CASCADE,
        related_name='dashboard_tags',
        verbose_name='Item',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        related_name='dashboard_inventory_tags',
        verbose_name='Entitas Bisnis',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('item', 'entitas_bisnis')
        verbose_name = 'Dashboard Inventory Tag'
        verbose_name_plural = 'Dashboard Inventory Tags'
        ordering = ['item__nama']

    def __str__(self) -> str:
        return f'Tag: {self.item.item_id} - {self.item.nama}'
