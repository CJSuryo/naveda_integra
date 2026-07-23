"""GrabFood adapter.

Grab is the reference pattern for onboarding: the merchant authorises on Grab's
own site and Grab pushes the resulting store id back to our callback, so an
operator never types an outlet id.

Menu ownership is *pull*: we expose the catalog and tell Grab to fetch it, then
Grab reports the sync result asynchronously.

[VERIFY] Signature scheme, exact paths and the menu-notify contract must be
confirmed against Grab's partner documentation once sandbox credentials exist.
Everything is driven from ``config_templates`` and the constants below so the
corrections are localised.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from ..constants import AggregatorType, OrderStatus, OrderType
from ..dto import (
    CanonicalMenu, CanonicalModifier, CanonicalOrder, CanonicalOrderItem,
    CanonicalStatusUpdate, ConnectAction, money,
)
from .base import AuthError, BaseAdapter, SignatureError, constant_time_compare

#: Grab sends monetary amounts as integer minor units.
MINOR_UNIT_DIVISOR = 100

#: Grab's order-state vocabulary → canonical lifecycle.
STATE_MAP = {
    'UNCONFIRMED': OrderStatus.CREATED,
    'PENDING': OrderStatus.CREATED,
    'ACCEPTED': OrderStatus.ACCEPTED,
    'CONFIRMED': OrderStatus.ACCEPTED,
    'PREPARING': OrderStatus.PREPARING,
    'READY': OrderStatus.READY,
    'DRIVER_ALLOCATED': OrderStatus.READY,
    'DRIVER_ARRIVED': OrderStatus.DRIVER_ARRIVED,
    'COLLECTED': OrderStatus.PICKED_UP,
    'IN_DELIVERY': OrderStatus.PICKED_UP,
    'DELIVERED': OrderStatus.COMPLETED,
    'COMPLETED': OrderStatus.COMPLETED,
    'CANCELLED': OrderStatus.CANCELLED,
    'FAILED': OrderStatus.CANCELLED,
}

ORDER_TYPE_MAP = {
    'DELIVERY': OrderType.DELIVERY,
    'TAKEAWAY': OrderType.TAKEAWAY,
    'SELF_PICKUP': OrderType.TAKEAWAY,
    'DINE_IN': OrderType.DINE_IN,
}


class GrabFoodAdapter(BaseAdapter):
    aggregator = AggregatorType.GRABFOOD
    #: Grab treats anything other than 204 on its order webhook as a retry.
    ack_status_code = 204

    # ── Auth ────────────────────────────────────────────────────────────────

    def refresh_access_token(self) -> str:
        cred = self.credential
        if not cred.client_id or not cred.client_secret_encrypted:
            raise AuthError('GrabFood client_id/client_secret belum diisi.')
        payload = {
            'client_id': cred.client_id,
            'client_secret': cred.client_secret,
            'grant_type': 'client_credentials',
            'scope': ' '.join(self.template.scopes),
        }
        import requests
        try:
            response = requests.post(self.template.auth_url, json=payload, timeout=20)
        except requests.RequestException as exc:
            raise AuthError(f'GrabFood token request gagal: {exc}') from exc
        if response.status_code >= 400:
            raise AuthError(
                f'GrabFood menolak kredensial ({response.status_code}): {response.text[:500]}'
            )
        data = response.json()
        token = data.get('access_token', '')
        if not token:
            raise AuthError('GrabFood tidak mengembalikan access_token.')
        self.store_tokens(access_token=token, expires_in=data.get('expires_in', 3600))
        return token

    # ── Inbound ─────────────────────────────────────────────────────────────

    def verify_webhook(self, request) -> None:
        """HMAC-SHA256 over the canonical request description.

        [VERIFY] Grab's documented canonical string. The body hash is taken from
        the *raw* bytes; hashing re-serialised JSON would change the digest.
        """
        secret = self.credential.webhook_secret
        if not secret:
            raise SignatureError('GrabFood webhook secret belum dikonfigurasi.')

        provided = request.headers.get('X-Grab-Signature', '') or request.headers.get(
            'Authorization', ''
        ).replace('Bearer ', '')
        if not provided:
            raise SignatureError('Header tanda tangan GrabFood tidak ada.')

        body_hash = base64.b64encode(hashlib.sha256(request.body).digest()).decode()
        canonical = '\n'.join([
            request.method.upper(),
            request.headers.get('Content-Type', 'application/json'),
            request.headers.get('Date', ''),
            request.path,
            body_hash,
        ])
        expected = base64.b64encode(
            hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()
        ).decode()
        if not constant_time_compare(expected, provided):
            raise SignatureError('Tanda tangan GrabFood tidak cocok.')

    def extract_event_meta(self, payload: dict, request) -> dict:
        return {
            'event_type': payload.get('state') or payload.get('eventType') or 'order',
            'external_event_id': payload.get('eventID', '') or request.headers.get(
                'X-Grab-Delivery-Id', ''
            ),
            'external_order_id': payload.get('orderID', '') or payload.get('orderId', ''),
            'external_store_id': payload.get('merchantID', '') or payload.get('storeID', ''),
        }

    def parse_order(self, payload: dict) -> CanonicalOrder | None:
        if not payload.get('orderID') and not payload.get('orderId'):
            return None
        # A bare state callback carries no items; that is a status update.
        if 'items' not in payload and 'order' not in payload:
            return None

        body = payload.get('order') or payload
        items = [self._parse_item(raw) for raw in body.get('items', [])]

        native_state = (payload.get('state') or 'UNCONFIRMED').upper()
        price = body.get('price', {}) or {}

        subtotal = money(price.get('subtotal'), divisor=MINOR_UNIT_DIVISOR)
        tax = money(price.get('tax'), divisor=MINOR_UNIT_DIVISOR)
        total = money(price.get('grandTotal') or price.get('total'), divisor=MINOR_UNIT_DIVISOR)
        merchant_promo = money(
            price.get('merchantFundPromo') or price.get('merchantChargeAmount'),
            divisor=MINOR_UNIT_DIVISOR,
        )
        discount = money(price.get('discount'), divisor=MINOR_UNIT_DIVISOR) or merchant_promo

        return CanonicalOrder(
            aggregator=self.aggregator,
            external_order_id=str(body.get('orderID') or body.get('orderId')),
            external_store_id=str(body.get('merchantID') or body.get('storeID') or ''),
            status=STATE_MAP.get(native_state, OrderStatus.CREATED),
            order_type=ORDER_TYPE_MAP.get(
                (body.get('orderType') or 'DELIVERY').upper(), OrderType.DELIVERY
            ),
            items=items,
            subtotal=subtotal or sum((i.line_total for i in items), money(0)),
            discount_amount=discount,
            merchant_funded_discount=merchant_promo,
            tax_amount=tax,
            delivery_fee=money(price.get('deliveryFee'), divisor=MINOR_UNIT_DIVISOR),
            packaging_fee=money(price.get('packagingFee'), divisor=MINOR_UNIT_DIVISOR),
            total_amount=total,
            short_order_number=str(body.get('shortOrderNumber', '')),
            customer_name=(body.get('eater', {}) or {}).get('name', ''),
            customer_phone=(body.get('eater', {}) or {}).get('mobileNumber', ''),
            delivery_address=((body.get('eater', {}) or {}).get('address', {}) or {}).get(
                'address', ''
            ),
            notes=body.get('comment', '') or body.get('note', ''),
            placed_at=_parse_time(body.get('submitTime') or body.get('orderTime')),
            external_status=native_state,
            raw_payload=payload,
        )

    def _parse_item(self, raw: dict) -> CanonicalOrderItem:
        modifiers = [
            CanonicalModifier(
                external_id=str(m.get('id') or m.get('modifierID') or ''),
                name=m.get('name', ''),
                price=money(m.get('price'), divisor=MINOR_UNIT_DIVISOR),
                quantity=money(m.get('quantity') or 1),
            )
            for group in raw.get('modifierGroups', []) or []
            for m in (group.get('modifiers', []) or [])
        ]
        return CanonicalOrderItem(
            external_id=str(raw.get('id') or raw.get('itemID') or ''),
            name=raw.get('name', ''),
            quantity=money(raw.get('quantity') or 1),
            unit_price=money(raw.get('price'), divisor=MINOR_UNIT_DIVISOR),
            modifiers=modifiers,
            notes=raw.get('comment', ''),
        )

    def parse_status(self, payload: dict) -> CanonicalStatusUpdate | None:
        order_id = payload.get('orderID') or payload.get('orderId')
        state = (payload.get('state') or '').upper()
        if not order_id or not state:
            return None
        driver = payload.get('driver', {}) or {}
        return CanonicalStatusUpdate(
            aggregator=self.aggregator,
            external_order_id=str(order_id),
            status=STATE_MAP.get(state, OrderStatus.CREATED),
            external_status=state,
            driver_name=driver.get('name', ''),
            driver_phone=driver.get('mobileNumber', ''),
            cancel_reason=payload.get('cancelReason', '') or payload.get('reason', ''),
            raw_payload=payload,
        )

    # ── Outbound ────────────────────────────────────────────────────────────

    def push_menu(self, store_link, menu: CanonicalMenu) -> dict:
        """Grab pulls the menu; we only notify that it changed.

        The catalog itself is served from our own endpoint, which Grab fetches.
        """
        return self.request(
            'POST', '/grabfood/partner/v1/merchant/menu/notification',
            json={'merchantID': store_link.external_store_id},
        )

    def pull_menu(self, store_link):
        """GrabFood has nothing to pull: it never stores a menu of its own.

        Grab's model is the inverse of GoFood/ShopeeFood — Grab calls
        ``grab_menu_pull`` and fetches whatever Naveda currently serves. There
        is no separate "menu on Grab" to read back, even for a business that
        already sells on GrabFood today. That existing menu must be entered
        into Naveda's catalog once by hand; from then on the normal "Kirim
        Menu" push keeps Grab in sync.
        """
        from .base import NotSupported
        raise NotSupported(
            'GrabFood tidak menyimpan menu sendiri — GrabFood selalu mengambil '
            'menu dari Naveda, bukan sebaliknya. Menu yang sudah ada di GrabFood '
            'hari ini perlu dimasukkan sekali secara manual ke katalog Naveda; '
            'setelah itu tombol "Kirim Menu" akan menjaganya tetap sinkron.'
        )

    def push_item_availability(self, store_link, external_item_id, available) -> dict:
        return self.request(
            'PUT', '/grabfood/partner/v1/merchant/menu/entity/status',
            json={
                'merchantID': store_link.external_store_id,
                'entityID': external_item_id,
                'status': 'AVAILABLE' if available else 'UNAVAILABLE',
            },
        )

    def push_store_status(self, store_link, accepting_orders: bool) -> dict:
        return self.request(
            'PUT', '/grabfood/partner/v1/merchant/status',
            json={
                'merchantID': store_link.external_store_id,
                'status': 'OPEN' if accepting_orders else 'CLOSED',
            },
        )

    # ── Onboarding ──────────────────────────────────────────────────────────

    def begin_connect(self, session, redirect_uri: str) -> ConnectAction:
        cred = self.credential
        if not cred.client_id:
            return ConnectAction(
                kind='form',
                fields=['client_id', 'client_secret'],
                message=(
                    'Masukkan Client ID dan Client Secret dari Grab Merchant Portal. '
                    'Nilai ini diberikan Grab setelah akses Partner API disetujui.'
                ),
            )
        params = {
            'client_id': cred.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.template.scopes),
            'state': session.oauth_state,
        }
        from urllib.parse import urlencode
        return ConnectAction(
            kind='redirect',
            redirect_url=f'{self.template.authorize_url}?{urlencode(params)}',
            message='Setujui akses di situs Grab, lalu Anda akan kembali ke sini.',
        )

    def complete_connect(self, session, params: dict) -> None:
        """Grab issues app-level tokens, so connection is a credential check."""
        self.refresh_access_token()

    def link_store(self, store_link) -> dict:
        """Ask Grab for a self-activation URL for this branch.

        Grab returns a URL the merchant opens; after approval Grab calls our
        activation callback with the store id, which we then persist. The
        operator never sees or types that id.
        """
        result = self.request(
            'POST', '/grabfood/partner/v1/merchant/activation/url',
            json={
                'partnerMerchantID': str(store_link.store_config_id),
                'clientID': self.credential.client_id,
            },
        )
        store_link.activation_requested_at = timezone.now()
        store_link.save(update_fields=['activation_requested_at', 'updated_at'])
        return result

    def validate_store_id(self, value: str) -> tuple[bool, str]:
        ok, msg = super().validate_store_id(value)
        if not ok:
            return ok, msg
        return True, ''


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, dt_timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
