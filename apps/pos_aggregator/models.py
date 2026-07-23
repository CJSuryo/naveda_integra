"""Data model for GoFood / GrabFood / ShopeeFood integration.

Ownership follows the EntitasBisnis hierarchy:

* ``AggregatorCredential`` hangs off ``MerchantPOSConfig`` (EntitasBisnis lv2) —
  the operating company is the merchant account holder.
* ``AggregatorStoreLink`` hangs off ``StorePOSConfig`` (EntitasBisnis lv3) —
  a branch is what maps to an aggregator outlet.

``AggregatorOrder`` owns the *delivery lifecycle*, which Sales cannot express
(accepted / preparing / driver arrived / cancelled). Once an order is releasable
it is posted into ``SalesHeader``/``SalesItem`` through the same path the cashier
screen uses, so accounting keeps a single source of truth.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from pos_config.models import MerchantPOSConfig, StorePOSConfig

from . import crypto
from .constants import (
    AggregatorType, Environment, LinkStatus, OnboardingState, OrderStatus,
    OrderType, POSTrigger, SyncStatus, WebhookStatus,
)


class AggregatorCredential(models.Model):
    """Per-merchant, per-aggregator credentials and behaviour flags.

    Secrets are encrypted at rest; the ``*_encrypted`` columns never contain
    plaintext. Read and write them through the ``client_secret``,
    ``access_token``, ``refresh_token`` and ``webhook_secret`` properties.
    """

    merchant_config = models.ForeignKey(
        MerchantPOSConfig, on_delete=models.CASCADE, related_name='aggregator_credentials'
    )
    aggregator = models.CharField(max_length=20, choices=AggregatorType.choices)

    country = models.CharField(max_length=2, default='ID')
    environment = models.CharField(
        max_length=20, choices=Environment.choices, default=Environment.PRODUCTION
    )

    # --- Identity ---
    client_id = models.CharField(max_length=255, blank=True)
    client_secret_encrypted = models.TextField(blank=True)
    #: GoFood direct-integration chain id. Unused in the facilitator model.
    enterprise_id = models.CharField(max_length=255, blank=True)

    # --- OAuth tokens ---
    access_token_encrypted = models.TextField(blank=True)
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    refresh_token_expires_at = models.DateTimeField(null=True, blank=True)

    # --- Inbound webhook verification ---
    webhook_secret_encrypted = models.TextField(blank=True)

    # --- Behaviour ---
    pos_trigger = models.CharField(
        max_length=20, choices=POSTrigger.choices, default=POSTrigger.ON_CREATED,
        verbose_name='Kirim ke dapur saat',
        help_text='Kapan pesanan diteruskan ke dapur. Default: saat pesanan masuk.',
    )
    tax_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name='Tax % channel ini',
        help_text='Kosongkan = ikut konfigurasi merchant.',
    )
    #: Markup applied to catalog prices when publishing to this channel, to
    #: absorb the aggregator's commission.
    price_markup_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        verbose_name='Markup harga %',
        help_text='Menaikkan harga jual di channel ini untuk menutup komisi aggregator.',
    )
    auto_accept_orders = models.BooleanField(
        default=True,
        help_text='Terima pesanan otomatis. Matikan jika dapur ingin konfirmasi manual.',
    )

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('merchant_config', 'aggregator')
        verbose_name = 'Kredensial Aggregator'
        verbose_name_plural = 'Kredensial Aggregator'
        indexes = [
            models.Index(fields=['aggregator', 'is_active'], name='idx_aggcred_type_active'),
        ]

    def __str__(self):
        return f'{self.get_aggregator_display()} — {self.merchant_config.entitas_bisnis_lv2.nama}'

    # --- Encrypted field accessors ---

    def _get_secret(self, field_name: str) -> str:
        return crypto.decrypt(getattr(self, field_name))

    def _set_secret(self, field_name: str, value: str) -> None:
        setattr(self, field_name, crypto.encrypt(value or ''))

    @property
    def client_secret(self) -> str:
        return self._get_secret('client_secret_encrypted')

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        self._set_secret('client_secret_encrypted', value)

    @property
    def access_token(self) -> str:
        return self._get_secret('access_token_encrypted')

    @access_token.setter
    def access_token(self, value: str) -> None:
        self._set_secret('access_token_encrypted', value)

    @property
    def refresh_token(self) -> str:
        return self._get_secret('refresh_token_encrypted')

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        self._set_secret('refresh_token_encrypted', value)

    @property
    def webhook_secret(self) -> str:
        return self._get_secret('webhook_secret_encrypted')

    @webhook_secret.setter
    def webhook_secret(self, value: str) -> None:
        self._set_secret('webhook_secret_encrypted', value)

    @property
    def masked_client_secret(self) -> str:
        try:
            return crypto.mask(self.client_secret)
        except crypto.DecryptionError:
            return '⚠ tidak terbaca'

    @property
    def template(self):
        from .config_templates import get_template
        return get_template(self.aggregator, self.country, self.environment)

    def effective_tax_pct(self) -> Decimal:
        if self.tax_pct is not None:
            return self.tax_pct
        return self.merchant_config.default_tax_pct


class AggregatorStoreLink(models.Model):
    """Maps one branch (lv3) to one outlet on one aggregator."""

    store_config = models.ForeignKey(
        StorePOSConfig, on_delete=models.CASCADE, related_name='aggregator_links'
    )
    credential = models.ForeignKey(
        AggregatorCredential, on_delete=models.CASCADE, related_name='store_links'
    )
    aggregator = models.CharField(max_length=20, choices=AggregatorType.choices)

    #: The aggregator's own identifier for this outlet.
    external_store_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_store_name = models.CharField(max_length=255, blank=True)
    external_store_address = models.TextField(blank=True)

    status = models.CharField(
        max_length=20, choices=LinkStatus.choices, default=LinkStatus.NOT_LINKED
    )
    status_detail = models.TextField(blank=True)

    #: Grab blocks re-activation for a period; this records when we last asked.
    activation_requested_at = models.DateTimeField(null=True, blank=True)
    linked_at = models.DateTimeField(null=True, blank=True)

    menu_sync_status = models.CharField(
        max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    menu_synced_at = models.DateTimeField(null=True, blank=True)
    menu_sync_detail = models.TextField(blank=True)

    is_accepting_orders = models.BooleanField(
        default=False,
        help_text='Outlet menerima pesanan di aggregator. Dimatikan saat tutup.',
    )
    is_live = models.BooleanField(
        default=False,
        help_text='Sudah lulus pemeriksaan dan boleh menerima pesanan sungguhan.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ('store_config', 'aggregator'),
        ]
        constraints = [
            # Two branches must never claim the same outlet: that silently routes
            # one store's orders into another store's kitchen and books the
            # revenue against the wrong entity.
            models.UniqueConstraint(
                fields=['aggregator', 'external_store_id'],
                condition=models.Q(external_store_id__gt=''),
                name='uniq_aggregator_external_store',
            ),
        ]
        verbose_name = 'Hubungan Cabang–Aggregator'
        verbose_name_plural = 'Hubungan Cabang–Aggregator'

    def __str__(self):
        return f'{self.get_aggregator_display()} — {self.store_config.entitas_bisnis_lv3.nama}'


class AggregatorItemSetting(models.Model):
    """Per-channel price and availability override for a catalog item.

    The same dish is usually priced higher on delivery channels than in store,
    because the aggregator takes a commission. Without this the merchant eats
    the commission on every order.
    """

    credential = models.ForeignKey(
        AggregatorCredential, on_delete=models.CASCADE, related_name='item_settings'
    )
    catalog_item = models.ForeignKey(
        'pos_catalog.CatalogItem', on_delete=models.CASCADE, related_name='aggregator_settings'
    )
    price = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        help_text='Kosongkan = harga katalog + markup channel.',
    )
    is_available = models.BooleanField(default=True)
    external_item_id = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('credential', 'catalog_item')
        verbose_name = 'Harga Item per Channel'
        verbose_name_plural = 'Harga Item per Channel'

    def __str__(self):
        return f'{self.catalog_item} @ {self.credential.get_aggregator_display()}'

    def effective_price(self) -> Decimal:
        if self.price is not None:
            return self.price
        base = self.catalog_item.selling_price
        markup = self.credential.price_markup_pct or Decimal('0')
        return (base * (Decimal('100') + markup) / Decimal('100')).quantize(Decimal('0.01'))


class WebhookEvent(models.Model):
    """Durable record of every inbound aggregator call.

    Written *before* any processing, so an order survives a crashed worker, a
    lost broker message or a bug in normalisation. This table is what makes
    replay possible; the Celery queue is only a scheduler.
    """

    aggregator = models.CharField(max_length=20, choices=AggregatorType.choices, db_index=True)
    event_type = models.CharField(max_length=100, blank=True)
    #: Aggregator's own event/delivery id when supplied — the strongest dedup key.
    external_event_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_order_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_store_id = models.CharField(max_length=255, blank=True)

    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict, blank=True)
    signature_verified = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20, choices=WebhookStatus.choices, default=WebhookStatus.RECEIVED, db_index=True
    )
    error_message = models.TextField(blank=True)
    attempts = models.IntegerField(default=0)

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Webhook Event'
        verbose_name_plural = 'Webhook Events'
        ordering = ['-received_at']
        constraints = [
            models.UniqueConstraint(
                fields=['aggregator', 'external_event_id'],
                condition=models.Q(external_event_id__gt=''),
                name='uniq_webhook_event_id',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'received_at'], name='idx_webhook_status_time'),
        ]

    def __str__(self):
        return f'{self.aggregator} {self.event_type} {self.external_order_id or "-"}'


class AggregatorOrder(models.Model):
    """An order received from an aggregator, with its delivery lifecycle.

    Separate from ``SalesHeader`` on purpose: Sales records a completed
    commercial transaction, while this records a fast-moving delivery workflow
    that may end in cancellation before any sale exists.
    """

    store_link = models.ForeignKey(
        AggregatorStoreLink, on_delete=models.PROTECT, related_name='orders'
    )
    aggregator = models.CharField(max_length=20, choices=AggregatorType.choices, db_index=True)
    external_order_id = models.CharField(max_length=255, db_index=True)
    short_order_number = models.CharField(max_length=50, blank=True)

    status = models.IntegerField(
        choices=OrderStatus.choices, default=OrderStatus.CREATED, db_index=True
    )
    external_status = models.CharField(max_length=100, blank=True)
    order_type = models.CharField(
        max_length=20, choices=OrderType.choices, default=OrderType.DELIVERY
    )

    # --- Money (net figures, tax un-baked by the adapter) ---
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    merchant_funded_discount = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal('0'),
        help_text='Bagian diskon yang ditanggung merchant — hanya ini yang mengurangi pendapatan.',
    )
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    delivery_fee = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    packaging_fee = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))

    # --- People ---
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=50, blank=True)
    delivery_address = models.TextField(blank=True)
    driver_name = models.CharField(max_length=200, blank=True)
    driver_phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    cancel_reason = models.TextField(blank=True)

    # --- Downstream posting ---
    sales_header = models.OneToOneField(
        'sales.SalesHeader', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aggregator_order',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posting_error = models.TextField(blank=True)
    #: True once the order has been released to the kitchen, so re-delivery of
    #: the triggering webhook cannot release it twice.
    released_to_kitchen = models.BooleanField(default=False)
    has_unmapped_items = models.BooleanField(
        default=False,
        help_text='Aggregator mengirim item yang tidak cocok dengan katalog. Perlu ditinjau.',
    )

    raw_payload = models.JSONField(default=dict, blank=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pesanan Aggregator'
        verbose_name_plural = 'Pesanan Aggregator'
        ordering = ['-created_at']
        constraints = [
            # The database-level backstop for idempotency. The Redis lock and the
            # existence check are faster, but this is what holds when Redis is
            # degraded and two workers race the same retry.
            models.UniqueConstraint(
                fields=['aggregator', 'external_order_id'],
                name='uniq_aggregator_order',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_aggorder_status_time'),
            models.Index(fields=['store_link', 'status'], name='idx_aggorder_store_status'),
        ]

    def __str__(self):
        return f'{self.get_aggregator_display()} #{self.short_order_number or self.external_order_id}'

    @property
    def is_terminal(self) -> bool:
        from .constants import TERMINAL_STATUSES
        return self.status in TERMINAL_STATUSES

    def can_advance_to(self, new_status: int) -> bool:
        """Reject stale and out-of-order webhooks with an integer comparison.

        Cancellation is the one backward move that is always allowed: an order
        can be cancelled from any non-terminal state.
        """
        if self.is_terminal:
            return False
        if new_status == OrderStatus.CANCELLED:
            return True
        return new_status > self.status


class AggregatorOrderItem(models.Model):
    order = models.ForeignKey(AggregatorOrder, on_delete=models.CASCADE, related_name='items')
    #: Null when the aggregator sent something we could not map to the catalog.
    item = models.ForeignKey(
        'purchase.ItemMasterPurchase', on_delete=models.PROTECT,
        null=True, blank=True, related_name='aggregator_order_items',
    )
    external_item_id = models.CharField(max_length=255, blank=True)
    name_snapshot = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    modifier_total = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    line_total = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Item Pesanan Aggregator'
        verbose_name_plural = 'Item Pesanan Aggregator'

    def __str__(self):
        return f'{self.name_snapshot} ×{self.quantity}'


class AggregatorOrderModifier(models.Model):
    order_item = models.ForeignKey(
        AggregatorOrderItem, on_delete=models.CASCADE, related_name='modifiers'
    )
    external_id = models.CharField(max_length=255, blank=True)
    name_snapshot = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('1'))

    def __str__(self):
        return self.name_snapshot


class AggregatorOrderLog(models.Model):
    """Append-only audit trail per order."""

    order = models.ForeignKey(AggregatorOrder, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=50)
    detail = models.TextField(blank=True)
    from_status = models.IntegerField(choices=OrderStatus.choices, null=True, blank=True)
    to_status = models.IntegerField(choices=OrderStatus.choices, null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aggregator_order_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} @ {self.created_at:%Y-%m-%d %H:%M}'


class OnboardingSession(models.Model):
    """Resumable connect-a-channel workflow for one merchant + aggregator."""

    credential = models.OneToOneField(
        AggregatorCredential, on_delete=models.CASCADE, related_name='onboarding'
    )
    state = models.CharField(
        max_length=30, choices=OnboardingState.choices, default=OnboardingState.NOT_STARTED
    )
    last_error = models.TextField(blank=True)
    #: Latest pre-flight results, as a list of CheckResult-shaped dicts.
    preflight_results = models.JSONField(default=list, blank=True)
    #: CSRF-equivalent nonce for the OAuth redirect. Verified on callback.
    oauth_state = models.CharField(max_length=128, blank=True)
    oauth_state_created_at = models.DateTimeField(null=True, blank=True)

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aggregator_onboardings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sesi Onboarding'
        verbose_name_plural = 'Sesi Onboarding'

    def __str__(self):
        return f'{self.credential} — {self.get_state_display()}'

    @property
    def preflight_passed(self) -> bool:
        results = self.preflight_results or []
        return bool(results) and all(r.get('passed') for r in results)


class WebhookSubscription(models.Model):
    """One registered webhook event on the aggregator's side.

    Only aggregators with an explicit subscription API (GoFood) use this. Stored
    so re-running registration reconciles existing subscriptions instead of
    creating duplicates.
    """

    credential = models.ForeignKey(
        AggregatorCredential, on_delete=models.CASCADE, related_name='webhook_subscriptions'
    )
    event_name = models.CharField(max_length=100)
    external_subscription_id = models.CharField(max_length=255, blank=True)
    callback_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(
        max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    detail = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('credential', 'event_name')
        verbose_name = 'Langganan Webhook'
        verbose_name_plural = 'Langganan Webhook'

    def __str__(self):
        return f'{self.event_name} — {self.get_status_display()}'
