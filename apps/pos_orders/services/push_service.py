import json
import logging
from django.conf import settings
from pos_config.models import WebPushSubscription

logger = logging.getLogger(__name__)


def send_push_to_store(store_id: int, role: str, title: str, body: str, data: dict) -> None:
    """Send web push notification to all active subscribers with the given role in a store."""
    if not getattr(settings, 'VAPID_PRIVATE_KEY', None) or not getattr(settings, 'VAPID_CLAIM_EMAIL', None):
        return  # Push not configured

    from pywebpush import webpush, WebPushException

    subscriptions = WebPushSubscription.objects.filter(
        store_id=store_id, role=role, is_active=True
    )

    payload = json.dumps({'title': title, 'body': body, **data})

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh_key, 'auth': sub.auth_key},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{settings.VAPID_CLAIM_EMAIL}'},
            )
        except WebPushException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 410:
                sub.is_active = False
                sub.save(update_fields=['is_active'])
            else:
                logger.warning('Push failed for subscription %s: %s', sub.pk, e)
