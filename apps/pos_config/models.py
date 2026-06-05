from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3


class MerchantPOSConfig(models.Model):
    entitas_bisnis = models.OneToOneField(
        EntitasBisnis, on_delete=models.CASCADE, related_name='pos_config'
    )
    is_pos_active = models.BooleanField(default=False)
    logo = models.ImageField(upload_to='pos/logos/', null=True, blank=True)
    qris_image = models.ImageField(upload_to='pos/qris/', null=True, blank=True)
    default_tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    default_service_charge_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    tax_inclusive = models.BooleanField(default=False)
    currency = models.CharField(max_length=3, default='IDR')
    revenue_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_revenue_merchant',
        help_text='Akun pendapatan default untuk penjualan POS',
    )
    offset_coa_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_merchant_offset',
        verbose_name='HPP Account',
        help_text='Akun HPP — digunakan sebagai offset_coa_account di SalesItem.',
    )
    default_payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_merchant_payment',
        verbose_name='Default Payment Account',
        help_text='Akun kas/piutang default jika PaymentMethod tidak punya payment_account sendiri.',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_merchant_configs',
        verbose_name='Sub-Transaction Type',
        help_text='Sub-tipe transaksi penjualan POS (module=sales, direction=outflow).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Merchant POS Config'

    def __str__(self):
        return f'POS Config — {self.entitas_bisnis.nama}'


class StorePOSConfig(models.Model):
    PRINTER_EPSON = 'EPSON_TM'
    PRINTER_STAR = 'STAR_TSP'
    PRINTER_GENERIC = 'GENERIC_ESCPOS'
    PRINTER_CHOICES = [
        (PRINTER_EPSON, 'Epson TM Series'),
        (PRINTER_STAR, 'Star TSP Series'),
        (PRINTER_GENERIC, 'Generic ESC/POS'),
    ]

    entitas_bisnis_lv2 = models.OneToOneField(
        EntitasBisnisLv2, on_delete=models.CASCADE, related_name='pos_config'
    )
    merchant_config = models.ForeignKey(
        MerchantPOSConfig, on_delete=models.CASCADE, related_name='stores'
    )
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    service_charge_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    printer_type = models.CharField(max_length=20, choices=PRINTER_CHOICES, blank=True)
    printer_ip = models.GenericIPAddressField(null=True, blank=True)
    printer_port = models.IntegerField(default=9100)
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.entitas_bisnis_lv2.nama} — {self.merchant_config.entitas_bisnis.nama}'

    def effective_tax_pct(self) -> Decimal:
        return self.tax_pct if self.tax_pct is not None else self.merchant_config.default_tax_pct

    def effective_service_charge_pct(self) -> Decimal:
        return (
            self.service_charge_pct
            if self.service_charge_pct is not None
            else self.merchant_config.default_service_charge_pct
        )


class PaymentMethod(models.Model):
    CASH = 'CASH'
    QRIS = 'QRIS'
    TRANSFER = 'TRANSFER'
    OTHER = 'OTHER'
    METHOD_CHOICES = [
        (CASH, 'Tunai'),
        (QRIS, 'QRIS'),
        (TRANSFER, 'Transfer Bank'),
        (OTHER, 'Lainnya'),
    ]

    merchant_config = models.ForeignKey(
        MerchantPOSConfig, on_delete=models.CASCADE, related_name='payment_methods'
    )
    store = models.ForeignKey(
        StorePOSConfig, on_delete=models.CASCADE, null=True, blank=True,
        related_name='payment_methods'
    )
    name = models.CharField(max_length=100)
    method_type = models.CharField(max_length=20, choices=METHOD_CHOICES)
    offset_coa_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_payment_method_offset',
        help_text='Akun debit saat pembayaran diterima (Kas, Bank, dll)',
    )
    payment_account = models.ForeignKey(
        'master_data.Akun', on_delete=models.PROTECT, null=True, blank=True,
        related_name='pos_payment_method_account',
        verbose_name='Payment Account',
        help_text='Akun kas/bank untuk metode ini. Override merchant default_payment_account.',
    )
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_method_type_display()})'


class WorkShift(models.Model):
    store = models.ForeignKey(StorePOSConfig, on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name} ({self.start_time}–{self.end_time})'


class ShiftLog(models.Model):
    store = models.ForeignKey(StorePOSConfig, on_delete=models.CASCADE, related_name='shift_logs')
    shift = models.ForeignKey(WorkShift, on_delete=models.PROTECT, related_name='logs')
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='shift_logs'
    )
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    closing_cash = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.employee.name} — {self.shift.name} {self.clock_in.date()}'

    @property
    def is_active(self) -> bool:
        return self.clock_out is None


class WebPushSubscription(models.Model):
    ROLE_CASHIER = 'CASHIER'
    ROLE_KITCHEN = 'KITCHEN'
    ROLE_MANAGER = 'MANAGER'
    ROLE_CHOICES = [
        (ROLE_CASHIER, 'Kasir'),
        (ROLE_KITCHEN, 'Dapur'),
        (ROLE_MANAGER, 'Manajer'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_subscriptions'
    )
    store = models.ForeignKey(
        StorePOSConfig, on_delete=models.CASCADE, related_name='push_subscriptions'
    )
    endpoint = models.URLField(max_length=500)
    p256dh_key = models.CharField(max_length=200)
    auth_key = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CASHIER)
    user_agent = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'endpoint')


class OutletPOSConfig(models.Model):
    """Lv3-specific POS config. Overrides MerchantPOSConfig (lv1) for STT + accounts."""

    entitas_bisnis_lv3 = models.OneToOneField(
        EntitasBisnisLv3,
        on_delete=models.CASCADE,
        related_name='pos_config',
    )
    merchant_config = models.ForeignKey(
        MerchantPOSConfig,
        on_delete=models.CASCADE,
        related_name='outlets',
    )
    sub_transaction_type = models.ForeignKey(
        'purchase.SubTransactionType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_configs',
        verbose_name='Sub-Transaction Type (Override)',
        help_text='Kosongkan = pakai default dari Merchant (lv1).',
    )
    revenue_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_revenue',
        verbose_name='Revenue Account (Override)',
    )
    offset_coa_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_offset',
        verbose_name='HPP Account (Override)',
    )
    default_payment_account = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='pos_outlet_payment',
        verbose_name='Payment Account (Override)',
    )
    tax_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Tax % (Override)',
        help_text='Kosongkan = pakai default dari Store (lv2) atau Merchant (lv1).',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Outlet POS Config'

    def __str__(self) -> str:
        return f'Outlet POS Config — {self.entitas_bisnis_lv3.nama}'
