"""Background work for the aggregator integration.

Webhook handlers do the minimum inline — persist and acknowledge — then hand
off here. Aggregators time out fast and treat a slow response as a failure to
be retried, so normalisation, accounting and menu pushes must not run inside
the request.

Retries are bounded and the durable record is the ``WebhookEvent`` row, not the
queue message: a task that exhausts its retries leaves a FAILED event that
``retry_failed_webhook_events`` picks up later.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from .constants import SyncStatus, WebhookStatus

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30, acks_late=True)
def process_webhook_event(self, event_id: int):
    """Normalise one stored webhook into order state."""
    from .models import WebhookEvent
    from .services.ingest import IngestError, process_event

    event = WebhookEvent.objects.filter(pk=event_id).first()
    if not event:
        logger.warning('WebhookEvent %s disappeared before processing', event_id)
        return
    if event.status == WebhookStatus.PROCESSED:
        return

    event.attempts += 1
    event.save(update_fields=['attempts'])

    try:
        process_event(event)
    except IngestError as exc:
        # A business-level problem (unlinked outlet, status before create).
        # Retrying immediately will not help much, but the outlet may get
        # linked minutes later, so a bounded retry is still worthwhile.
        event.status = WebhookStatus.FAILED
        event.error_message = str(exc)
        event.save(update_fields=['status', 'error_message'])
        raise self.retry(exc=exc, countdown=60 * min(self.request.retries + 1, 10))
    except Exception as exc:
        event.status = WebhookStatus.FAILED
        event.error_message = f'{type(exc).__name__}: {exc}'
        event.save(update_fields=['status', 'error_message'])
        logger.exception('Failed to process webhook event %s', event_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, acks_late=True)
def post_order_to_sales(self, order_id: int):
    """Turn a released order into SalesHeader/SalesItem + journals."""
    from .models import AggregatorOrder, AggregatorOrderLog
    from .services.sales_posting import PostingError, post_order

    order = AggregatorOrder.objects.filter(pk=order_id).first()
    if not order or order.sales_header_id:
        return

    try:
        post_order(order)
    except PostingError as exc:
        # A configuration problem a human must fix. Record it visibly and stop
        # retrying — retrying a missing account never succeeds on its own.
        order.posting_error = str(exc)
        order.save(update_fields=['posting_error', 'updated_at'])
        AggregatorOrderLog.objects.create(
            order=order, action='POSTING_BLOCKED', detail=str(exc)
        )
        logger.warning('Order %s cannot be posted: %s', order_id, exc)
    except Exception as exc:
        order.posting_error = f'{type(exc).__name__}: {exc}'
        order.save(update_fields=['posting_error', 'updated_at'])
        logger.exception('Unexpected error posting order %s', order_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_menu_task(self, store_link_id: int):
    from .models import AggregatorStoreLink
    from .services.menu import MenuError, publish_menu

    link = AggregatorStoreLink.objects.filter(pk=store_link_id).first()
    if not link:
        return
    try:
        publish_menu(link)
    except MenuError:
        # Menu content problems are for a human; the failure detail is already
        # stored on the link for the wizard to display.
        return
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def publish_all_menus(credential_id: int):
    from .models import AggregatorStoreLink
    links = AggregatorStoreLink.objects.filter(
        credential_id=credential_id
    ).exclude(external_store_id='')
    for link in links:
        publish_menu_task.delay(link.pk)


@shared_task
def push_availability_task(store_link_id: int, catalog_item_id: int, available: bool):
    from pos_catalog.models import CatalogItem
    from .models import AggregatorStoreLink
    from .services.menu import push_availability

    link = AggregatorStoreLink.objects.filter(pk=store_link_id).first()
    item = CatalogItem.objects.filter(pk=catalog_item_id).first()
    if not link or not item:
        return
    try:
        push_availability(link, item, available)
    except Exception:
        logger.warning('Availability push failed for link %s', store_link_id, exc_info=True)


@shared_task
def push_order_status_task(order_id: int, status: int):
    """Tell the aggregator the kitchen state, where the channel supports it."""
    from .adapters import NotSupported, get_adapter
    from .models import AggregatorOrder, AggregatorOrderLog

    order = AggregatorOrder.objects.filter(pk=order_id).select_related(
        'store_link__credential'
    ).first()
    if not order:
        return
    try:
        get_adapter(order.store_link.credential).push_order_status(order, status)
        AggregatorOrderLog.objects.create(
            order=order, action='STATUS_PUSHED', detail=str(status)
        )
    except NotSupported:
        return
    except Exception as exc:
        AggregatorOrderLog.objects.create(
            order=order, action='STATUS_PUSH_FAILED', detail=str(exc)[:500]
        )


@shared_task
def refresh_expiring_tokens():
    """Refresh OAuth tokens before they lapse.

    Without this an integration dies quietly: orders simply stop arriving, and
    the cause is not obvious for hours.
    """
    from datetime import timedelta
    from .adapters import get_adapter
    from .models import AggregatorCredential

    horizon = timezone.now() + timedelta(hours=1)
    credentials = AggregatorCredential.objects.filter(
        is_active=True, access_token_expires_at__lte=horizon,
    )
    for credential in credentials:
        try:
            get_adapter(credential).refresh_access_token()
        except Exception:
            logger.warning(
                'Token refresh failed for credential %s (%s)',
                credential.pk, credential.aggregator, exc_info=True,
            )


@shared_task
def retry_failed_webhook_events():
    """Second chance for events that failed for a transient reason."""
    from datetime import timedelta
    from .models import WebhookEvent

    cutoff = timezone.now() - timedelta(days=1)
    stuck = WebhookEvent.objects.filter(
        status=WebhookStatus.FAILED, received_at__gte=cutoff, attempts__lt=10,
    ).order_by('received_at')[:200]
    for event in stuck:
        process_webhook_event.delay(event.pk)


@shared_task
def reconcile_stale_menu_syncs():
    """Surface menu pushes that never reported back.

    An aggregator that accepts a menu and then goes quiet leaves the branch
    looking synced when it is not; this flips those to FAILED so the wizard
    shows the truth.
    """
    from datetime import timedelta
    from .models import AggregatorStoreLink

    cutoff = timezone.now() - timedelta(minutes=45)
    stale = AggregatorStoreLink.objects.filter(
        menu_sync_status=SyncStatus.IN_PROGRESS, updated_at__lte=cutoff,
    )
    for link in stale:
        link.menu_sync_status = SyncStatus.FAILED
        link.menu_sync_detail = (
            'Aggregator tidak mengonfirmasi sinkronisasi menu dalam 45 menit. '
            'Coba "Kirim Menu" sekali lagi.'
        )
        link.save(update_fields=['menu_sync_status', 'menu_sync_detail', 'updated_at'])
