"""Inbound pipeline: aggregator webhook → AggregatorOrder.

Ordering matters and is not arbitrary:

1. **Persist first.** The raw payload becomes a ``WebhookEvent`` row before any
   parsing. Everything after this point can crash and the order is still
   recoverable by replay.
2. **Lock.** A short-lived cache lock keyed by the external order id serialises
   concurrent deliveries. Aggregators retry aggressively and often fire
   create+accept within milliseconds of each other.
3. **Dedup.** An existence check on ``(aggregator, external_order_id)`` catches
   the common retry; a database unique constraint catches the race the lock
   misses when Redis is degraded.
4. **Normalise and store.**
5. **Advance the lifecycle** only forward, so a late-arriving earlier event
   cannot rewind an order.

Sales posting is deliberately *not* done here — see ``sales_posting``. An order
that is cancelled before the kitchen is released must never reach the ledger.
"""
from __future__ import annotations

import contextlib
import logging
import uuid

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..constants import OrderStatus, POSTrigger, WebhookStatus
from ..dto import CanonicalOrder, CanonicalStatusUpdate
from ..models import (
    AggregatorCredential, AggregatorOrder, AggregatorOrderItem, AggregatorOrderLog,
    AggregatorOrderModifier, AggregatorStoreLink, WebhookEvent,
)

logger = logging.getLogger(__name__)

LOCK_TTL = 300


class IngestError(Exception):
    pass


class StoreNotLinked(IngestError):
    """The aggregator sent an order for an outlet we do not know about."""


@contextlib.contextmanager
def order_lock(aggregator: str, external_order_id: str):
    """Serialise processing of one order across workers.

    Falls through (without blocking) when the cache backend is unavailable:
    losing the lock degrades us to the database unique constraint, which is
    still correct, just noisier.
    """
    key = f'agg-order-lock:{aggregator}:{external_order_id}'
    token = uuid.uuid4().hex
    acquired = False
    try:
        acquired = cache.add(key, token, LOCK_TTL)
    except Exception:  # pragma: no cover - cache backend outage
        logger.warning('Order lock unavailable; relying on DB constraint', exc_info=True)
    try:
        yield acquired
    finally:
        if acquired:
            with contextlib.suppress(Exception):
                if cache.get(key) == token:
                    cache.delete(key)


def record_event(*, aggregator, payload, request, meta, signature_verified) -> WebhookEvent:
    """Persist the delivery. Returns an existing row for a repeated event id."""
    event_id = meta.get('external_event_id') or ''
    if event_id:
        existing = WebhookEvent.objects.filter(
            aggregator=aggregator, external_event_id=event_id
        ).first()
        if existing:
            return existing
    interesting_headers = {
        k: v for k, v in request.headers.items()
        if k.lower().startswith(('x-', 'content-type', 'date'))
        # Never persist the credential itself.
        and k.lower() != 'authorization'
    }
    try:
        return WebhookEvent.objects.create(
            aggregator=aggregator,
            event_type=meta.get('event_type', '')[:100],
            external_event_id=event_id[:255],
            external_order_id=str(meta.get('external_order_id', ''))[:255],
            external_store_id=str(meta.get('external_store_id', ''))[:255],
            payload=payload,
            headers=interesting_headers,
            signature_verified=signature_verified,
        )
    except IntegrityError:
        # Concurrent delivery of the same event id won the race.
        return WebhookEvent.objects.get(aggregator=aggregator, external_event_id=event_id)


def resolve_store_link(aggregator: str, external_store_id: str) -> AggregatorStoreLink:
    link = (
        AggregatorStoreLink.objects
        .select_related('credential__merchant_config', 'store_config__entitas_bisnis_lv3')
        .filter(aggregator=aggregator, external_store_id=external_store_id)
        .first()
    )
    if not link:
        raise StoreNotLinked(
            f'{aggregator}: outlet "{external_store_id}" belum terhubung ke cabang manapun.'
        )
    return link


def process_event(event: WebhookEvent) -> AggregatorOrder | None:
    """Turn a stored webhook into order state. Idempotent by construction."""
    from ..adapters import get_adapter

    credential = _credential_for(event)
    adapter = get_adapter(credential)

    order_dto = adapter.parse_order(event.payload)
    status_dto = None if order_dto else adapter.parse_status(event.payload)

    if order_dto is None and status_dto is None:
        event.status = WebhookStatus.PROCESSED
        event.processed_at = timezone.now()
        event.error_message = 'Event tidak mengandung order maupun perubahan status.'
        event.save(update_fields=['status', 'processed_at', 'error_message'])
        return None

    external_id = (order_dto or status_dto).external_order_id
    with order_lock(event.aggregator, external_id):
        if order_dto is not None:
            order = _upsert_order(order_dto, event)
        else:
            order = _apply_status(status_dto, event)

    # Do not overwrite a status the handlers deliberately set: DUPLICATE marks a
    # retry, and FAILED is what keeps an orphaned callback eligible for replay.
    event.refresh_from_db(fields=['status'])
    if event.status == WebhookStatus.RECEIVED:
        event.status = WebhookStatus.PROCESSED
        event.processed_at = timezone.now()
        event.save(update_fields=['status', 'processed_at'])
    return order


def _credential_for(event: WebhookEvent) -> AggregatorCredential:
    if event.external_store_id:
        link = (
            AggregatorStoreLink.objects
            .select_related('credential')
            .filter(aggregator=event.aggregator, external_store_id=event.external_store_id)
            .first()
        )
        if link:
            return link.credential
    credential = AggregatorCredential.objects.filter(
        aggregator=event.aggregator, is_active=True
    ).first()
    if not credential:
        raise IngestError(f'Tidak ada kredensial aktif untuk {event.aggregator}.')
    return credential


@transaction.atomic
def _upsert_order(dto: CanonicalOrder, event: WebhookEvent) -> AggregatorOrder:
    link = resolve_store_link(dto.aggregator, dto.external_store_id)

    existing = AggregatorOrder.objects.filter(
        aggregator=dto.aggregator, external_order_id=dto.external_order_id
    ).first()
    if existing:
        # A retried create. Only the lifecycle may move on.
        if existing.can_advance_to(dto.status):
            _transition(existing, dto.status, dto.external_status, 'WEBHOOK_REPLAY')
        event.status = WebhookStatus.DUPLICATE
        event.save(update_fields=['status'])
        return existing

    _resolve_catalog_items(dto, link)

    order = AggregatorOrder.objects.create(
        store_link=link,
        aggregator=dto.aggregator,
        external_order_id=dto.external_order_id,
        short_order_number=dto.short_order_number,
        status=dto.status,
        external_status=dto.external_status,
        order_type=dto.order_type,
        subtotal=dto.subtotal,
        discount_amount=dto.discount_amount,
        merchant_funded_discount=dto.merchant_funded_discount,
        tax_amount=dto.tax_amount,
        delivery_fee=dto.delivery_fee,
        packaging_fee=dto.packaging_fee,
        total_amount=dto.total_amount,
        customer_name=dto.customer_name,
        customer_phone=dto.customer_phone,
        delivery_address=dto.delivery_address,
        driver_name=dto.driver_name,
        driver_phone=dto.driver_phone,
        notes=dto.notes,
        placed_at=dto.placed_at,
        raw_payload=dto.raw_payload,
        has_unmapped_items=dto.has_unmapped_items,
    )

    for line in dto.items:
        item = AggregatorOrderItem.objects.create(
            order=order,
            item_id=line.item_id,
            external_item_id=line.external_id,
            name_snapshot=line.name,
            quantity=line.quantity,
            unit_price=line.unit_price,
            modifier_total=line.modifier_total,
            line_total=line.line_total,
            notes=line.notes,
        )
        for mod in line.modifiers:
            AggregatorOrderModifier.objects.create(
                order_item=item,
                external_id=mod.external_id,
                name_snapshot=mod.name,
                price=mod.price,
                quantity=mod.quantity,
            )

    AggregatorOrderLog.objects.create(
        order=order, action='RECEIVED',
        detail=f'Diterima dari {order.get_aggregator_display()}.',
        to_status=order.status,
    )
    if order.has_unmapped_items:
        AggregatorOrderLog.objects.create(
            order=order, action='UNMAPPED_ITEMS',
            detail='Sebagian item tidak cocok dengan katalog dan perlu ditinjau manual.',
        )

    _maybe_release(order)
    return order


def _apply_status(dto: CanonicalStatusUpdate, event: WebhookEvent) -> AggregatorOrder | None:
    order = AggregatorOrder.objects.filter(
        aggregator=dto.aggregator, external_order_id=dto.external_order_id
    ).first()
    if not order:
        # The status arrived before the create. Leave the event for replay
        # rather than inventing an order from a payload without line items.
        event.status = WebhookStatus.FAILED
        event.error_message = 'Status diterima sebelum pesanan dibuat — menunggu replay.'
        event.save(update_fields=['status', 'error_message'])
        return None

    if dto.driver_name or dto.driver_phone:
        order.driver_name = dto.driver_name or order.driver_name
        order.driver_phone = dto.driver_phone or order.driver_phone
        order.save(update_fields=['driver_name', 'driver_phone', 'updated_at'])

    if not order.can_advance_to(dto.status):
        AggregatorOrderLog.objects.create(
            order=order, action='STATUS_IGNORED',
            detail=(
                f'Status {dto.external_status} diabaikan: pesanan sudah pada '
                f'{order.get_status_display()}.'
            ),
            from_status=order.status, to_status=dto.status,
        )
        return order

    _transition(order, dto.status, dto.external_status, 'STATUS_UPDATE',
                cancel_reason=dto.cancel_reason)
    _maybe_release(order)
    return order


def _transition(order, new_status, external_status, action, cancel_reason=''):
    previous = order.status
    order.status = new_status
    order.external_status = external_status or order.external_status
    fields = ['status', 'external_status', 'updated_at']
    if cancel_reason:
        order.cancel_reason = cancel_reason
        fields.append('cancel_reason')
    order.save(update_fields=fields)
    AggregatorOrderLog.objects.create(
        order=order, action=action, from_status=previous, to_status=new_status,
        detail=external_status,
    )


def _maybe_release(order: AggregatorOrder) -> None:
    """Release to the kitchen once the merchant's chosen trigger is reached.

    Some merchants start cooking immediately; others wait for a driver so a
    cancellation does not waste food. Releasing is idempotent — the flag makes
    a redelivered webhook harmless.
    """
    if order.released_to_kitchen or order.status == OrderStatus.CANCELLED:
        return

    trigger = order.store_link.credential.pos_trigger
    reached = {
        POSTrigger.ON_CREATED: OrderStatus.CREATED,
        POSTrigger.ON_ACCEPTED: OrderStatus.ACCEPTED,
        POSTrigger.ON_DRIVER_ARRIVED: OrderStatus.DRIVER_ARRIVED,
    }[trigger]

    if order.status < reached:
        return

    order.released_to_kitchen = True
    order.save(update_fields=['released_to_kitchen', 'updated_at'])
    AggregatorOrderLog.objects.create(
        order=order, action='RELEASED_TO_KITCHEN',
        detail=f'Trigger: {order.store_link.credential.get_pos_trigger_display()}',
    )

    from .realtime import broadcast_new_order
    transaction.on_commit(lambda: broadcast_new_order(order))

    from ..tasks import post_order_to_sales
    transaction.on_commit(lambda: post_order_to_sales.delay(order.pk))


def _resolve_catalog_items(dto: CanonicalOrder, link: AggregatorStoreLink) -> None:
    """Map aggregator item ids back to internal stock items.

    We publish our own ids into the menu, so the round trip is a lookup rather
    than a guess. Unmapped lines are flagged, never silently dropped — dropping
    them would understate the order and corrupt stock.
    """
    from ..models import AggregatorItemSetting

    external_ids = [i.external_id for i in dto.items if i.external_id]
    if not external_ids:
        return

    settings_by_external = {
        s.external_item_id: s
        for s in AggregatorItemSetting.objects
        .filter(credential=link.credential, external_item_id__in=external_ids)
        .select_related('catalog_item')
    }

    for line in dto.items:
        setting = settings_by_external.get(line.external_id)
        if setting:
            line.item_id = setting.catalog_item.item_id
            continue
        # Fall back to our own encoding: menus are published with the catalog
        # item primary key as the external id.
        if line.external_id.isdigit():
            from pos_catalog.models import CatalogItem
            catalog_item = CatalogItem.objects.filter(pk=int(line.external_id)).first()
            if catalog_item:
                line.item_id = catalog_item.item_id
