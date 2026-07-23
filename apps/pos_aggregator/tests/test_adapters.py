"""Adapter behaviour that must not regress.

Signature verification and money normalisation are the two places where a
subtle change breaks the integration in a way that looks like something else:
a bad signature reads as a credentials problem, and a wrong divisor produces
plausible-looking but incorrect revenue.
"""
import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase

from pos_aggregator.adapters import SignatureError, get_adapter, get_adapter_class
from pos_aggregator.adapters.shopeefood import ShopeeFoodAdapter
from pos_aggregator.constants import AggregatorType, OrderStatus
from pos_aggregator.dto import money

from .factories import gofood_order_payload, make_credential


class _RawRequest:
    """Minimal stand-in carrying the raw body, which is what gets signed."""

    def __init__(self, body: bytes, headers=None, method='POST', path='/hook/'):
        self.body = body
        self.headers = headers or {}
        self.method = method
        self.path = path


class RegistryTest(TestCase):
    def test_every_aggregator_has_an_adapter(self):
        for value, _ in AggregatorType.choices:
            self.assertIsNotNone(get_adapter_class(value))

    def test_unknown_aggregator_is_refused(self):
        from pos_aggregator.adapters import NotSupported
        with self.assertRaises(NotSupported):
            get_adapter_class('DELIVEROO')


class GoFoodSignatureTest(TestCase):
    def setUp(self):
        self.credential = make_credential(aggregator=AggregatorType.GOFOOD)
        self.adapter = get_adapter(self.credential)
        self.secret = self.credential.webhook_secret

    def _signed(self, body: bytes, prefix=''):
        digest = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        return _RawRequest(body, {'X-Go-Signature': prefix + digest})

    def test_valid_signature_accepted(self):
        body = json.dumps({'a': 1}).encode()
        self.adapter.verify_webhook(self._signed(body))  # must not raise

    def test_tampered_body_rejected(self):
        body = json.dumps({'a': 1}).encode()
        request = self._signed(body)
        request.body = json.dumps({'a': 2}).encode()
        with self.assertRaises(SignatureError):
            self.adapter.verify_webhook(request)

    def test_missing_header_rejected(self):
        with self.assertRaises(SignatureError):
            self.adapter.verify_webhook(_RawRequest(b'{}'))

    def test_algorithm_prefixed_signature_accepted(self):
        body = json.dumps({'a': 1}).encode()
        self.adapter.verify_webhook(self._signed(body, prefix='sha256='))

    def test_signature_is_over_raw_bytes_not_reserialised_json(self):
        """Key order and whitespace must not change the verdict."""
        body = b'{"b": 2, "a": 1}'
        self.adapter.verify_webhook(self._signed(body))


class GoFoodParsingTest(TestCase):
    def setUp(self):
        self.adapter = get_adapter(make_credential(aggregator=AggregatorType.GOFOOD))

    def test_parses_order_into_decimals(self):
        order = self.adapter.parse_order(gofood_order_payload())
        self.assertIsNotNone(order)
        self.assertEqual(order.external_order_id, 'GO-1')
        self.assertEqual(order.status, OrderStatus.CREATED)
        self.assertIsInstance(order.total_amount, Decimal)
        self.assertEqual(order.total_amount, Decimal('55500.00'))
        self.assertEqual(order.items[0].quantity, Decimal('2'))

    def test_status_only_payload_is_not_an_order(self):
        payload = gofood_order_payload(event='order.completed')
        del payload['order']['items']
        self.assertIsNone(self.adapter.parse_order(payload))
        update = self.adapter.parse_status(payload)
        self.assertEqual(update.status, OrderStatus.COMPLETED)

    def test_unknown_event_produces_no_status(self):
        payload = gofood_order_payload(event='order.something_new')
        del payload['order']['items']
        self.assertIsNone(self.adapter.parse_status(payload))


class GrabFoodParsingTest(TestCase):
    def setUp(self):
        self.adapter = get_adapter(make_credential(aggregator=AggregatorType.GRABFOOD))

    def test_minor_units_are_divided_by_one_hundred(self):
        payload = {
            'orderID': 'GR-1',
            'state': 'ACCEPTED',
            'merchantID': 'M-1',
            'orderType': 'DELIVERY',
            'items': [{'id': '1', 'name': 'Ayam', 'quantity': 1, 'price': 1550000}],
            'price': {'subtotal': 1550000, 'tax': 170500, 'grandTotal': 1720500},
        }
        order = self.adapter.parse_order(payload)
        self.assertEqual(order.items[0].unit_price, Decimal('15500.00'))
        self.assertEqual(order.total_amount, Decimal('17205.00'))
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_grab_expects_a_204_acknowledgement(self):
        self.assertEqual(self.adapter.ack_status_code, 204)


class ShopeeFoodTest(TestCase):
    def setUp(self):
        self.credential = make_credential(aggregator=AggregatorType.SHOPEEFOOD)
        self.adapter = get_adapter(self.credential)

    def test_signature_uses_canonical_compact_json(self):
        payload = {'b': 2, 'a': 1}
        body = json.dumps(payload).encode()
        canonical = 'POST:/hook/:' + json.dumps(payload, separators=(',', ':'), sort_keys=True)
        digest = hmac.new(
            self.credential.webhook_secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()
        self.adapter.verify_webhook(_RawRequest(body, {'X-SF-Signature': digest}))

    def test_wrong_signature_rejected(self):
        with self.assertRaises(SignatureError):
            self.adapter.verify_webhook(
                _RawRequest(b'{"a":1}', {'X-SF-Signature': 'deadbeef'})
            )

    def test_store_id_format_is_validated_before_saving(self):
        ok, _ = self.adapter.validate_store_id('1234567890')
        self.assertTrue(ok)

        for bad in ('', 'ab', 'has space', 'toko#1'):
            ok, message = self.adapter.validate_store_id(bad)
            self.assertFalse(ok, bad)
            self.assertTrue(message)

    def test_ack_envelope_is_shopee_specific(self):
        self.assertEqual(self.adapter.ack_body(), {'code': 0, 'message': 'success'})

    def test_no_merchant_consent_flow_is_reported_honestly(self):
        action = self.adapter.begin_connect(session=None, redirect_uri='https://x/cb')
        self.assertEqual(action.kind, 'form')
        self.assertIn('client_id', action.fields)


class NotSupportedTest(TestCase):
    def test_outlet_discovery_refused_where_no_api_exists(self):
        from pos_aggregator.adapters import NotSupported
        adapter = get_adapter(make_credential(aggregator=AggregatorType.SHOPEEFOOD))
        with self.assertRaises(NotSupported):
            adapter.discover_outlets()

    def test_outbound_status_refused_on_grab(self):
        from pos_aggregator.adapters import NotSupported
        adapter = get_adapter(make_credential(aggregator=AggregatorType.GRABFOOD))
        with self.assertRaises(NotSupported):
            adapter.push_order_status(order=None, status=OrderStatus.READY)
