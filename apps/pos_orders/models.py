from decimal import Decimal
from django.conf import settings
from django.db import models
from django.db.models import Sum
from pos_config.models import StorePOSConfig, PaymentMethod, ShiftLog


class Order(models.Model):
    SOURCE_POS = 'POS'
    SOURCE_GOFOOD = 'GOFOOD'
    SOURCE_GRABFOOD = 'GRABFOOD'
    SOURCE_SHOPEEFOOD = 'SHOPEEFOOD'
    SOURCE_SHOPEE = 'SHOPEE'
    SOURCE_OTHER = 'OTHER'
    SOURCE_CHOICES = [
        (SOURCE_POS, 'POS'),
        (SOURCE_GOFOOD, 'GoFood'),
        (SOURCE_GRABFOOD, 'GrabFood'),
        (SOURCE_SHOPEEFOOD, 'ShopeeFood'),
        (SOURCE_SHOPEE, 'Shopee'),
        (SOURCE_OTHER, 'Lainnya'),
    ]

    STATUS_DRAFT = 'DRAFT'
    STATUS_OPEN = 'OPEN'
    STATUS_IN_QUEUE = 'IN_QUEUE'
    STATUS_PREPARING = 'PREPARING'
    STATUS_READY = 'READY'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_REFUNDED = 'REFUNDED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_OPEN, 'Terbuka'),
        (STATUS_IN_QUEUE, 'Dalam Antrian'),
        (STATUS_PREPARING, 'Diproses'),
        (STATUS_READY, 'Siap'),
        (STATUS_COMPLETED, 'Selesai'),
        (STATUS_CANCELLED, 'Dibatalkan'),
        (STATUS_REFUNDED, 'Direfund'),
    ]

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

    ORDER_TYPE_DINE_IN = 'DINE_IN'
    ORDER_TYPE_TAKEAWAY = 'TAKEAWAY'
    ORDER_TYPE_DELIVERY = 'DELIVERY'
    ORDER_TYPE_CHOICES = [
        (ORDER_TYPE_DINE_IN, 'Makan di Tempat'),
        (ORDER_TYPE_TAKEAWAY, 'Bawa Pulang'),
        (ORDER_TYPE_DELIVERY, 'Pesan Antar'),
    ]

    order_number = models.CharField(max_length=50, unique=True, blank=True, null=True, default=None)
    store = models.ForeignKey(StorePOSConfig, on_delete=models.PROTECT, related_name='orders')
    shift_log = models.ForeignKey(ShiftLog, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cashier_orders')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_POS)
    external_order_id = models.CharField(max_length=100, blank=True)
    external_order_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default=ORDER_TYPE_DINE_IN)
    table_number = models.CharField(max_length=20, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    # member FK to pos_crm.Member will be added in Phase 4 migration once pos_crm app is installed
    # member = models.ForeignKey('pos_crm.Member', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    service_charge_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    notes = models.TextField(blank=True)
    sales_header = models.OneToOneField(
        'sales.SalesHeader', on_delete=models.SET_NULL, null=True, blank=True, related_name='pos_order'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_number} ({self.get_status_display()})'

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def is_fully_paid(self) -> bool:
        confirmed = self.payments.filter(is_confirmed=True).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        return confirmed >= self.total_amount

    def recalculate_totals(self) -> None:
        items_total = self.items.exclude(status='CANCELLED').aggregate(
            total=Sum('subtotal')
        )['total'] or Decimal('0')

        try:
            promotions_total = self.promotions.aggregate(
                total=Sum('discount_amount')
            )['total'] or Decimal('0')
        except Exception:
            promotions_total = Decimal('0')

        subtotal_after_discount = items_total - promotions_total

        tax_pct = self.store.effective_tax_pct()
        svc_pct = self.store.effective_service_charge_pct()

        if self.store.merchant_config.tax_inclusive:
            tax = (subtotal_after_discount * tax_pct / (100 + tax_pct)).quantize(Decimal('0.01'))
            net = subtotal_after_discount - tax
        else:
            tax = (subtotal_after_discount * tax_pct / 100).quantize(Decimal('0.01'))
            net = subtotal_after_discount

        svc = (subtotal_after_discount * svc_pct / 100).quantize(Decimal('0.01'))

        self.subtotal = items_total
        self.discount_amount = promotions_total
        self.tax_amount = tax
        self.service_charge_amount = svc
        self.total_amount = (subtotal_after_discount + tax + svc).quantize(Decimal('0.01'))
        self.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'service_charge_amount', 'total_amount'])


class OrderItem(models.Model):
    ITEM_STATUS_PENDING = 'PENDING'
    ITEM_STATUS_PREPARING = 'PREPARING'
    ITEM_STATUS_READY = 'READY'
    ITEM_STATUS_CANCELLED = 'CANCELLED'
    ITEM_STATUS_CHOICES = [
        (ITEM_STATUS_PENDING, 'Menunggu'),
        (ITEM_STATUS_PREPARING, 'Diproses'),
        (ITEM_STATUS_READY, 'Siap'),
        (ITEM_STATUS_CANCELLED, 'Dibatalkan'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('pos_catalog.POSProduct', on_delete=models.PROTECT, related_name='order_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    modifier_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    subtotal = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=ITEM_STATUS_CHOICES, default=ITEM_STATUS_PENDING)

    def __str__(self):
        return f'{self.product.pos_name} x{self.quantity}'


class OrderItemModifier(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='modifiers')
    modifier_option = models.ForeignKey('pos_catalog.ModifierOption', on_delete=models.PROTECT)
    option_name_snapshot = models.CharField(max_length=100)
    group_name_snapshot = models.CharField(max_length=100)
    price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)


class OrderPayment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reference_number = models.CharField(max_length=100, blank=True)
    is_confirmed = models.BooleanField(default=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='confirmed_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Refund(models.Model):
    REFUND_FULL = 'FULL'
    REFUND_PARTIAL = 'PARTIAL'
    REFUND_STATUS_PENDING = 'PENDING'
    REFUND_STATUS_APPROVED = 'APPROVED'
    REFUND_STATUS_COMPLETED = 'COMPLETED'
    REFUND_STATUS_REJECTED = 'REJECTED'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='refunds')
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='initiated_refunds'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_refunds'
    )
    reason = models.TextField()
    refund_type = models.CharField(max_length=10, choices=[(REFUND_FULL, 'Full'), (REFUND_PARTIAL, 'Parsial')])
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    refund_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=[
        (REFUND_STATUS_PENDING, 'Menunggu'),
        (REFUND_STATUS_APPROVED, 'Disetujui'),
        (REFUND_STATUS_COMPLETED, 'Selesai'),
        (REFUND_STATUS_REJECTED, 'Ditolak'),
    ], default=REFUND_STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RefundItem(models.Model):
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name='items')
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
