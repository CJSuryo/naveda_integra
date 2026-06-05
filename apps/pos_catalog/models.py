from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max
from pos_config.models import MerchantPOSConfig


class ModifierGroup(models.Model):
    merchant_config = models.ForeignKey(MerchantPOSConfig, on_delete=models.CASCADE, related_name='modifier_groups')
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    min_selections = models.IntegerField(default=0)
    max_selections = models.IntegerField(default=1)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.min_selections > self.max_selections:
            raise ValidationError('min_selections tidak boleh melebihi max_selections')
        if self.is_required and self.min_selections < 1:
            raise ValidationError('Grup wajib harus memiliki min_selections >= 1')


class ModifierOption(models.Model):
    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=100)
    additional_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    is_default = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return f'{self.name} (+{self.additional_price})'


class ProductModifierGroup(models.Model):
    item = models.ForeignKey('purchase.ItemMasterPurchase', on_delete=models.CASCADE, related_name='modifier_links')
    modifier_group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name='product_links')
    display_order = models.IntegerField(default=0)

    class Meta:
        unique_together = ('item', 'modifier_group')
        ordering = ['display_order']


class CatalogItem(models.Model):
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        related_name='catalog_items',
    )
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase',
        on_delete=models.PROTECT,
        related_name='catalog_entries',
    )
    selling_price = models.DecimalField(max_digits=15, decimal_places=4)
    display_name = models.CharField(max_length=200, blank=True)
    display_order = models.IntegerField(default=0)
    product_image = models.ImageField(upload_to='catalog/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('entitas_bisnis', 'item')
        ordering = ['display_order', 'item__nama']
        verbose_name = 'Catalog Item'
        verbose_name_plural = 'Catalog Items'

    def __str__(self):
        name = self.display_name or self.item.nama
        return f'{name} — {self.entitas_bisnis.nama}'

    def save(self, *args, **kwargs):
        if not self.pk and self.display_order == 0:
            max_order = CatalogItem.objects.filter(
                entitas_bisnis=self.entitas_bisnis
            ).aggregate(m=Max('display_order'))['m']
            self.display_order = (max_order or 0) + 1
        super().save(*args, **kwargs)


class CatalogItemLog(models.Model):
    catalog_item = models.ForeignKey(
        CatalogItem, on_delete=models.CASCADE, related_name='logs'
    )
    field_name = models.CharField(max_length=50)
    old_value = models.TextField()
    new_value = models.TextField()
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='catalog_logs',
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Catalog Item Log'
        verbose_name_plural = 'Catalog Item Logs'

    def __str__(self):
        return f'{self.catalog_item} · {self.field_name} @ {self.changed_at}'
