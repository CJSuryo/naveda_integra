from django.db import models


class Campaign(models.Model):
    TYPE_DISCOUNT_PCT   = 'DISCOUNT_PCT'
    TYPE_DISCOUNT_FIXED = 'DISCOUNT_FIXED'
    TYPE_BUY_X_GET_Y    = 'BUY_X_GET_Y'
    TYPE_FREE_ITEM      = 'FREE_ITEM'
    TYPE_VOUCHER        = 'VOUCHER'
    TYPE_CHOICES = [
        (TYPE_DISCOUNT_PCT, 'Diskon %'),
        (TYPE_DISCOUNT_FIXED, 'Diskon Nominal'),
        (TYPE_BUY_X_GET_Y, 'Beli X Gratis Y'),
        (TYPE_FREE_ITEM, 'Item Gratis'),
        (TYPE_VOUCHER, 'Voucher'),
    ]

    APPLICABLE_ALL      = 'ALL'
    APPLICABLE_CATEGORY = 'CATEGORY'
    APPLICABLE_PRODUCT  = 'PRODUCT'
    APPLICABLE_CHOICES  = [
        (APPLICABLE_ALL, 'Semua'),
        (APPLICABLE_CATEGORY, 'Kategori'),
        (APPLICABLE_PRODUCT, 'Produk'),
    ]

    merchant_config       = models.ForeignKey('pos_config.MerchantPOSConfig', on_delete=models.CASCADE, related_name='campaigns')
    name                  = models.CharField(max_length=200)
    description           = models.TextField(blank=True)
    campaign_type         = models.CharField(max_length=30, choices=TYPE_CHOICES)
    discount_pct          = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_amount       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    max_discount_cap      = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    min_purchase_amount   = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    buy_quantity          = models.IntegerField(null=True, blank=True)
    get_quantity          = models.IntegerField(null=True, blank=True)
    applicable_to         = models.CharField(max_length=20, choices=APPLICABLE_CHOICES, default=APPLICABLE_ALL)
    applicable_products   = models.ManyToManyField('purchase.ItemMasterPurchase', blank=True, related_name='campaign_products')
    stores                = models.ManyToManyField('pos_config.StorePOSConfig', blank=True)
    is_active             = models.BooleanField(default=True)
    start_date            = models.DateField()
    end_date              = models.DateField(null=True, blank=True)
    max_uses              = models.IntegerField(null=True, blank=True)
    uses_count            = models.IntegerField(default=0)
    per_member_limit      = models.IntegerField(null=True, blank=True)
    requires_member       = models.BooleanField(default=False)
    min_tier              = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class Voucher(models.Model):
    campaign      = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='vouchers')
    code          = models.CharField(max_length=50, unique=True)
    is_used       = models.BooleanField(default=False)
    used_by       = models.ForeignKey('pos_crm.Member', on_delete=models.SET_NULL, null=True, blank=True)
    used_in_order = models.ForeignKey('pos_orders.Order', on_delete=models.SET_NULL, null=True, blank=True)
    used_at       = models.DateTimeField(null=True, blank=True)
    expires_at    = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class OrderPromotion(models.Model):
    order           = models.ForeignKey('pos_orders.Order', on_delete=models.CASCADE, related_name='promotions')
    campaign        = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    voucher         = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2)
    description     = models.CharField(max_length=200)

    def __str__(self):
        return f'{self.order.order_number} — {self.campaign.name}'
