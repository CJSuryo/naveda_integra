"""GoFood (GoBiz) adapter — Facilitator model.

The handoff's decisive finding: GoBiz offers two integration models and only the
Facilitator one supports self-service onboarding.

* Direct Integration uses ``client_credentials``; nobody authorises anything and
  outlet ids are typed by hand.
* **Facilitator** uses ``authorization_code``: the merchant enters their phone,
  receives an OTP, approves a consent screen, and we receive a code. Outlets are
  then *discovered* via ``token-info``, so the operator types nothing at all.

This adapter implements the Facilitator model. ``client_credentials`` remains
available behind ``AggregatorCredential.enterprise_id`` so an existing direct
integration keeps working during migration — do not remove it without checking
whether any merchant is still on that path.

Prerequisite outside the code: the company must be registered as a GoBiz Partner
(facilitator). That is a one-time application with an external lead time.

[VERIFY] Endpoint paths and the exact webhook event names against the GoBiz
developer portal once facilitator credentials are issued.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlencode

import requests

from ..constants import AggregatorType, OrderStatus, OrderType, SyncStatus
from ..dto import (
    CanonicalMenu, CanonicalMenuItem, CanonicalMenuModifier, CanonicalMenuModifierGroup,
    CanonicalModifier, CanonicalOrder, CanonicalOrderItem, CanonicalStatusUpdate,
    ConnectAction, OutletInfo, money,
)
from .base import AuthError, BaseAdapter, SignatureError, UpstreamError, constant_time_compare

EVENT_STATUS_MAP = {
    'order.created': OrderStatus.CREATED,
    'order.merchant_accepted': OrderStatus.ACCEPTED,
    'order.food_prepared': OrderStatus.READY,
    'order.otw_pickup': OrderStatus.READY,
    'order.driver_arrived': OrderStatus.DRIVER_ARRIVED,
    'order.otw_delivery': OrderStatus.PICKED_UP,
    'order.completed': OrderStatus.COMPLETED,
    'order.cancelled': OrderStatus.CANCELLED,
}

ORDER_TYPE_MAP = {
    'DELIVERY': OrderType.DELIVERY,
    'PICKUP': OrderType.TAKEAWAY,
    'TAKEAWAY': OrderType.TAKEAWAY,
    'DINE_IN': OrderType.DINE_IN,
}


class GoFoodAdapter(BaseAdapter):
    aggregator = AggregatorType.GOFOOD
    ack_status_code = 200

    # ── Auth ────────────────────────────────────────────────────────────────

    def refresh_access_token(self) -> str:
        """Refresh via ``refresh_token``; fall back to legacy client_credentials.

        A merchant connected through the Facilitator flow always has a refresh
        token. Only a legacy direct integration (identified by ``enterprise_id``
        with no refresh token) uses the client-credentials grant.
        """
        cred = self.credential
        if cred.refresh_token_encrypted:
            return self._grant({
                'grant_type': 'refresh_token',
                'refresh_token': cred.refresh_token,
                'client_id': cred.client_id,
                'client_secret': cred.client_secret,
            })
        if cred.enterprise_id:
            return self._grant({
                'grant_type': 'client_credentials',
                'client_id': cred.client_id,
                'client_secret': cred.client_secret,
                'scope': ' '.join(self.template.scopes),
            })
        raise AuthError(
            'GoFood belum terhubung. Jalankan "Hubungkan Akun" untuk memberi '
            'persetujuan lewat GoBiz.'
        )

    def _grant(self, payload: dict) -> str:
        try:
            response = requests.post(self.template.auth_url, json=payload, timeout=20)
        except requests.RequestException as exc:
            raise AuthError(f'GoFood token request gagal: {exc}') from exc
        if response.status_code >= 400:
            raise AuthError(
                f'GoFood menolak kredensial ({response.status_code}): {response.text[:500]}'
            )
        data = response.json()
        token = data.get('access_token', '')
        if not token:
            raise AuthError('GoFood tidak mengembalikan access_token.')
        self.store_tokens(
            access_token=token,
            expires_in=data.get('expires_in', 3600),
            refresh_token=data.get('refresh_token', ''),
            refresh_expires_in=data.get('refresh_token_expires_in'),
        )
        return token

    # ── Inbound ─────────────────────────────────────────────────────────────

    def verify_webhook(self, request) -> None:
        """HMAC-SHA256 of the raw body against ``X-Go-Signature``.

        GoFood signs the bytes it sent. Parsing and re-serialising the JSON
        first reorders keys and changes whitespace, which silently breaks the
        comparison — always hash ``request.body``.
        """
        secret = self.credential.webhook_secret
        if not secret:
            raise SignatureError('GoFood notification secret belum dikonfigurasi.')
        provided = request.headers.get('X-Go-Signature', '')
        if not provided:
            raise SignatureError('Header X-Go-Signature tidak ada.')
        expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        # Some GoBiz deployments prefix the algorithm.
        provided_value = provided.split('=', 1)[-1].strip()
        if not constant_time_compare(expected, provided_value):
            raise SignatureError('Tanda tangan GoFood tidak cocok.')

    def extract_event_meta(self, payload: dict, request) -> dict:
        order = payload.get('order', {}) or payload.get('data', {}) or payload
        return {
            'event_type': payload.get('event') or payload.get('type') or '',
            'external_event_id': payload.get('id', '') or payload.get('event_id', ''),
            'external_order_id': str(order.get('id') or order.get('order_id') or ''),
            'external_store_id': str(order.get('outlet_id') or order.get('store_id') or ''),
        }

    def parse_order(self, payload: dict) -> CanonicalOrder | None:
        event = payload.get('event') or payload.get('type') or ''
        order = payload.get('order') or payload.get('data') or {}
        if not order.get('id') and not order.get('order_id'):
            return None
        if not order.get('items'):
            return None

        items = [self._parse_item(raw) for raw in order.get('items', [])]
        promos = order.get('applied_promotions', []) or []
        merchant_funded = sum(
            (money(p.get('merchant_funded_amount') or 0) for p in promos), money(0)
        )

        return CanonicalOrder(
            aggregator=self.aggregator,
            external_order_id=str(order.get('id') or order.get('order_id')),
            external_store_id=str(order.get('outlet_id') or order.get('store_id') or ''),
            status=EVENT_STATUS_MAP.get(event, OrderStatus.CREATED),
            order_type=ORDER_TYPE_MAP.get(
                (order.get('type') or 'DELIVERY').upper(), OrderType.DELIVERY
            ),
            items=items,
            subtotal=money(order.get('subtotal')) or sum(
                (i.line_total for i in items), money(0)
            ),
            discount_amount=money(order.get('discount_amount')),
            merchant_funded_discount=merchant_funded,
            tax_amount=money(order.get('tax')),
            delivery_fee=money(order.get('delivery_fee')),
            packaging_fee=money(order.get('packaging_fee')),
            total_amount=money(order.get('total') or order.get('grand_total')),
            short_order_number=str(order.get('order_number', '')),
            customer_name=(order.get('customer', {}) or {}).get('name', ''),
            customer_phone=(order.get('customer', {}) or {}).get('phone', ''),
            delivery_address=(order.get('delivery', {}) or {}).get('address', ''),
            driver_name=(order.get('driver', {}) or {}).get('name', ''),
            driver_phone=(order.get('driver', {}) or {}).get('phone', ''),
            notes=order.get('note', ''),
            placed_at=_parse_time(order.get('created_at')),
            external_status=event,
            raw_payload=payload,
        )

    def _parse_item(self, raw: dict) -> CanonicalOrderItem:
        modifiers = [
            CanonicalModifier(
                external_id=str(v.get('id', '')),
                name=v.get('name', ''),
                price=money(v.get('price')),
                quantity=money(v.get('quantity') or 1),
            )
            for v in (raw.get('variants') or raw.get('modifiers') or [])
        ]
        return CanonicalOrderItem(
            external_id=str(raw.get('id') or raw.get('item_id') or ''),
            name=raw.get('name', ''),
            quantity=money(raw.get('quantity') or 1),
            unit_price=money(raw.get('price')),
            modifiers=modifiers,
            notes=raw.get('note', ''),
        )

    def parse_status(self, payload: dict) -> CanonicalStatusUpdate | None:
        event = payload.get('event') or payload.get('type') or ''
        if event not in EVENT_STATUS_MAP:
            return None
        order = payload.get('order') or payload.get('data') or {}
        order_id = order.get('id') or order.get('order_id')
        if not order_id:
            return None
        driver = order.get('driver', {}) or {}
        return CanonicalStatusUpdate(
            aggregator=self.aggregator,
            external_order_id=str(order_id),
            status=EVENT_STATUS_MAP[event],
            external_status=event,
            driver_name=driver.get('name', ''),
            driver_phone=driver.get('phone', ''),
            cancel_reason=order.get('cancel_reason', ''),
            raw_payload=payload,
        )

    # ── Outbound ────────────────────────────────────────────────────────────

    def push_menu(self, store_link, menu: CanonicalMenu) -> dict:
        catalog = {
            'outlet_id': store_link.external_store_id,
            'currency': menu.currency,
            'categories': [
                {
                    'name': category,
                    'items': [
                        {
                            'id': item.external_id,
                            'name': item.name,
                            'description': item.description,
                            'price': str(item.price),
                            'is_available': item.is_available,
                            'image_url': item.image_url,
                            'position': item.display_order,
                            'variant_categories': [
                                {
                                    'id': group.external_id,
                                    'name': group.name,
                                    'min_selection': group.min_selections,
                                    'max_selection': group.max_selections,
                                    'is_required': group.is_required,
                                    'variants': [
                                        {
                                            'id': option.external_id,
                                            'name': option.name,
                                            'price': str(option.price),
                                            'is_available': option.is_available,
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
        }
        return self.request(
            'POST', f'/integrations/partner/{self.template.api_version}/catalog', json=catalog
        )

    def pull_menu(self, store_link) -> CanonicalMenu:
        """Read the menu currently live on GoFood — seeds first-time onboarding
        for a business that already has a working GoFood storefront.

        [VERIFY] Endpoint path and payload shape against the GoBiz developer
        portal once sandbox credentials exist; this mirrors ``push_menu``'s
        payload shape, which is the documented catalog structure.
        """
        data = self.request(
            'GET', f'/integrations/partner/{self.template.api_version}/catalog',
            params={'outlet_id': store_link.external_store_id},
        )
        categories = data.get('categories') or data.get('data', {}).get('categories') or []
        items = []
        for category in categories:
            category_name = category.get('name', 'Menu')
            for raw in category.get('items', []) or []:
                items.append(CanonicalMenuItem(
                    external_id=str(raw.get('id', '')),
                    name=raw.get('name', ''),
                    description=raw.get('description', ''),
                    price=money(raw.get('price')),
                    is_available=bool(raw.get('is_available', True)),
                    image_url=raw.get('image_url', ''),
                    display_order=int(raw.get('position', 0) or 0),
                    category=category_name,
                    modifier_groups=[
                        CanonicalMenuModifierGroup(
                            external_id=str(group.get('id', '')),
                            name=group.get('name', ''),
                            min_selections=int(group.get('min_selection', 0) or 0),
                            max_selections=int(group.get('max_selection', 1) or 1),
                            is_required=bool(group.get('is_required', False)),
                            options=[
                                CanonicalMenuModifier(
                                    external_id=str(v.get('id', '')),
                                    name=v.get('name', ''),
                                    price=money(v.get('price')),
                                    is_available=bool(v.get('is_available', True)),
                                )
                                for v in group.get('variants', []) or []
                            ],
                        )
                        for group in raw.get('variant_categories', []) or []
                    ],
                ))
        return CanonicalMenu(
            external_store_id=store_link.external_store_id,
            currency=data.get('currency', 'IDR'),
            items=items,
        )

    def push_item_availability(self, store_link, external_item_id, available) -> dict:
        return self.request(
            'PUT', f'/integrations/partner/{self.template.api_version}/catalog/item-status',
            json={
                'outlet_id': store_link.external_store_id,
                'item_id': external_item_id,
                'status': 'AVAILABLE' if available else 'OUT_OF_STOCK',
            },
        )

    def push_store_status(self, store_link, accepting_orders: bool) -> dict:
        return self.request(
            'PUT',
            f'/integrations/partner/outlets/{store_link.external_store_id}/'
            f'{self.template.api_version}/status',
            json={'status': 'OPEN' if accepting_orders else 'CLOSED'},
        )

    def push_order_status(self, order, status) -> dict:
        """GoFood is the one channel that accepts kitchen state back.

        Marking food ready lets Gojek dispatch the driver at the right moment
        instead of guessing, which measurably reduces food sitting on the pass.
        """
        if status != OrderStatus.READY:
            from .base import NotSupported
            raise NotSupported('GoFood hanya menerima status "food prepared".')
        return self.request(
            'PUT',
            f'/integrations/partner/{self.template.api_version}/orders/'
            f'{order.external_order_id}/food-prepared',
            json={},
        )

    # ── Onboarding (Facilitator) ────────────────────────────────────────────

    def begin_connect(self, session, redirect_uri: str) -> ConnectAction:
        cred = self.credential
        if not cred.client_id:
            return ConnectAction(
                kind='form',
                fields=['client_id', 'client_secret'],
                message=(
                    'Masukkan kredensial GoBiz Partner (Facilitator). Nilai ini '
                    'diberikan tim GoBiz sekali untuk seluruh perusahaan.'
                ),
            )
        params = {
            'client_id': cred.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.template.scopes),
            'state': session.oauth_state,
        }
        return ConnectAction(
            kind='redirect',
            redirect_url=f'{self.template.authorize_url}?{urlencode(params)}',
            message=(
                'Anda akan diarahkan ke GoBiz: masukkan nomor HP admin merchant, '
                'ketik OTP yang dikirim, lalu tekan Izinkan pada layar persetujuan. '
                'Kode berlaku sekitar 2 menit.'
            ),
        )

    def complete_connect(self, session, params: dict) -> None:
        """Exchange the authorization code immediately — it expires in ~2 min."""
        code = params.get('code')
        if not code:
            raise AuthError('GoBiz tidak mengirim authorization code.')
        cred = self.credential
        self._grant({
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': cred.client_id,
            'client_secret': cred.client_secret,
            'redirect_uri': params.get('redirect_uri', ''),
        })

    def discover_outlets(self) -> list[OutletInfo]:
        """Read the merchant's outlets straight from the token.

        This is why GoFood onboarding is better than Grab's: the operator picks
        from a list showing name *and address* rather than typing an id.
        """
        data = self.request(
            'GET', f'/integrations/partner/{self.template.api_version}/token-info'
        )
        outlets = data.get('outlets') or data.get('data', {}).get('outlets') or []
        return [
            OutletInfo(
                external_id=str(o.get('id') or o.get('outlet_id')),
                name=o.get('name', ''),
                address=o.get('address', ''),
                phone=o.get('phone', ''),
                email=o.get('email', ''),
            )
            for o in outlets
        ]

    def link_store(self, store_link) -> dict:
        return self.request(
            'PUT',
            f'/integrations/partner/outlets/{store_link.external_store_id}/'
            f'{self.template.api_version}/link/gofood',
            json={},
        )

    def unlink_store(self, store_link) -> dict:
        return self.request(
            'DELETE',
            f'/integrations/partner/outlets/{store_link.external_store_id}/'
            f'{self.template.api_version}/link/gofood',
        )

    def register_webhooks(self, callback_base_url: str) -> list:
        """Create or update all subscriptions in one idempotent pass.

        Re-running this repairs only what is missing: existing subscriptions are
        updated in place using their stored id, so pressing the button twice
        never produces duplicate deliveries.
        """
        from ..models import WebhookSubscription

        results = []
        base = f'/integrations/partner/{self.template.api_version}/notification-subscriptions'
        for event in self.template.webhook_events:
            callback = f'{callback_base_url.rstrip("/")}/{self.aggregator.lower()}/{self.credential.pk}/'
            sub, _ = WebhookSubscription.objects.get_or_create(
                credential=self.credential, event_name=event,
                defaults={'callback_url': callback},
            )
            try:
                if sub.external_subscription_id:
                    payload = {'event': event, 'callback_url': callback}
                    data = self.request(
                        'PUT', f'{base}/{sub.external_subscription_id}', json=payload
                    )
                else:
                    data = self.request(
                        'POST', base, json={'event': event, 'callback_url': callback}
                    )
                    sub.external_subscription_id = str(
                        data.get('id') or data.get('subscription_id') or ''
                    )
                sub.status = SyncStatus.SUCCESS
                sub.detail = ''
            except UpstreamError as exc:
                sub.status = SyncStatus.FAILED
                sub.detail = str(exc)
            sub.callback_url = callback
            sub.save()
            results.append(sub)
        return results

    def disconnect(self) -> None:
        base = f'/integrations/partner/{self.template.api_version}/notification-subscriptions'
        for sub in self.credential.webhook_subscriptions.all():
            if sub.external_subscription_id:
                try:
                    self.request('DELETE', f'{base}/{sub.external_subscription_id}')
                except UpstreamError:
                    # Already gone upstream, or credentials revoked first — the
                    # local disconnect must still complete.
                    pass
        self.credential.webhook_subscriptions.all().delete()
        super().disconnect()


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, dt_timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
