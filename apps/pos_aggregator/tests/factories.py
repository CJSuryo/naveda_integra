"""Builders for aggregator test fixtures."""
from decimal import Decimal

from pos_config.tests.factories import make_lv2, make_lv3, make_merchant, make_store

from pos_aggregator.constants import AggregatorType, Environment, LinkStatus
from pos_aggregator.models import AggregatorCredential, AggregatorStoreLink


def make_credential(merchant=None, aggregator=AggregatorType.GOFOOD, **kwargs):
    credential = AggregatorCredential.objects.create(
        merchant_config=merchant or make_merchant(),
        aggregator=aggregator,
        country='ID',
        environment=kwargs.pop('environment', Environment.PRODUCTION),
        client_id=kwargs.pop('client_id', 'test-client'),
        is_active=kwargs.pop('is_active', True),
        **kwargs,
    )
    credential.client_secret = 'test-secret'
    credential.webhook_secret = 'test-webhook-secret'
    credential.save()
    return credential


def make_store_link(credential=None, store=None, external_store_id='OUTLET-1', **kwargs):
    credential = credential or make_credential()
    if store is None:
        store = make_store(merchant=credential.merchant_config)
    return AggregatorStoreLink.objects.create(
        store_config=store,
        credential=credential,
        aggregator=credential.aggregator,
        external_store_id=external_store_id,
        status=kwargs.pop('status', LinkStatus.LINKED),
        **kwargs,
    )


def gofood_order_payload(order_id='GO-1', outlet_id='OUTLET-1', event='order.created',
                         items=None):
    return {
        'event': event,
        'id': f'evt-{order_id}-{event}',
        'order': {
            'id': order_id,
            'outlet_id': outlet_id,
            'order_number': 'A-100',
            'type': 'DELIVERY',
            'subtotal': '50000',
            'tax': '5500',
            'total': '55500',
            'delivery_fee': '10000',
            'customer': {'name': 'Budi', 'phone': '0812'},
            'items': items if items is not None else [
                {'id': '1', 'name': 'Nasi Goreng', 'quantity': 2, 'price': '25000'},
            ],
        },
    }
