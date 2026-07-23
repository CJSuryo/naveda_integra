"""ShopeeFood adapter.

ShopeeFood has **no public merchant-consent flow**. Access is granted
case-by-case by Shopee, credentials are provisioned out of band by an
administrator, and the operator supplies exactly one value per branch: the
store id.

Do not promise zero-touch ShopeeFood onboarding. What this adapter delivers is
the next best thing — one guided, format-validated copy-paste, with a worked
example on screen — and every other step automated.

[VERIFY] Signature canonical string, endpoint paths and the ack envelope against
Shopee's partner documentation once credentials are issued.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone as dt_timezone

import requests

from ..constants import AggregatorType, OrderStatus, OrderType
from ..dto import (
    CanonicalMenu, CanonicalMenuItem, CanonicalMenuModifier, CanonicalMenuModifierGroup,
    CanonicalModifier, CanonicalOrder, CanonicalOrderItem, CanonicalStatusUpdate,
    ConnectAction, money,
)
from .base import AuthError, BaseAdapter, SignatureError, constant_time_compare

#: Shopee normalises money by a fixed divisor rather than sending minor units.
AMOUNT_DIVISOR = 100000

STATUS_MAP = {
    'ORDER_CREATE': OrderStatus.CREATED,
    'NEW': OrderStatus.CREATED,
    'CONFIRMED': OrderStatus.ACCEPTED,
    'MERCHANT_CONFIRMED': OrderStatus.ACCEPTED,
    'PREPARING': OrderStatus.PREPARING,
    'READY': OrderStatus.READY,
    'DRIVER_ASSIGNED': OrderStatus.READY,
    'DRIVER_ARRIVED': OrderStatus.DRIVER_ARRIVED,
    'PICKED_UP': OrderStatus.PICKED_UP,
    'DELIVERED': OrderStatus.COMPLETED,
    'COMPLETED': OrderStatus.COMPLETED,
    'CANCELLED': OrderStatus.CANCELLED,
    'ORDER_CANCEL': OrderStatus.CANCELLED,
}

ORDER_TYPE_MAP = {
    'DELIVERY': OrderType.DELIVERY,
    'PICKUP': OrderType.TAKEAWAY,
    'SELF_PICKUP': OrderType.TAKEAWAY,
}

#: Shopee store ids observed as digit strings. Kept deliberately loose — a
#: too-strict rule blocks a legitimate id, which is worse than a soft warning.
STORE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{4,64}$')


class ShopeeFoodAdapter(BaseAdapter):
    aggregator = AggregatorType.SHOPEEFOOD
    ack_status_code = 200

    # ── Auth ────────────────────────────────────────────────────────────────

    def refresh_access_token(self) -> str:
        cred = self.credential
        if not cred.client_id or not cred.client_secret_encrypted:
            raise AuthError(
                'Kredensial ShopeeFood belum diisi. Administrator harus '
                'memasukkannya sekali di halaman kredensial.'
            )
        timestamp = int(time.time())
        base_string = f'{cred.client_id}{timestamp}'
        sign = hmac.new(
            cred.client_secret.encode(), base_string.encode(), hashlib.sha256
        ).hexdigest()
        try:
            response = requests.post(
                self.template.auth_url,
                json={'partner_id': cred.client_id, 'timestamp': timestamp, 'sign': sign},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise AuthError(f'ShopeeFood token request gagal: {exc}') from exc
        if response.status_code >= 400:
            raise AuthError(
                f'ShopeeFood menolak kredensial ({response.status_code}): {response.text[:500]}'
            )
        data = response.json()
        token = data.get('access_token', '')
        if not token:
            raise AuthError('ShopeeFood tidak mengembalikan access_token.')
        self.store_tokens(
            access_token=token,
            expires_in=data.get('expire_in') or data.get('expires_in') or 3600,
            refresh_token=data.get('refresh_token', ''),
        )
        return token

    # ── Inbound ─────────────────────────────────────────────────────────────

    def verify_webhook(self, request) -> None:
        """HMAC-SHA256 over ``METHOD:path:payload``.

        Unlike GoFood, Shopee signs a *canonicalised* string built from compact
        JSON. The compact separators matter: a space after ``:`` or ``,``
        produces a different digest.
        """
        secret = self.credential.webhook_secret or self.credential.client_secret
        if not secret:
            raise SignatureError('ShopeeFood webhook secret belum dikonfigurasi.')
        provided = request.headers.get('X-SF-Signature', '') or request.headers.get(
            'Authorization', ''
        )
        if not provided:
            raise SignatureError('Header X-SF-Signature tidak ada.')
        try:
            payload = json.loads(request.body or b'{}')
        except ValueError:
            raise SignatureError('Body ShopeeFood bukan JSON yang valid.')
        canonical = '{}:{}:{}'.format(
            request.method.upper(),
            request.path,
            json.dumps(payload, separators=(',', ':'), sort_keys=True),
        )
        expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if not constant_time_compare(expected, provided.strip()):
            raise SignatureError('Tanda tangan ShopeeFood tidak cocok.')

    def extract_event_meta(self, payload: dict, request) -> dict:
        order = payload.get('order') or payload.get('data') or payload
        return {
            'event_type': payload.get('event_type') or payload.get('status') or '',
            'external_event_id': str(payload.get('request_id', '')),
            'external_order_id': str(order.get('order_id') or order.get('id') or ''),
            'external_store_id': str(order.get('store_id') or payload.get('store_id') or ''),
        }

    def parse_order(self, payload: dict) -> CanonicalOrder | None:
        order = payload.get('order') or payload.get('data') or {}
        if not (order.get('order_id') or order.get('id')):
            return None
        if not order.get('items') and not order.get('order_items'):
            return None

        raw_items = order.get('items') or order.get('order_items') or []
        items = [self._parse_item(raw) for raw in raw_items]
        native = (payload.get('event_type') or order.get('status') or 'NEW').upper()

        return CanonicalOrder(
            aggregator=self.aggregator,
            external_order_id=str(order.get('order_id') or order.get('id')),
            external_store_id=str(order.get('store_id') or ''),
            status=STATUS_MAP.get(native, OrderStatus.CREATED),
            order_type=ORDER_TYPE_MAP.get(
                (order.get('order_type') or 'DELIVERY').upper(), OrderType.DELIVERY
            ),
            items=items,
            subtotal=money(order.get('subtotal'), divisor=AMOUNT_DIVISOR) or sum(
                (i.line_total for i in items), money(0)
            ),
            discount_amount=money(order.get('discount'), divisor=AMOUNT_DIVISOR),
            merchant_funded_discount=money(
                order.get('merchant_discount'), divisor=AMOUNT_DIVISOR
            ),
            tax_amount=money(order.get('tax'), divisor=AMOUNT_DIVISOR),
            delivery_fee=money(order.get('delivery_fee'), divisor=AMOUNT_DIVISOR),
            packaging_fee=money(order.get('packaging_fee'), divisor=AMOUNT_DIVISOR),
            total_amount=money(order.get('total_amount'), divisor=AMOUNT_DIVISOR),
            short_order_number=str(order.get('order_sn', '')),
            customer_name=(order.get('customer', {}) or {}).get('name', ''),
            customer_phone=(order.get('customer', {}) or {}).get('phone', ''),
            delivery_address=(order.get('delivery_address') or {}).get('address', '')
            if isinstance(order.get('delivery_address'), dict)
            else str(order.get('delivery_address') or ''),
            notes=order.get('remark', ''),
            placed_at=_parse_time(order.get('create_time')),
            external_status=native,
            raw_payload=payload,
        )

    def _parse_item(self, raw: dict) -> CanonicalOrderItem:
        modifiers = [
            CanonicalModifier(
                external_id=str(o.get('option_id', '')),
                name=o.get('name', ''),
                price=money(o.get('price'), divisor=AMOUNT_DIVISOR),
                quantity=money(o.get('quantity') or 1),
            )
            for group in (raw.get('option_groups') or [])
            for o in (group.get('options') or [])
        ]
        return CanonicalOrderItem(
            external_id=str(raw.get('item_id') or raw.get('dish_id') or ''),
            name=raw.get('name', ''),
            quantity=money(raw.get('quantity') or 1),
            unit_price=money(raw.get('price'), divisor=AMOUNT_DIVISOR),
            modifiers=modifiers,
            notes=raw.get('remark', ''),
        )

    def parse_status(self, payload: dict) -> CanonicalStatusUpdate | None:
        order = payload.get('order') or payload.get('data') or {}
        order_id = order.get('order_id') or order.get('id')
        native = (payload.get('event_type') or order.get('status') or '').upper()
        if not order_id or native not in STATUS_MAP:
            return None
        driver = order.get('driver', {}) or {}
        return CanonicalStatusUpdate(
            aggregator=self.aggregator,
            external_order_id=str(order_id),
            status=STATUS_MAP[native],
            external_status=native,
            driver_name=driver.get('name', ''),
            driver_phone=driver.get('phone', ''),
            cancel_reason=order.get('cancel_reason', ''),
            raw_payload=payload,
        )

    def ack_body(self) -> dict:
        """Shopee expects its own envelope, not a bare 200."""
        return {'code': 0, 'message': 'success'}

    # ── Outbound ────────────────────────────────────────────────────────────

    def push_menu(self, store_link, menu: CanonicalMenu) -> dict:
        payload = {
            'store_id': store_link.external_store_id,
            'menus': [
                {
                    'name': category,
                    'dishes': [
                        {
                            'dish_id': item.external_id,
                            'name': item.name,
                            'description': item.description,
                            'price': str(item.price),
                            'status': 1 if item.is_available else 0,
                            'photo': item.image_url,
                            'sort_order': item.display_order,
                            'option_groups': [
                                {
                                    'group_id': group.external_id,
                                    'name': group.name,
                                    'min_select': group.min_selections,
                                    'max_select': group.max_selections,
                                    'required': group.is_required,
                                    'options': [
                                        {
                                            'option_id': option.external_id,
                                            'name': option.name,
                                            'price': str(option.price),
                                            'status': 1 if option.is_available else 0,
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
        return self.request('POST', '/api/v2/food/menu/upload', json=payload)

    def pull_menu(self, store_link) -> CanonicalMenu:
        """Read the menu currently live on ShopeeFood — best-effort.

        [VERIFY] Endpoint path against Shopee's Open Platform docs once
        credentials exist. ShopeeFood's partner API access itself is granted
        case-by-case, so this path is the least likely of the three to have
        been exercised before a real sandbox run.
        """
        data = self.request(
            'GET', '/api/v2/food/menu/get',
            params={'store_id': store_link.external_store_id},
        )
        menus = data.get('menus') or data.get('response', {}).get('menus') or []
        items = []
        for category in menus:
            category_name = category.get('name', 'Menu')
            for raw in category.get('dishes', []) or []:
                items.append(CanonicalMenuItem(
                    external_id=str(raw.get('dish_id', '')),
                    name=raw.get('name', ''),
                    description=raw.get('description', ''),
                    price=money(raw.get('price')),
                    is_available=bool(raw.get('status', 1)),
                    image_url=raw.get('photo', ''),
                    display_order=int(raw.get('sort_order', 0) or 0),
                    category=category_name,
                    modifier_groups=[
                        CanonicalMenuModifierGroup(
                            external_id=str(group.get('group_id', '')),
                            name=group.get('name', ''),
                            min_selections=int(group.get('min_select', 0) or 0),
                            max_selections=int(group.get('max_select', 1) or 1),
                            is_required=bool(group.get('required', False)),
                            options=[
                                CanonicalMenuModifier(
                                    external_id=str(o.get('option_id', '')),
                                    name=o.get('name', ''),
                                    price=money(o.get('price')),
                                    is_available=bool(o.get('status', 1)),
                                )
                                for o in group.get('options', []) or []
                            ],
                        )
                        for group in raw.get('option_groups', []) or []
                    ],
                ))
        return CanonicalMenu(
            external_store_id=store_link.external_store_id,
            currency='IDR',
            items=items,
        )

    def push_item_availability(self, store_link, external_item_id, available) -> dict:
        return self.request(
            'POST', '/api/v2/food/dish/update_status',
            json={
                'store_id': store_link.external_store_id,
                'dish_id': external_item_id,
                'status': 1 if available else 0,
            },
        )

    def push_store_status(self, store_link, accepting_orders: bool) -> dict:
        return self.request(
            'POST', '/api/v2/food/store/update_status',
            json={
                'store_id': store_link.external_store_id,
                'status': 1 if accepting_orders else 0,
            },
        )

    # ── Onboarding ──────────────────────────────────────────────────────────

    def begin_connect(self, session, redirect_uri: str) -> ConnectAction:
        """No consent flow exists — collect credentials directly.

        This is a restricted step: these values are issued by Shopee to the
        company, not to the branch operator.
        """
        return ConnectAction(
            kind='form',
            fields=['client_id', 'client_secret'],
            message=(
                'ShopeeFood tidak menyediakan alur persetujuan otomatis. '
                'Administrator memasukkan Partner ID dan Partner Secret dari '
                'Shopee sekali saja; operator cabang tidak perlu melihat nilai ini.'
            ),
        )

    def complete_connect(self, session, params: dict) -> None:
        self.refresh_access_token()

    def validate_store_id(self, value: str) -> tuple[bool, str]:
        """Guard the one value an operator types by hand.

        A wrong store id attaches a branch's orders to the wrong kitchen and
        books its revenue against the wrong entity, so this is checked before
        it is ever saved.
        """
        value = (value or '').strip()
        if not value:
            return False, 'Store ID tidak boleh kosong.'
        if not STORE_ID_PATTERN.match(value):
            return False, (
                'Format Store ID tidak sesuai. Nilai yang benar berupa 4–64 '
                'karakter huruf/angka, contoh: 1234567890. Pastikan Anda '
                'menyalin ID outlet, bukan nama toko atau ID akun.'
            )
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
