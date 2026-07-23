"""Push new aggregator orders to whoever is watching a branch.

Two transports, on purpose:

* **Web push** is the durable guarantee. It survives a closed tab, a locked
  phone and a flaky connection, because the browser vendor queues it.
* **WebSocket** is the enhancement for a screen that is already open, giving an
  instant update without a refresh.

Order delivery must never *depend* on a live socket. Everything sent here is
already committed to the database first, so a missed notification costs a
refresh, never an order.
"""
from __future__ import annotations

import json
import logging

from asgiref.sync import async_to_sync
from django.conf import settings

logger = logging.getLogger(__name__)


def store_group(store_config_id: int) -> str:
    return f'pos_store_{store_config_id}'


def _serialise(order) -> dict:
    return {
        'id': order.pk,
        'aggregator': order.aggregator,
        'aggregator_label': order.get_aggregator_display(),
        'order_number': order.short_order_number or order.external_order_id,
        'status': order.status,
        'status_label': order.get_status_display(),
        'order_type': order.get_order_type_display(),
        'customer_name': order.customer_name,
        'total_amount': str(order.total_amount),
        'item_count': order.items.count(),
        'placed_at': order.placed_at.isoformat() if order.placed_at else None,
        'has_unmapped_items': order.has_unmapped_items,
    }


def broadcast_new_order(order) -> None:
    payload = _serialise(order)
    _send_socket(order.store_link.store_config_id, 'order.new', payload)
    _send_web_push(order.store_link.store_config_id, payload)


def broadcast_status_change(order) -> None:
    _send_socket(order.store_link.store_config_id, 'order.status', _serialise(order))


def _send_socket(store_config_id: int, event: str, payload: dict) -> None:
    try:
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            store_group(store_config_id),
            {'type': 'aggregator.event', 'event': event, 'payload': payload},
        )
    except Exception:
        # A dead channel layer must not roll back an order that is already
        # committed. The order board recovers on its next poll or reload.
        logger.warning('Realtime socket broadcast failed', exc_info=True)


def _send_web_push(store_config_id: int, payload: dict) -> None:
    private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    if not private_key:
        return
    try:
        from pywebpush import webpush, WebPushException
        from pos_config.models import WebPushSubscription

        subscriptions = WebPushSubscription.objects.filter(
            store_id=store_config_id, is_active=True,
        )
        body = json.dumps({
            'title': f'Pesanan {payload["aggregator_label"]} baru',
            'body': f'#{payload["order_number"]} — Rp {payload["total_amount"]}',
            'data': payload,
        })
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {'p256dh': sub.p256dh_key, 'auth': sub.auth_key},
                    },
                    data=body,
                    vapid_private_key=private_key,
                    vapid_claims={
                        'sub': f'mailto:{getattr(settings, "VAPID_CLAIM_EMAIL", "push@naveda.id")}'
                    },
                )
            except WebPushException as exc:
                # 404/410 means the browser dropped the subscription; stop
                # retrying it rather than failing every future broadcast.
                if exc.response is not None and exc.response.status_code in (404, 410):
                    sub.is_active = False
                    sub.save(update_fields=['is_active'])
                else:
                    logger.warning('Web push failed for subscription %s', sub.pk, exc_info=True)
    except Exception:
        logger.warning('Web push broadcast failed', exc_info=True)
