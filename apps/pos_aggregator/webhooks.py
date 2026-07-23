"""Public webhook endpoints.

These are the only unauthenticated, internet-facing views in the project, so
they are deliberately small and defensive:

* CSRF is exempt because the caller is a server, not a browser session — the
  signature is the authentication.
* The signature is checked against the **raw body** before anything is trusted.
  A request that fails verification is rejected without being processed; it is
  still recorded, because repeated failures are how a misconfiguration (or an
  attack) becomes visible.
* The response is returned as soon as the payload is stored. Aggregators time
  out quickly and treat anything non-2xx as "retry", so slow work happens in a
  task, never inline.
"""
from __future__ import annotations

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .adapters import SignatureError, get_adapter
from .constants import AggregatorType
from .models import AggregatorCredential
from .services.ingest import record_event
from .tasks import process_webhook_event

logger = logging.getLogger(__name__)


def _ack(adapter, credential):
    """Return exactly what this aggregator expects for a handled delivery."""
    if hasattr(adapter, 'ack_body'):
        return JsonResponse(adapter.ack_body(), status=adapter.ack_status_code)
    if adapter.ack_status_code == 204:
        return HttpResponse(status=204)
    return JsonResponse({'ok': True}, status=adapter.ack_status_code)


@csrf_exempt
@require_POST
def receive(request, aggregator: str, credential_id: int):
    """Single entry point for every aggregator callback."""
    aggregator = aggregator.upper()
    if aggregator not in AggregatorType.values:
        return JsonResponse({'ok': False, 'error': 'unknown aggregator'}, status=404)

    credential = (
        AggregatorCredential.objects
        .filter(pk=credential_id, aggregator=aggregator)
        .select_related('merchant_config')
        .first()
    )
    if not credential:
        return JsonResponse({'ok': False, 'error': 'unknown endpoint'}, status=404)

    adapter = get_adapter(credential)

    try:
        adapter.verify_webhook(request)
    except SignatureError as exc:
        # Logged at warning: a burst here means a rotated secret or a probe.
        logger.warning(
            'Rejected %s webhook for credential %s: %s', aggregator, credential_id, exc
        )
        return JsonResponse({'ok': False, 'error': 'invalid signature'}, status=401)

    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({'ok': False, 'error': 'expected a json object'}, status=400)

    meta = adapter.extract_event_meta(payload, request)
    event = record_event(
        aggregator=aggregator, payload=payload, request=request,
        meta=meta, signature_verified=True,
    )

    process_webhook_event.delay(event.pk)
    return _ack(adapter, credential)


@csrf_exempt
@require_POST
def grab_activation_callback(request, credential_id: int):
    """GrabFood pushes the store id here after the merchant approves.

    This is what keeps Grab onboarding free of typed identifiers: the operator
    presses Activate, approves on Grab, and the id arrives here.
    """
    from django.utils import timezone
    from .constants import LinkStatus
    from .models import AggregatorStoreLink

    credential = AggregatorCredential.objects.filter(
        pk=credential_id, aggregator=AggregatorType.GRABFOOD
    ).first()
    if not credential:
        return JsonResponse({'ok': False, 'error': 'unknown endpoint'}, status=404)

    adapter = get_adapter(credential)
    try:
        adapter.verify_webhook(request)
    except SignatureError as exc:
        logger.warning('Rejected Grab activation callback: %s', exc)
        return JsonResponse({'ok': False, 'error': 'invalid signature'}, status=401)

    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

    partner_merchant_id = payload.get('partnerMerchantID') or payload.get('partnerMerchantId')
    merchant_id = payload.get('merchantID') or payload.get('merchantId')
    status = (payload.get('status') or '').upper()

    if not partner_merchant_id or not merchant_id:
        return JsonResponse({'ok': False, 'error': 'missing ids'}, status=400)

    link = AggregatorStoreLink.objects.filter(
        credential=credential, store_config_id=partner_merchant_id
    ).first()
    if not link:
        return JsonResponse({'ok': False, 'error': 'unknown store'}, status=404)

    if status in ('SUCCESS', 'ACTIVATED', 'COMPLETED'):
        link.external_store_id = str(merchant_id)
        link.status = LinkStatus.LINKED
        link.linked_at = timezone.now()
        link.status_detail = ''
    else:
        link.status = LinkStatus.FAILED
        link.status_detail = payload.get('message', '') or status
    link.save(update_fields=[
        'external_store_id', 'status', 'linked_at', 'status_detail', 'updated_at'
    ])

    return HttpResponse(status=204)


@csrf_exempt
def grab_menu_pull(request, credential_id: int, store_link_id: int):
    """GrabFood fetches the catalog from us rather than receiving a push."""
    from .models import AggregatorStoreLink
    from .services.menu import build_menu

    credential = AggregatorCredential.objects.filter(
        pk=credential_id, aggregator=AggregatorType.GRABFOOD
    ).first()
    if not credential:
        return JsonResponse({'ok': False, 'error': 'unknown endpoint'}, status=404)

    adapter = get_adapter(credential)
    try:
        adapter.verify_webhook(request)
    except SignatureError as exc:
        logger.warning('Rejected Grab menu pull: %s', exc)
        return JsonResponse({'ok': False, 'error': 'invalid signature'}, status=401)

    link = AggregatorStoreLink.objects.filter(
        pk=store_link_id, credential=credential
    ).first()
    if not link:
        return JsonResponse({'ok': False, 'error': 'unknown store'}, status=404)

    menu = build_menu(link)
    return JsonResponse({
        'merchantID': link.external_store_id,
        'currency': {'code': menu.currency},
        'categories': [
            {
                'categoryID': category,
                'name': category,
                'items': [
                    {
                        'itemID': item.external_id,
                        'name': item.name,
                        'description': item.description,
                        'price': int(item.price * 100),
                        'availableStatus': 'AVAILABLE' if item.is_available else 'UNAVAILABLE',
                        'photos': [item.image_url] if item.image_url else [],
                        'sequence': item.display_order,
                        'modifierGroups': [
                            {
                                'modifierGroupID': group.external_id,
                                'name': group.name,
                                'selectionRangeMin': group.min_selections,
                                'selectionRangeMax': group.max_selections,
                                'modifiers': [
                                    {
                                        'modifierID': option.external_id,
                                        'name': option.name,
                                        'price': int(option.price * 100),
                                        'availableStatus': (
                                            'AVAILABLE' if option.is_available else 'UNAVAILABLE'
                                        ),
                                    }
                                    for option in group.options
                                ],
                            }
                            for group in item.modifier_groups
                        ],
                    }
                    for item in items
                ],
            }
            for category, items in menu.categories().items()
        ],
    })
