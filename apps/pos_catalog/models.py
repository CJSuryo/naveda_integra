from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
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
