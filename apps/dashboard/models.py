from django.db import models


class DashboardInventoryTag(models.Model):
    item = models.OneToOneField(
        'purchase.ItemMasterPurchase',
        on_delete=models.CASCADE,
        related_name='dashboard_tag',
        verbose_name='Item',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dashboard Inventory Tag'
        verbose_name_plural = 'Dashboard Inventory Tags'
        ordering = ['item__nama']

    def __str__(self) -> str:
        return f'Tag: {self.item.item_id} - {self.item.nama}'
