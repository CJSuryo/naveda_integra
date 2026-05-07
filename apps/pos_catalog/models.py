from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from apps.purchase.models import ItemMasterPurchase


class POSCategory(models.Model):
    merchant_config = models.ForeignKey(MerchantPOSConfig, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#0054a6')
    icon = models.CharField(max_length=50, blank=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class POSProduct(models.Model):
    item_master = models.OneToOneField(ItemMasterPurchase, on_delete=models.CASCADE, related_name='pos_product')
    merchant_config = models.ForeignKey(MerchantPOSConfig, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(POSCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    pos_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='pos/products/', null=True, blank=True)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2)
    is_available = models.BooleanField(default=True)
    track_inventory = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'pos_name']

    def __str__(self):
        return self.pos_name


class ProductStoreAvailability(models.Model):
    product = models.ForeignKey(POSProduct, on_delete=models.CASCADE, related_name='store_availability')
    store = models.ForeignKey(StorePOSConfig, on_delete=models.CASCADE, related_name='product_availability')
    is_available = models.BooleanField(default=True)
    selling_price_override = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('product', 'store')

    def effective_price(self) -> Decimal:
        return self.selling_price_override if self.selling_price_override is not None else self.product.selling_price


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
    product = models.ForeignKey(POSProduct, on_delete=models.CASCADE, related_name='modifier_links')
    modifier_group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name='product_links')
    display_order = models.IntegerField(default=0)

    class Meta:
        unique_together = ('product', 'modifier_group')
        ordering = ['display_order']
