"""Ingestion behaviour: idempotency, ordering guards, and release timing.

These are the properties that keep the integration honest under the conditions
aggregators actually create — aggressive retries, near-simultaneous events, and
callbacks arriving out of order.
"""
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from pos_aggregator.constants import AggregatorType, OrderStatus, POSTrigger, WebhookStatus
from pos_aggregator.models import AggregatorOrder, AggregatorStoreLink, WebhookEvent
from pos_aggregator.services import ingest

from .factories import gofood_order_payload, make_credential, make_store_link


class _FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {'Content-Type': 'application/json'}


def _event(credential, payload, meta=None):
    adapter_meta = meta or {
        'event_type': payload.get('event', ''),
        'external_event_id': payload.get('id', ''),
        'external_order_id': payload['order']['id'],
        'external_store_id': payload['order']['outlet_id'],
    }
    return ingest.record_event(
        aggregator=credential.aggregator, payload=payload,
        request=_FakeRequest(), meta=adapter_meta, signature_verified=True,
    )


class RecordEventTest(TestCase):
    def setUp(self):
        self.credential = make_credential()

    def test_stores_payload_before_processing(self):
        payload = gofood_order_payload()
        event = _event(self.credential, payload)
        self.assertEqual(event.payload, payload)
        self.assertEqual(event.status, WebhookStatus.RECEIVED)

    def test_repeated_event_id_returns_same_row(self):
        payload = gofood_order_payload()
        first = _event(self.credential, payload)
        second = _event(self.credential, payload)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_authorization_header_is_never_persisted(self):
        payload = gofood_order_payload()
        request = _FakeRequest({'Authorization': 'Bearer super-secret', 'X-Go-Signature': 'abc'})
        event = ingest.record_event(
            aggregator=self.credential.aggregator, payload=payload, request=request,
            meta={'external_event_id': 'e1', 'external_order_id': 'GO-1',
                  'external_store_id': 'OUTLET-1', 'event_type': 'order.created'},
            signature_verified=True,
        )
        self.assertNotIn('Authorization', event.headers)
        self.assertIn('X-Go-Signature', event.headers)


class ProcessEventTest(TestCase):
    def setUp(self):
        self.credential = make_credential()
        self.link = make_store_link(self.credential, external_store_id='OUTLET-1')

    def test_creates_order_with_items(self):
        event = _event(self.credential, gofood_order_payload())
        order = ingest.process_event(event)
        self.assertIsNotNone(order)
        self.assertEqual(order.external_order_id, 'GO-1')
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.status, OrderStatus.CREATED)
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookStatus.PROCESSED)

    def test_retried_create_does_not_duplicate_the_order(self):
        payload = gofood_order_payload()
        ingest.process_event(_event(self.credential, payload))

        # Same order, different delivery id — the aggregator retrying.
        retry = dict(payload)
        retry['id'] = 'evt-retry'
        ingest.process_event(_event(self.credential, retry))

        self.assertEqual(AggregatorOrder.objects.count(), 1)

    def test_database_constraint_blocks_duplicate_even_without_the_lock(self):
        ingest.process_event(_event(self.credential, gofood_order_payload()))
        with self.assertRaises(IntegrityError):
            AggregatorOrder.objects.create(
                store_link=self.link, aggregator=AggregatorType.GOFOOD,
                external_order_id='GO-1',
            )

    def test_status_callback_advances_the_order(self):
        ingest.process_event(_event(self.credential, gofood_order_payload()))
        accepted = gofood_order_payload(event='order.merchant_accepted')
        accepted['id'] = 'evt-accepted'
        del accepted['order']['items']  # a status callback carries no lines
        order = ingest.process_event(_event(self.credential, accepted))
        self.assertEqual(order.status, OrderStatus.ACCEPTED)

    def test_out_of_order_callback_cannot_rewind_the_order(self):
        ingest.process_event(_event(self.credential, gofood_order_payload()))
        order = AggregatorOrder.objects.get()
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=['status'])

        late = gofood_order_payload(event='order.merchant_accepted')
        late['id'] = 'evt-late'
        del late['order']['items']
        ingest.process_event(_event(self.credential, late))

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.COMPLETED)

    def test_cancellation_is_allowed_from_any_live_state(self):
        ingest.process_event(_event(self.credential, gofood_order_payload()))
        order = AggregatorOrder.objects.get()
        order.status = OrderStatus.PICKED_UP
        order.save(update_fields=['status'])

        cancel = gofood_order_payload(event='order.cancelled')
        cancel['id'] = 'evt-cancel'
        del cancel['order']['items']
        ingest.process_event(_event(self.credential, cancel))

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_order_for_unknown_outlet_is_rejected_not_guessed(self):
        payload = gofood_order_payload(outlet_id='OUTLET-UNKNOWN')
        with self.assertRaises(ingest.StoreNotLinked):
            ingest.process_event(_event(self.credential, payload))

    def test_status_before_create_is_left_for_replay(self):
        status_only = gofood_order_payload(event='order.completed')
        status_only['id'] = 'evt-orphan'
        del status_only['order']['items']
        event = _event(self.credential, status_only)
        self.assertIsNone(ingest.process_event(event))
        event.refresh_from_db()
        self.assertEqual(event.status, WebhookStatus.FAILED)

    def test_unmapped_items_are_flagged_not_dropped(self):
        payload = gofood_order_payload(items=[
            {'id': 'not-a-catalog-id', 'name': 'Misteri', 'quantity': 1, 'price': '1000'},
        ])
        order = ingest.process_event(_event(self.credential, payload))
        self.assertTrue(order.has_unmapped_items)
        self.assertEqual(order.items.count(), 1)


class ReleaseTriggerTest(TestCase):
    """Which lifecycle event hands the order to the kitchen."""

    def _order(self, trigger):
        credential = make_credential(pos_trigger=trigger)
        make_store_link(credential, external_store_id='OUTLET-1')
        ingest.process_event(_event(credential, gofood_order_payload()))
        return credential, AggregatorOrder.objects.get()

    def test_on_created_releases_immediately(self):
        _, order = self._order(POSTrigger.ON_CREATED)
        self.assertTrue(order.released_to_kitchen)

    def test_on_driver_arrived_waits(self):
        credential, order = self._order(POSTrigger.ON_DRIVER_ARRIVED)
        self.assertFalse(order.released_to_kitchen)

        arrived = gofood_order_payload(event='order.driver_arrived')
        arrived['id'] = 'evt-arrived'
        del arrived['order']['items']
        ingest.process_event(_event(credential, arrived))

        order.refresh_from_db()
        self.assertTrue(order.released_to_kitchen)

    def test_release_is_idempotent(self):
        credential, order = self._order(POSTrigger.ON_CREATED)
        released_logs = order.logs.filter(action='RELEASED_TO_KITCHEN').count()

        accepted = gofood_order_payload(event='order.merchant_accepted')
        accepted['id'] = 'evt-accepted'
        del accepted['order']['items']
        ingest.process_event(_event(credential, accepted))

        order.refresh_from_db()
        self.assertEqual(
            order.logs.filter(action='RELEASED_TO_KITCHEN').count(), released_logs
        )


class StoreLinkUniquenessTest(TestCase):
    def test_two_branches_cannot_claim_the_same_outlet(self):
        credential = make_credential()
        make_store_link(credential, external_store_id='OUTLET-9')
        from pos_config.tests.factories import make_store
        other_branch = make_store(merchant=credential.merchant_config)
        with self.assertRaises(IntegrityError):
            AggregatorStoreLink.objects.create(
                store_config=other_branch, credential=credential,
                aggregator=credential.aggregator, external_store_id='OUTLET-9',
            )


class TransitionGuardTest(TestCase):
    def setUp(self):
        credential = make_credential()
        link = make_store_link(credential)
        self.order = AggregatorOrder.objects.create(
            store_link=link, aggregator=credential.aggregator,
            external_order_id='X-1', status=OrderStatus.ACCEPTED,
        )

    def test_forward_transition_allowed(self):
        self.assertTrue(self.order.can_advance_to(OrderStatus.READY))

    def test_backward_transition_refused(self):
        self.assertFalse(self.order.can_advance_to(OrderStatus.CREATED))

    def test_same_status_refused(self):
        self.assertFalse(self.order.can_advance_to(OrderStatus.ACCEPTED))

    def test_cancel_always_allowed_while_live(self):
        self.assertTrue(self.order.can_advance_to(OrderStatus.CANCELLED))

    def test_nothing_moves_after_a_terminal_state(self):
        self.order.status = OrderStatus.CANCELLED
        self.assertFalse(self.order.can_advance_to(OrderStatus.COMPLETED))
        self.order.status = OrderStatus.COMPLETED
        self.assertFalse(self.order.can_advance_to(OrderStatus.CANCELLED))
