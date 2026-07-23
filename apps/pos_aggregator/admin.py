from django.contrib import admin

from .models import (
    AggregatorCredential, AggregatorItemSetting, AggregatorOrder, AggregatorOrderItem,
    AggregatorOrderLog, AggregatorStoreLink, OnboardingSession, WebhookEvent,
    WebhookSubscription,
)


@admin.register(AggregatorCredential)
class AggregatorCredentialAdmin(admin.ModelAdmin):
    list_display = ('aggregator', 'merchant_config', 'environment', 'is_active', 'updated_at')
    list_filter = ('aggregator', 'environment', 'is_active')
    search_fields = ('client_id', 'enterprise_id')
    # Secrets are encrypted blobs; showing them in admin would defeat the vault.
    exclude = (
        'client_secret_encrypted', 'access_token_encrypted',
        'refresh_token_encrypted', 'webhook_secret_encrypted',
    )
    readonly_fields = ('masked_client_secret', 'created_at', 'updated_at')


@admin.register(AggregatorStoreLink)
class AggregatorStoreLinkAdmin(admin.ModelAdmin):
    list_display = (
        'aggregator', 'store_config', 'external_store_id', 'status',
        'menu_sync_status', 'is_live',
    )
    list_filter = ('aggregator', 'status', 'menu_sync_status', 'is_live')
    search_fields = ('external_store_id', 'external_store_name')


class AggregatorOrderItemInline(admin.TabularInline):
    model = AggregatorOrderItem
    extra = 0


class AggregatorOrderLogInline(admin.TabularInline):
    model = AggregatorOrderLog
    extra = 0
    readonly_fields = ('action', 'detail', 'from_status', 'to_status', 'actor', 'created_at')


@admin.register(AggregatorOrder)
class AggregatorOrderAdmin(admin.ModelAdmin):
    list_display = (
        'external_order_id', 'aggregator', 'store_link', 'status',
        'total_amount', 'sales_header', 'created_at',
    )
    list_filter = ('aggregator', 'status', 'has_unmapped_items')
    search_fields = ('external_order_id', 'short_order_number', 'customer_name')
    readonly_fields = ('raw_payload', 'created_at', 'updated_at')
    inlines = (AggregatorOrderItemInline, AggregatorOrderLogInline)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'aggregator', 'event_type', 'external_order_id', 'status',
        'signature_verified', 'attempts', 'received_at',
    )
    list_filter = ('aggregator', 'status', 'signature_verified')
    search_fields = ('external_order_id', 'external_event_id')
    readonly_fields = ('payload', 'headers', 'received_at', 'processed_at')

    actions = ('replay_events',)

    @admin.action(description='Proses ulang event terpilih')
    def replay_events(self, request, queryset):
        from .tasks import process_webhook_event
        for event in queryset:
            process_webhook_event.delay(event.pk)
        self.message_user(request, f'{queryset.count()} event dijadwalkan untuk diproses ulang.')


@admin.register(OnboardingSession)
class OnboardingSessionAdmin(admin.ModelAdmin):
    list_display = ('credential', 'state', 'updated_at')
    list_filter = ('state',)
    readonly_fields = ('preflight_results', 'created_at', 'updated_at')


admin.site.register(AggregatorItemSetting)
admin.site.register(WebhookSubscription)
