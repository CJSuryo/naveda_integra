# POS System Design Spec
**Date:** 2026-05-05  
**Project:** Naveda Integra  
**Scope:** Full POS module addition to existing Django ERP  

---

## Context

Naveda Integra is a Django 6+ ERP with double-entry accounting, FIFO inventory costing, and automated journal entries. It currently handles Sales, Purchase, Inventory, Manufacturing, Payables, Receivables, Fixed Assets, and Equity — all via server-side templates, function-based views, and a custom `ni-` CSS design system (no Bootstrap, no DRF, no Celery, no React).

This spec adds a full Point-of-Sale module. The POS must integrate perfectly with the existing Sales → FIFO → JurnalAutomasi pipeline. Every completed POS order must produce a `SalesHeader` with full FIFO allocation and balanced journal entries, identical to a manual sales entry.

---

## Key Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Real-time strategy | Hybrid — cashier WebSocket, reports polling | Balance infrastructure cost vs. UX need |
| QRIS | Static QR image per merchant, cashier manually confirms | No payment gateway dependency |
| Aggregator integration | Source field on Order from day 1 | Prevents future migration of order data |
| Product modifiers | Full modifier groups (required/optional, min/max, per-option pricing) | Standard FnB POS requirement |
| App structure | 7 focused `pos_*` apps | Mirrors existing 13-app pattern, clean TDD boundaries |
| Push notifications | VAPID web push (pywebpush) + WebSocket in-screen | Works backgrounded/locked, no native app needed |
| Frontend | Existing `ni-` design system, vanilla JS + service worker | Zero new framework dependencies |

---

## Architecture

### New Django Apps

```
pos_config/       → Merchant & store config, payment methods, work shifts, push subscriptions
pos_catalog/      → Products, categories, modifier groups, modifier options
pos_orders/       → Orders, order items, modifiers, payments, refunds, WebSocket consumers
pos_crm/          → Members, loyalty points, tier config
pos_promotions/   → Campaigns, vouchers, order-applied promotions
pos_reports/      → Daily snapshots, report queries (mostly computed, few models)
pos_aggregators/  → Online channel config, webhook ingestion logs
```

### App Dependency Graph (no circular imports)

```
entitas_bisnis (existing)
    └── pos_config              (OneToOne sidecars on EntitasBisnis / EntitasBisnisLv2)
            ├── pos_catalog     (FK to pos_config + OneToOne to purchase.ItemMasterPurchase)
            ├── pos_crm         (FK to pos_config)
            └── pos_promotions  (FK to pos_config, M2M to pos_catalog)
                    └── pos_orders   (FK to all above + OneToOne to sales.SalesHeader on complete)
                            └── pos_reports   (queries pos_orders)
                            └── pos_aggregators (creates pos_orders.Order)
```

Existing apps `sales`, `purchase`, `inventory`, `jurnal` are called FROM `pos_orders/services/` — never from models. No existing app imports from any `pos_*` app.

### New Infrastructure

| Component | Package | Use |
|-----------|---------|-----|
| WebSocket | `channels>=4.0,<5.0` | Real-time cashier + kitchen display |
| Channel layer | `channels-redis>=4.0,<5.0` | Group messaging between consumers |
| Redis | (managed or local) | Backend for channels-redis |
| Image fields | `Pillow>=10.0,<12.0` | Product images, QRIS images, logos |
| Web Push | `pywebpush>=2.0,<3.0` | Background push notifications via VAPID |

**Updated `requirements.txt` additions:**
```
channels>=4.0,<5.0
channels-redis>=4.0,<5.0
Pillow>=10.0,<12.0
pywebpush>=2.0,<3.0
```

**New `naveda_integra/asgi.py`:**
```python
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
import pos_orders.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(pos_orders.routing.websocket_urlpatterns)
    ),
})
```

**New `base.py` additions:**
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL", default="redis://localhost:6379")]},
    }
}
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_PUBLIC_KEY  = env("VAPID_PUBLIC_KEY", default="")
VAPID_CLAIM_EMAIL = env("VAPID_CLAIM_EMAIL", default="push@example.com")
```

---

## Data Models

### `pos_config` App

```python
class MerchantPOSConfig(models.Model):
    entitas_bisnis      = OneToOneField(EntitasBisnis, CASCADE, related_name='pos_config')
    is_pos_active       = BooleanField(default=False)
    logo                = ImageField(upload_to='pos/logos/', null=True, blank=True)
    qris_image          = ImageField(upload_to='pos/qris/', null=True, blank=True)
    default_tax_pct     = DecimalField(max_digits=5, decimal_places=2, default=0)
    default_service_charge_pct = DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_inclusive       = BooleanField(default=False)  # tax included in selling_price or added on top
    currency            = CharField(max_length=3, default='IDR')
    created_at          = DateTimeField(auto_now_add=True)
    updated_at          = DateTimeField(auto_now=True)


class StorePOSConfig(models.Model):
    entitas_bisnis_lv2  = OneToOneField(EntitasBisnisLv2, CASCADE, related_name='pos_config')
    merchant_config     = ForeignKey(MerchantPOSConfig, CASCADE, related_name='stores')
    tax_pct             = DecimalField(null=True, blank=True)   # None = inherit merchant default
    service_charge_pct  = DecimalField(null=True, blank=True)
    printer_type        = CharField(choices=[EPSON_TM, STAR_TSP, GENERIC_ESCPOS], blank=True)
    printer_ip          = GenericIPAddressField(null=True, blank=True)
    printer_port        = IntegerField(default=9100)
    receipt_header      = TextField(blank=True)
    receipt_footer      = TextField(blank=True)
    is_active           = BooleanField(default=True)

    def effective_tax_pct(self):
        return self.tax_pct if self.tax_pct is not None else self.merchant_config.default_tax_pct

    def effective_service_charge_pct(self):
        return self.service_charge_pct if self.service_charge_pct is not None \
               else self.merchant_config.default_service_charge_pct


class PaymentMethod(models.Model):
    merchant_config = ForeignKey(MerchantPOSConfig, CASCADE, related_name='payment_methods')
    store           = ForeignKey(StorePOSConfig, CASCADE, null=True, blank=True, related_name='payment_methods')
    name            = CharField(max_length=100)
    method_type     = CharField(choices=[CASH, QRIS, TRANSFER, OTHER])
    is_active       = BooleanField(default=True)
    display_order   = IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']


class WorkShift(models.Model):
    store       = ForeignKey(StorePOSConfig, CASCADE, related_name='shifts')
    name        = CharField(max_length=100)   # Pagi / Siang / Malam
    start_time  = TimeField()
    end_time    = TimeField()
    is_active   = BooleanField(default=True)


class ShiftLog(models.Model):
    store         = ForeignKey(StorePOSConfig, CASCADE, related_name='shift_logs')
    shift         = ForeignKey(WorkShift, PROTECT, related_name='logs')
    employee      = ForeignKey(settings.AUTH_USER_MODEL, PROTECT, related_name='shift_logs')
    clock_in      = DateTimeField()
    clock_out     = DateTimeField(null=True, blank=True)
    opening_cash  = DecimalField(max_digits=15, decimal_places=2, default=0)
    closing_cash  = DecimalField(null=True, blank=True)
    notes         = TextField(blank=True)

    @property
    def is_active(self):
        return self.clock_out is None


class WebPushSubscription(models.Model):
    ROLE_CASHIER  = 'CASHIER'
    ROLE_KITCHEN  = 'KITCHEN'
    ROLE_MANAGER  = 'MANAGER'

    user        = ForeignKey(settings.AUTH_USER_MODEL, CASCADE, related_name='push_subscriptions')
    store       = ForeignKey(StorePOSConfig, CASCADE, related_name='push_subscriptions')
    endpoint    = URLField(max_length=500)
    p256dh_key  = CharField(max_length=200)
    auth_key    = CharField(max_length=100)
    role        = CharField(choices=[CASHIER, KITCHEN, MANAGER], default=ROLE_CASHIER)
    user_agent  = CharField(max_length=300, blank=True)
    is_active   = BooleanField(default=True)
    created_at  = DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'endpoint')
```

---

### `pos_catalog` App

```python
class POSCategory(models.Model):
    merchant_config = ForeignKey(MerchantPOSConfig, CASCADE, related_name='categories')
    name            = CharField(max_length=100)
    color           = CharField(max_length=7, default='#0054a6')   # hex
    icon            = CharField(max_length=50, blank=True)          # lucide icon name
    display_order   = IntegerField(default=0)
    is_active       = BooleanField(default=True)


class POSProduct(models.Model):
    item_master     = OneToOneField(ItemMasterPurchase, CASCADE, related_name='pos_product')
    merchant_config = ForeignKey(MerchantPOSConfig, CASCADE, related_name='products')
    category        = ForeignKey(POSCategory, SET_NULL, null=True, related_name='products')
    pos_name        = CharField(max_length=200)    # display name on screen (may differ from accounting name)
    description     = TextField(blank=True)
    image           = ImageField(upload_to='pos/products/', null=True, blank=True)
    selling_price   = DecimalField(max_digits=15, decimal_places=2)
    is_available    = BooleanField(default=True)
    track_inventory = BooleanField(default=True)   # False = no FIFO stock check (service items)
    display_order   = IntegerField(default=0)


class ProductStoreAvailability(models.Model):
    """Per-store override. Absence means inherit merchant-level POSProduct settings."""
    product                = ForeignKey(POSProduct, CASCADE, related_name='store_availability')
    store                  = ForeignKey(StorePOSConfig, CASCADE, related_name='product_availability')
    is_available           = BooleanField(default=True)
    selling_price_override = DecimalField(null=True, blank=True)   # None = use POSProduct.selling_price

    class Meta:
        unique_together = ('product', 'store')


class ModifierGroup(models.Model):
    merchant_config  = ForeignKey(MerchantPOSConfig, CASCADE, related_name='modifier_groups')
    name             = CharField(max_length=100)   # "Ukuran", "Level Es", "Topping"
    is_required      = BooleanField(default=False)
    min_selections   = IntegerField(default=0)
    max_selections   = IntegerField(default=1)     # 1 = single choice, >1 = multi-select
    display_order    = IntegerField(default=0)
    is_active        = BooleanField(default=True)

    def clean(self):
        if self.min_selections > self.max_selections:
            raise ValidationError("min_selections tidak boleh melebihi max_selections")
        if self.is_required and self.min_selections < 1:
            raise ValidationError("Grup wajib harus min_selections >= 1")


class ModifierOption(models.Model):
    group            = ForeignKey(ModifierGroup, CASCADE, related_name='options')
    name             = CharField(max_length=100)
    additional_price = DecimalField(max_digits=10, decimal_places=2, default=0)
    is_default       = BooleanField(default=False)
    is_available     = BooleanField(default=True)
    display_order    = IntegerField(default=0)


class ProductModifierGroup(models.Model):
    """Through table linking a POSProduct to reusable ModifierGroups."""
    product         = ForeignKey(POSProduct, CASCADE, related_name='modifier_links')
    modifier_group  = ForeignKey(ModifierGroup, CASCADE, related_name='product_links')
    display_order   = IntegerField(default=0)

    class Meta:
        unique_together = ('product', 'modifier_group')
        ordering = ['display_order']
```

---

### `pos_orders` App

```python
class Order(models.Model):
    # source choices
    SOURCE_POS        = 'POS'
    SOURCE_GOFOOD     = 'GOFOOD'
    SOURCE_GRABFOOD   = 'GRABFOOD'
    SOURCE_SHOPEEFOOD = 'SHOPEEFOOD'
    SOURCE_SHOPEE     = 'SHOPEE'
    SOURCE_OTHER      = 'OTHER'

    # status choices
    STATUS_DRAFT      = 'DRAFT'       # being built by cashier
    STATUS_OPEN       = 'OPEN'        # submitted, waiting kitchen acknowledgement
    STATUS_IN_QUEUE   = 'IN_QUEUE'    # acknowledged by kitchen
    STATUS_PREPARING  = 'PREPARING'
    STATUS_READY      = 'READY'       # ready for handover
    STATUS_COMPLETED  = 'COMPLETED'   # payment confirmed, order closed
    STATUS_CANCELLED  = 'CANCELLED'
    STATUS_REFUNDED   = 'REFUNDED'

    VALID_TRANSITIONS = {
        STATUS_DRAFT:     [STATUS_OPEN, STATUS_CANCELLED],
        STATUS_OPEN:      [STATUS_IN_QUEUE, STATUS_CANCELLED],
        STATUS_IN_QUEUE:  [STATUS_PREPARING, STATUS_CANCELLED],
        STATUS_PREPARING: [STATUS_READY, STATUS_CANCELLED],
        STATUS_READY:     [STATUS_COMPLETED, STATUS_CANCELLED],
        STATUS_COMPLETED: [STATUS_REFUNDED],
        STATUS_CANCELLED: [],
        STATUS_REFUNDED:  [],
    }

    order_number         = CharField(max_length=50, unique=True)   # ORD-{store_code}-{YYYYMMDD}-{seq}
    store                = ForeignKey(StorePOSConfig, PROTECT, related_name='orders')
    shift_log            = ForeignKey(ShiftLog, SET_NULL, null=True, related_name='orders')
    cashier              = ForeignKey(settings.AUTH_USER_MODEL, PROTECT, related_name='cashier_orders')
    source               = CharField(choices=SOURCE_CHOICES, default=SOURCE_POS)
    external_order_id    = CharField(max_length=100, blank=True)
    external_order_data  = JSONField(default=dict, blank=True)
    status               = CharField(choices=STATUS_CHOICES, default=STATUS_DRAFT)
    order_type           = CharField(choices=[DINE_IN, TAKEAWAY, DELIVERY], default='DINE_IN')
    table_number         = CharField(max_length=20, blank=True)
    customer_name        = CharField(max_length=200, blank=True)
    member               = ForeignKey('pos_crm.Member', SET_NULL, null=True, related_name='orders')
    subtotal             = DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount      = DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount           = DecimalField(max_digits=15, decimal_places=2, default=0)
    service_charge_amount = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount         = DecimalField(max_digits=15, decimal_places=2, default=0)
    notes                = TextField(blank=True)
    sales_header         = OneToOneField('sales.SalesHeader', SET_NULL, null=True, related_name='pos_order')
    created_at           = DateTimeField(auto_now_add=True, db_index=True)
    updated_at           = DateTimeField(auto_now=True)
    completed_at         = DateTimeField(null=True, blank=True)

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def recalculate_totals(self):
        """Recompute subtotal from items, then apply tax/service charge from store config."""
        ...

    def is_fully_paid(self) -> bool:
        confirmed_total = self.payments.filter(is_confirmed=True).aggregate(Sum('amount'))['amount__sum'] or 0
        return confirmed_total >= self.total_amount


class OrderItem(models.Model):
    order          = ForeignKey(Order, CASCADE, related_name='items')
    product        = ForeignKey(POSProduct, PROTECT, related_name='order_items')
    quantity       = DecimalField(max_digits=10, decimal_places=3)
    unit_price     = DecimalField(max_digits=15, decimal_places=2)   # snapshot at order time
    modifier_total = DecimalField(max_digits=15, decimal_places=2, default=0)
    subtotal       = DecimalField(max_digits=15, decimal_places=2)   # (unit_price + modifier_total) * qty
    notes          = TextField(blank=True)
    status         = CharField(choices=[PENDING, PREPARING, READY, CANCELLED], default='PENDING')


class OrderItemModifier(models.Model):
    order_item          = ForeignKey(OrderItem, CASCADE, related_name='modifiers')
    modifier_option     = ForeignKey(ModifierOption, PROTECT)
    option_name_snapshot = CharField(max_length=100)   # protects against modifier rename
    group_name_snapshot  = CharField(max_length=100)
    price_snapshot       = DecimalField(max_digits=10, decimal_places=2)   # protects against price change


class OrderPayment(models.Model):
    order             = ForeignKey(Order, CASCADE, related_name='payments')
    payment_method    = ForeignKey(PaymentMethod, PROTECT)
    amount            = DecimalField(max_digits=15, decimal_places=2)
    reference_number  = CharField(max_length=100, blank=True)
    is_confirmed      = BooleanField(default=True)   # False for QRIS/Transfer awaiting cashier confirm
    confirmed_at      = DateTimeField(null=True, blank=True)
    confirmed_by      = ForeignKey(settings.AUTH_USER_MODEL, SET_NULL, null=True)
    created_at        = DateTimeField(auto_now_add=True)


class Refund(models.Model):
    order          = ForeignKey(Order, PROTECT, related_name='refunds')
    initiated_by   = ForeignKey(settings.AUTH_USER_MODEL, PROTECT, related_name='initiated_refunds')
    approved_by    = ForeignKey(settings.AUTH_USER_MODEL, SET_NULL, null=True, related_name='approved_refunds')
    reason         = TextField()
    refund_type    = CharField(choices=[FULL, PARTIAL])
    amount         = DecimalField(max_digits=15, decimal_places=2)
    refund_method  = ForeignKey(PaymentMethod, PROTECT)
    status         = CharField(choices=[PENDING, APPROVED, COMPLETED, REJECTED], default='PENDING')
    created_at     = DateTimeField(auto_now_add=True)
    updated_at     = DateTimeField(auto_now=True)


class RefundItem(models.Model):
    refund      = ForeignKey(Refund, CASCADE, related_name='items')
    order_item  = ForeignKey(OrderItem, PROTECT)
    quantity    = DecimalField(max_digits=10, decimal_places=3)
    amount      = DecimalField(max_digits=15, decimal_places=2)
```

---

### `pos_crm` App

```python
class MemberTierConfig(models.Model):
    merchant_config      = ForeignKey(MerchantPOSConfig, CASCADE, related_name='tier_configs')
    tier                 = CharField(choices=[REGULAR, SILVER, GOLD, PLATINUM])
    min_total_spent      = DecimalField(max_digits=15, decimal_places=2)
    points_per_thousand  = IntegerField(default=1)   # points earned per Rp 1.000 spent
    point_value          = DecimalField(max_digits=10, decimal_places=2, default=100)  # Rp per 1 point

    class Meta:
        unique_together = ('merchant_config', 'tier')


class Member(models.Model):
    member_id       = CharField(max_length=20, unique=True)   # MBR-0001
    merchant_config = ForeignKey(MerchantPOSConfig, CASCADE, related_name='members')
    entitas_bisnis  = ForeignKey(EntitasBisnis, SET_NULL, null=True, blank=True, related_name='member_profiles')
    name            = CharField(max_length=200)
    phone           = CharField(max_length=20)   # primary lookup key
    email           = EmailField(blank=True)
    birth_date      = DateField(null=True, blank=True)
    tier            = CharField(choices=[REGULAR, SILVER, GOLD, PLATINUM], default='REGULAR')
    points          = IntegerField(default=0)
    total_spent     = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_orders    = IntegerField(default=0)
    joined_at       = DateTimeField(auto_now_add=True)
    is_active       = BooleanField(default=True)
    notes           = TextField(blank=True)

    class Meta:
        unique_together = ('merchant_config', 'phone')


class MemberPointLog(models.Model):
    member     = ForeignKey(Member, CASCADE, related_name='point_logs')
    order      = ForeignKey('pos_orders.Order', SET_NULL, null=True, blank=True)
    points     = IntegerField()   # positive = earned, negative = redeemed
    reason     = CharField(max_length=200)
    created_at = DateTimeField(auto_now_add=True)
```

---

### `pos_promotions` App

```python
class Campaign(models.Model):
    TYPE_DISCOUNT_PCT   = 'DISCOUNT_PCT'
    TYPE_DISCOUNT_FIXED = 'DISCOUNT_FIXED'
    TYPE_BUY_X_GET_Y    = 'BUY_X_GET_Y'
    TYPE_FREE_ITEM      = 'FREE_ITEM'
    TYPE_VOUCHER        = 'VOUCHER'

    merchant_config       = ForeignKey(MerchantPOSConfig, CASCADE, related_name='campaigns')
    name                  = CharField(max_length=200)
    description           = TextField(blank=True)
    campaign_type         = CharField(choices=TYPE_CHOICES)
    discount_pct          = DecimalField(null=True, blank=True)
    discount_amount       = DecimalField(null=True, blank=True)
    max_discount_cap      = DecimalField(null=True, blank=True)    # cap for pct discounts
    min_purchase_amount   = DecimalField(default=0)
    buy_quantity          = IntegerField(null=True, blank=True)    # for BUY_X_GET_Y
    get_quantity          = IntegerField(null=True, blank=True)
    applicable_to         = CharField(choices=[ALL, CATEGORY, PRODUCT])
    applicable_products   = ManyToManyField(POSProduct, blank=True)
    applicable_categories = ManyToManyField(POSCategory, blank=True)
    stores                = ManyToManyField(StorePOSConfig, blank=True)  # empty = all stores
    is_active             = BooleanField(default=True)
    start_date            = DateField()
    end_date              = DateField(null=True, blank=True)
    max_uses              = IntegerField(null=True, blank=True)    # None = unlimited
    uses_count            = IntegerField(default=0)
    per_member_limit      = IntegerField(null=True, blank=True)
    requires_member       = BooleanField(default=False)
    min_tier              = CharField(max_length=20, blank=True)   # minimum tier for eligibility


class Voucher(models.Model):
    campaign      = ForeignKey(Campaign, CASCADE, related_name='vouchers')
    code          = CharField(max_length=50, unique=True)
    is_used       = BooleanField(default=False)
    used_by       = ForeignKey('pos_crm.Member', SET_NULL, null=True, blank=True)
    used_in_order = ForeignKey('pos_orders.Order', SET_NULL, null=True, blank=True)
    used_at       = DateTimeField(null=True, blank=True)
    expires_at    = DateTimeField(null=True, blank=True)
    created_at    = DateTimeField(auto_now_add=True)


class OrderPromotion(models.Model):
    order           = ForeignKey('pos_orders.Order', CASCADE, related_name='promotions')
    campaign        = ForeignKey(Campaign, PROTECT)
    voucher         = ForeignKey(Voucher, SET_NULL, null=True, blank=True)
    discount_amount = DecimalField(max_digits=15, decimal_places=2)
    description     = CharField(max_length=200)   # "Diskon 20% - maks Rp 50.000"
```

---

### `pos_reports` App

```python
class DailySalesSnapshot(models.Model):
    """
    Generated at shift close or EOD via report_service.generate_daily_snapshot().
    NOT computed live — queried for fast dashboard loading.
    """
    store                 = ForeignKey(StorePOSConfig, CASCADE, related_name='daily_snapshots')
    date                  = DateField(db_index=True)
    shift_log             = ForeignKey(ShiftLog, SET_NULL, null=True, blank=True)
    total_orders          = IntegerField(default=0)
    total_items           = IntegerField(default=0)
    gross_sales           = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_discount        = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_tax             = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_service_charge  = DecimalField(max_digits=15, decimal_places=2, default=0)
    net_sales             = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cogs            = DecimalField(max_digits=15, decimal_places=2, default=0)
    gross_profit          = DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_collected        = DecimalField(max_digits=15, decimal_places=2, default=0)
    qris_collected        = DecimalField(max_digits=15, decimal_places=2, default=0)
    transfer_collected    = DecimalField(max_digits=15, decimal_places=2, default=0)
    total_refunds         = DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at            = DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('store', 'date')
```

---

### `pos_aggregators` App

```python
class AggregatorConfig(models.Model):
    PLATFORM_GOFOOD     = 'GOFOOD'
    PLATFORM_GRABFOOD   = 'GRABFOOD'
    PLATFORM_SHOPEEFOOD = 'SHOPEEFOOD'
    PLATFORM_SHOPEE     = 'SHOPEE'

    merchant_config         = ForeignKey(MerchantPOSConfig, CASCADE, related_name='aggregator_configs')
    store                   = ForeignKey(StorePOSConfig, CASCADE, related_name='aggregator_configs')
    platform                = CharField(choices=PLATFORM_CHOICES)
    external_merchant_id    = CharField(max_length=200)
    webhook_secret          = CharField(max_length=200, blank=True)
    api_key_encrypted       = CharField(max_length=500, blank=True)   # encrypted via Fernet (cryptography package); add cryptography>=42.0 to requirements
    is_active               = BooleanField(default=False)
    commission_pct          = DecimalField(max_digits=5, decimal_places=2, default=0)
    auto_accept             = BooleanField(default=False)

    class Meta:
        unique_together = ('store', 'platform')


class AggregatorWebhookLog(models.Model):
    aggregator_config = ForeignKey(AggregatorConfig, CASCADE, related_name='webhook_logs')
    received_at       = DateTimeField(auto_now_add=True, db_index=True)
    payload           = JSONField()
    processed         = BooleanField(default=False)
    order             = ForeignKey('pos_orders.Order', SET_NULL, null=True, blank=True)
    error_message     = TextField(blank=True)
```

---

## Service Layer

All business logic lives in `services/` subpackages. Views call services, never direct ORM. Existing apps' services called only from `pos_orders/services/sales_integration.py`.

### `pos_orders/services/`

#### `order_service.py`
```
create_order(store, cashier, order_type, source, shift_log=None) → Order
add_item(order, product, quantity, selected_modifier_option_ids, notes='') → OrderItem
remove_item(order_item) → None
update_item_quantity(order_item, new_qty) → OrderItem
apply_promotion(order, campaign_or_voucher_code) → OrderPromotion
remove_promotion(order, order_promotion) → None
calculate_totals(order) → (subtotal, discount, tax, service_charge, total)
  - applies store tax_inclusive logic
  - sums all OrderPromotion.discount_amount
submit_order(order) → Order   (DRAFT → OPEN, generates order_number)
transition_status(order, new_status, by_user) → Order
  - validates via Order.can_transition_to()
  - fires WebSocket + web push broadcast
process_payment(order, payment_method, amount, reference_number='') → OrderPayment
confirm_payment(order_payment, confirmed_by) → bool (True if order now fully paid)
complete_order(order) → Order
  - calls sales_integration.create_sales_from_order(order)
  - calls member_service.add_points(order.member, order)  if member attached
  - sets completed_at = now()
  - broadcasts to cashier_{store_id} + kitchen_{store_id}
cancel_order(order, reason, by_user) → Order
```

#### `sales_integration.py`
```
create_sales_from_order(order: Order) → SalesHeader
  Creates SalesHeader with transaction_id derived from order_number
  Creates SalesEntitasBisnis using store.entitas_bisnis_lv2.entitas_bisnis
  For each non-CANCELLED OrderItem:
    Creates SalesItem(item_master=item.product.item_master, quantity, selling_price=unit_price)
  Calls existing sales.services.process_fifo_allocation(sales_header)
  Calls existing jurnal.services.run_jurnal_automasi(sales_header)
  Sets order.sales_header = sales_header
  Returns sales_header

reverse_sales_for_refund(refund: Refund) → None
  Calls existing sales.services.reverse_sales_header(refund.order.sales_header)
  Restores FIFO batches
  Creates reversal journal entries
  Updates order.status = REFUNDED
```

#### `refund_service.py`
```
initiate_refund(order, by_user, reason, refund_type, items=None) → Refund
  items: list of {order_item_id, quantity, amount} for partial; None for full
  validates order.status == COMPLETED
approve_refund(refund, by_user) → Refund
complete_refund(refund) → Refund
  calls sales_integration.reverse_sales_for_refund(refund)
  deducts member points if earned on this order
```

#### `push_service.py`
```
send_push_to_store(store_id, role, title, body, data: dict) → None
  queries WebPushSubscription(store_id=store_id, role=role, is_active=True)
  for each sub: pywebpush.webpush(...)
  on WebPushException 410: marks is_active=False

PUSH_TRIGGERS:
  Order.source != POS → notify CASHIER + KITCHEN on new order
  order.status → READY → notify CASHIER
  OrderPayment.is_confirmed → True → notify CASHIER
  Refund.status → PENDING → notify MANAGER
```

#### `receipt_service.py`
```
generate_receipt_text(order: Order) → str
  formats receipt lines (store header, items, modifiers, totals, payment, footer)
  used for on-screen display and ESC/POS printer output

send_to_printer(store: StorePOSConfig, text: str) → None
  opens TCP socket to store.printer_ip:store.printer_port
  encodes text as ESC/POS bytes (cp437 encoding)
  sends and closes — fire and forget, logs failure but does not raise
  no-op if store.printer_ip is blank
```

### `pos_catalog/services/product_service.py`
```
get_available_products(store: StorePOSConfig) → QuerySet[POSProduct]
  filters by POSProduct.is_available + ProductStoreAvailability override
check_stock(product, quantity, entitas_bisnis) → (bool, Decimal)
  queries FIFOBatch.remaining_qty for product.item_master where track_inventory=True
validate_modifier_selections(product, selected_option_ids) → list[str]  (errors)
  checks all required ModifierGroups have selection
  checks min/max per group not violated
```

### `pos_promotions/services/promotion_service.py`
```
get_applicable_campaigns(order: Order) → list[Campaign]
  filters active, within date range, min_purchase met, store in campaign.stores
calculate_discount(campaign, order) → Decimal
validate_voucher(code, order) → (Voucher | None, error_message | None)
apply_voucher(code, order) → OrderPromotion
generate_voucher_codes(campaign, count, prefix='') → list[Voucher]
```

### `pos_crm/services/member_service.py`
```
lookup_member(phone, merchant) → Member | None
register_member(merchant, name, phone, email='', birth_date=None) → Member
add_points(member, order) → MemberPointLog
  points = floor(order.total_amount / 1000) * tier_config.points_per_thousand
redeem_points(member, order, points_to_redeem) → (Decimal, MemberPointLog)
  returns discount_amount applied
check_tier_upgrade(member) → bool (True if tier changed)
  compares member.total_spent against MemberTierConfig thresholds
```

### `pos_reports/services/report_service.py`
```
get_sales_summary(store, date_from, date_to) → dict
  queries Order(status=COMPLETED) for period
get_top_products(store, date_from, date_to, limit=10) → list[(POSProduct, qty, revenue)]
  annotates OrderItem aggregated by product
get_payment_breakdown(store, date_from, date_to) → dict[method_type → total]
get_laba_rugi(store, date_from, date_to) → dict
  gross_sales, net_sales, cogs (from SalesItemFIFOAllocation), gross_profit, expenses
generate_daily_snapshot(store, date) → DailySalesSnapshot
  called at ShiftLog.clock_out or manual trigger
```

---

## WebSocket Architecture

### New Files
```
naveda_integra/asgi.py
pos_orders/consumers.py
pos_orders/routing.py
pos_orders/events.py
```

### Consumer (`pos_orders/consumers.py`)
```python
class CashierConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        store_id = self.scope['url_route']['kwargs']['store_id']
        # Verify user has pos.view_cashier permission for this store
        self.group = f"cashier_{store_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def order_update(self, event):
        await self.send_json(event['data'])


class KitchenConsumer(AsyncJsonWebsocketConsumer):
    # Same pattern, group = f"kitchen_{store_id}"
```

### WebSocket URLs
```
ws/pos/cashier/<int:store_id>/
ws/pos/kitchen/<int:store_id>/
```

### Event Schemas
```json
// New order
{"event": "order.new", "order_number": "ORD-...", "source": "GOFOOD",
 "items": ["Nasi Goreng x2"], "total": 85000, "table": "5"}

// Status changed
{"event": "order.status", "order_number": "ORD-...", "status": "READY",
 "timestamp": "2026-05-05T10:30:00+07:00"}

// Payment confirmed
{"event": "order.payment_confirmed", "order_number": "ORD-...",
 "method": "QRIS", "amount": 85000}
```

### Broadcast Helper (`pos_orders/events.py`)
```python
async def broadcast(store_id: int, group_prefix: str, event_type: str, data: dict):
    layer = get_channel_layer()
    await layer.group_send(
        f"{group_prefix}_{store_id}",
        {"type": "order.update", "data": {"event": event_type, **data}}
    )
```
Called from `order_service.py` via `async_to_sync(broadcast)(...)` since services are sync.

---

## Web Push Notifications

### VAPID Setup
Generate once per deployment:
```bash
python -c "from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print(v.public_key, v.private_key)"
```
Store in env: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL`.

### Client-Side Flow
```
Browser loads cashier screen
  → push-manager.js runs
  → GET /pos/push/vapid-key/ → gets public key
  → Notification.requestPermission()
  → serviceWorker.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: vapidKey})
  → POST /pos/push/subscribe/ {endpoint, keys.p256dh, keys.auth, role}
  → Server saves WebPushSubscription
```

### Service Worker (`static/js/pos/service-worker.js`)
```javascript
self.addEventListener('push', event => {
    const data = event.data.json();
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/pos/icon-192.png',
            badge: '/static/pos/badge-72.png',
            data: {url: data.url},
            tag: data.order_number,   // replaces duplicate notifications per order
            renotify: true
        })
    );
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url));
});
```

### Push Triggers by Role

| Event | CASHIER | KITCHEN | MANAGER |
|-------|---------|---------|---------|
| New order (aggregator source) | ✓ | ✓ | — |
| New order (another POS terminal) | ✓ | ✓ | — |
| Order status → READY | ✓ | — | — |
| Payment confirmed (QRIS/Transfer) | ✓ | — | — |
| Refund requested | — | — | ✓ |

### In-Screen UI Markers (when tab is active)
- Animated card injected at top of order queue on `order.new` WebSocket event
- Pulsing red dot badge on "Pesanan" sidebar nav item
- Browser tab title prefix: `(N) Kasir — Naveda POS` where N = unread orders
- `AudioContext` beep (short tone, no audio file needed) on new order

---

## Permissions (RBAC Extension)

New entries in `config/roles_permissions.toml`:

```toml
[permissions.pos]
pos.view_cashier     = {roles = ["admin", "operator", "business_owner", "business_employee", "kasir"]}
pos.manage_orders    = {roles = ["admin", "operator", "business_owner", "business_employee", "kasir"]}
pos.approve_refund   = {roles = ["admin", "operator", "business_owner"]}
pos.manage_products  = {roles = ["admin", "operator", "business_owner"]}
pos.manage_config    = {roles = ["admin", "operator", "business_owner"]}
pos.view_reports     = {roles = ["admin", "operator", "business_owner"]}
pos.manage_members   = {roles = ["admin", "operator", "business_owner"]}
pos.manage_promotions = {roles = ["admin", "operator", "business_owner"]}
pos.manage_aggregators = {roles = ["admin", "operator", "business_owner"]}
```

New role `kasir` (Cashier):
- Scope: cashier screen, order management only
- No access to: product management, config, reports, member management
- Access via `UserEntitasBisnis` — scoped to their assigned store

---

## Integration With Existing Modules

### Sales Integration
`pos_orders/services/sales_integration.create_sales_from_order()` creates standard `SalesHeader` / `SalesEntitasBisnis` / `SalesItem` records. The resulting records are indistinguishable from a manual Sales entry. This means:
- Full FIFO allocation runs (existing `sales/services.py`)
- Journal automation fires (existing `jurnal` app)
- Piutang can be created if payment_account is AR
- All financial reports (Neraca, Laba Rugi) automatically include POS sales

### Inventory Integration
`product_service.check_stock()` queries `FIFOBatch.remaining_qty` for the product's `ItemMasterPurchase`. On order completion, FIFO batches are consumed via existing allocation logic. `POSProduct.track_inventory = False` skips this check (for service items, combos).

### Manufacturing Integration
Finished goods produced via `ProductionOrder` appear in FIFO batches and are sellable via POS. No changes needed to manufacturing app.

### Purchase Integration
New products purchased via `PurchaseHeader` → `ItemMasterPurchase` → can be linked to `POSProduct`. The OneToOne relationship means a product must exist in purchase master before being sold on POS. This enforces accounting completeness.

---

## URL Structure

```
/pos/                         → POS home / store selector
/pos/cashier/<store_id>/      → Cashier screen
/pos/queue/<store_id>/        → Order queue / kitchen display
/pos/orders/                  → Order list (management)
/pos/orders/<pk>/             → Order detail
/pos/catalog/                 → Product list
/pos/catalog/create/          → New product
/pos/catalog/<pk>/            → Product detail/edit
/pos/modifiers/               → Modifier group list
/pos/modifiers/create/
/pos/modifiers/<pk>/
/pos/members/                 → Member list
/pos/members/<pk>/            → Member detail + transaction history
/pos/promotions/              → Campaign list
/pos/promotions/create/
/pos/promotions/<pk>/
/pos/promotions/<pk>/vouchers/ → Voucher list + generation
/pos/reports/                 → Reports dashboard
/pos/reports/daily/           → Daily summary
/pos/reports/products/        → Top products
/pos/reports/payments/        → Payment breakdown
/pos/config/                  → Merchant config
/pos/config/stores/           → Store list
/pos/config/stores/<pk>/      → Store config edit
/pos/shifts/                  → Shift management
/pos/aggregators/             → Aggregator config list
/pos/aggregators/<pk>/        → Aggregator config edit

/pos/push/vapid-key/          → GET: returns VAPID public key
/pos/push/subscribe/          → POST: save WebPushSubscription
/pos/push/unsubscribe/        → POST: deactivate subscription
/pos/aggregators/webhook/<platform>/<store_id>/  → POST: inbound webhook

ws/pos/cashier/<store_id>/    → WebSocket cashier
ws/pos/kitchen/<store_id>/    → WebSocket kitchen
```

---

## Frontend Overview

All screens use existing `ni-` design system (no new CSS framework). Vanilla JS + service worker.

### Cashier Screen (`/pos/cashier/<store_id>/`)
- **Left panel (60%):** Product grid with category tab filter at top. Search bar. Product cards: image, name, price, availability indicator. Click to add (opens modifier selection modal if product has required modifiers).
- **Right panel (40%):** Order builder. Customer name / table number fields. Member phone lookup (inline, shows tier + points). Item list: product name, modifier summary, qty stepper, item subtotal, remove button. Promotion code input. Totals breakdown: subtotal, diskon, pajak, service charge, **TOTAL**. Action: "Bayar" button → opens payment modal.
- **Top bar:** Store name, shift status, cashier name, order count badge.
- **New order marker:** Animated banner drops from top when `order.new` WebSocket event received. Tab title updates to `(N) Kasir`.

### Payment Modal
- Order total + breakdown
- Payment method buttons (icons per type)
- Cash selected: shows "Uang Diterima" input + computed "Kembalian"
- QRIS selected: shows `MerchantPOSConfig.qris_image` full-size + "Konfirmasi Pembayaran Diterima" button
- Transfer selected: reference number input + confirm button
- Split payment: "+ Tambah Pembayaran" to add multiple rows
- Submit: disabled until all payments confirmed and total covered

### Order Queue / Kitchen Display (`/pos/queue/<store_id>/`)
- Three columns: **Menunggu** / **Diproses** / **Siap**
- Order cards: order number, source badge (POS/GoFood/etc.), items, time elapsed
- Tap/click card → advance to next status
- WebSocket-driven column updates
- Suitable for tablet mounted in kitchen

### Management Pages
Follow existing `ni-` table + form pattern:
- Product list: sortable table, filter by category, availability toggle
- Product form: fields + modifier group assignment (checkboxes with reorder)
- Modifier group builder: group fields + nested option rows (add/remove dynamically)
- Member list: search by name/phone, filter by tier
- Campaign builder: type selector shows/hides relevant fields (BUY_X_GET_Y shows buy/get qty, VOUCHER shows generate button)
- Shift close form: closing_cash input + auto-generated summary card

### Reports (`/pos/reports/`)
- Date range picker (existing pattern)
- Summary cards: Total Pesanan, Penjualan Kotor, Penjualan Bersih, Laba Kotor
- Chart.js line chart: daily net sales trend
- Top 10 Produk table: rank, product name, qty sold, revenue
- Pembayaran pie chart: Cash / QRIS / Transfer breakdown
- Laba/Rugi card: Net Sales - COGS = Laba Kotor, + Pengeluaran row (links to existing Jurnal Beban)
- Export: Excel (openpyxl, existing pattern) + PDF

---

## TDD Strategy

All tests written before implementation per app. Uses Django's built-in `TestCase` (existing pattern). Run with `python manage.py test`.

```
pos_config/tests/
  test_models.py
    - StorePOSConfig.effective_tax_pct() returns store value if set, merchant default if null
    - ShiftLog.is_active returns True when clock_out is None
    - WebPushSubscription unique_together enforced
  test_views.py
    - CRUD requires pos.manage_config permission
    - User without permission gets 302/403

pos_catalog/tests/
  test_models.py
    - ModifierGroup.clean() raises if min > max
    - ModifierGroup.clean() raises if is_required and min_selections < 1
  test_services.py
    - get_available_products respects ProductStoreAvailability override
    - check_stock queries correct EntitasBisnis FIFOBatch
    - validate_modifier_selections catches missing required group
    - validate_modifier_selections catches exceeding max_selections

pos_orders/tests/
  test_models.py
    - Order.can_transition_to() allows valid transitions only
    - Order.recalculate_totals() correct with tax_inclusive=True
    - Order.recalculate_totals() correct with tax_inclusive=False
    - Order.is_fully_paid() True only when confirmed payments >= total
  test_order_service.py
    - Full lifecycle: create→add_item→modifier→apply_promo→pay_cash→complete
    - Split payment flow: partial cash + partial QRIS (unconfirmed) → not complete until confirmed
    - Cancel order before COMPLETED → no SalesHeader created
    - Modifier price snapshot preserved after ModifierOption price change
  test_sales_integration.py  ← CRITICAL INTEGRATION TEST
    - create_sales_from_order creates SalesHeader with correct items and quantities
    - FIFO batches consumed (FIFOBatch.remaining_qty decremented correctly)
    - Journal entries balance: sum(debit) == sum(credit)
    - order.sales_header set correctly
    - Inventory records updated
  test_refund_service.py
    - Full refund reverses SalesHeader and restores FIFO batches
    - Member points deducted on refund completion
  test_consumers.py
    - WebsocketCommunicator connects and receives order.new event
    - order.status event broadcast on transition_status call
  test_push_service.py
    - WebPushSubscription marked is_active=False on 410 response

pos_crm/tests/
  test_models.py
    - Member unique_together (merchant_config, phone) enforced
  test_services.py
    - add_points uses correct tier config points_per_thousand
    - check_tier_upgrade promotes member at correct total_spent threshold
    - redeem_points deducts from member.points and creates negative MemberPointLog

pos_promotions/tests/
  test_models.py
    - Voucher.is_used enforced (cannot apply same voucher twice)
  test_services.py
    - calculate_discount DISCOUNT_PCT respects max_discount_cap
    - BUY_X_GET_Y applies only to applicable_products
    - validate_voucher rejects expired voucher
    - validate_voucher rejects exceeded per_member_limit
    - apply_voucher marks Voucher.is_used = True

pos_reports/tests/
  test_report_service.py
    - generate_daily_snapshot gross_sales == sum of Order.total_amount for that date
    - net_sales == gross_sales - total_discount
    - cogs matches sum of SalesItemFIFOAllocation.cogs_amount

pos_aggregators/tests/
  test_webhook.py
    - Ingest mock GoFood payload → creates Order with source=GOFOOD, correct items
    - Duplicate external_order_id rejected
    - Invalid webhook signature returns 403
    - Failed parsing creates AggregatorWebhookLog with processed=False + error_message
```

---

## Phased Implementation Plan

| Phase | Apps | Effort | Gate |
|-------|------|--------|------|
| **1 — Foundation** | `pos_config`, `pos_catalog` | 2 weeks | All model tests passing. Product + modifier CRUD working. VAPID keys generated. |
| **2 — Order Engine** | `pos_orders` (models + services + WebSocket) | 2 weeks | Working cashier screen. Orders flow DRAFT→COMPLETED. WebSocket events in browser. Push notification fires on new order. |
| **3 — Sales Integration** | `pos_orders/services/sales_integration.py` | 1 week | Completed order produces balanced SalesHeader + FIFO + Journal. Refund flow reverses correctly. Critical integration tests passing. |
| **4 — CRM + Promotions** | `pos_crm`, `pos_promotions` | 2 weeks | Member lookup in cashier. Points earned + redeemed. Voucher applied to order. Campaign discounts calculated. |
| **5 — Reports** | `pos_reports` | 1 week | All report views rendering. DailySalesSnapshot generates on shift close. Export working. |
| **6 — Aggregators** | `pos_aggregators` | 2 weeks | Webhook endpoints live per platform. Orders ingested with correct source. Aggregator config UI. |

**Total estimated: ~10 weeks**

---

## AI Agent Reference Notes

Agents implementing this plan should reference the following existing code:

| Need | Existing File | Pattern to Follow |
|------|--------------|-------------------|
| Function-based views | `apps/sales/views.py` | `@login_required`, `_check_perm()`, `JsonResponse` for AJAX |
| Service layer pattern | `apps/sales/services.py` | Pure functions, no request object, return model instances |
| FIFO allocation | `apps/sales/services.py:process_fifo_allocation()` | Called after SalesItem creation |
| Journal automation | `apps/jurnal/services.py` (or signals) | `run_jurnal_automasi(sales_header)` |
| Auto-generated IDs | `apps/purchase/models.py:ItemMasterPurchase.save()` | Sequential ID generation pattern |
| Permission check | `apps/accounts/views.py:_check_perm()` | Reuse this helper |
| ni- form classes | `apps/sales/forms.py` | `attrs={'class': 'ni-input'}` on all widgets |
| Excel export | `apps/sales/views.py:sales_export()` | openpyxl pattern |
| PDF generation | `apps/sales/views.py:sales_invoice()` | Django template → PDF |
| Multi-entity access | `apps/entitas_bisnis/models.py` | `UserEntitasBisnis` junction table scoping |
| TOML permissions | `config/roles_permissions.toml` + `apps/accounts/management/commands/sync_roles_permissions.py` | Add new codes, re-run sync command |
| Test pattern | `apps/accounts/tests.py` | `TestCase`, `setUp`, no mocking of database |

**Critical invariant:** Every completed POS `Order` must produce a `SalesHeader` where `sum(JurnalDetail.debit) == sum(JurnalDetail.credit)`. The integration test in `pos_orders/tests/test_sales_integration.py` must verify this before Phase 3 is considered complete.

**Never:** Import from `pos_*` apps inside existing apps (`sales`, `purchase`, `inventory`, etc.). The dependency always flows inward: POS → existing, never existing → POS.
