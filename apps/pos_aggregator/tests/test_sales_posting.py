"""Sales posting: allocation exactness and idempotency.

Money bugs here are silent and cumulative, so these tests assert exact totals
rather than approximate ones.
"""
from decimal import Decimal

from django.test import TestCase

from pos_aggregator.services.sales_posting import _allocate


class AllocateTest(TestCase):
    """Splitting an amount across lines must never lose or invent a cent."""

    def test_parts_sum_exactly_to_the_total(self):
        weights = [Decimal('10000'), Decimal('20000'), Decimal('30000')]
        shares = _allocate(Decimal('6600'), weights)
        self.assertEqual(sum(shares), Decimal('6600'))

    def test_indivisible_remainder_lands_on_the_largest_line(self):
        weights = [Decimal('1'), Decimal('1'), Decimal('1')]
        shares = _allocate(Decimal('10.00'), weights)
        self.assertEqual(sum(shares), Decimal('10.00'))

    def test_proportional_split(self):
        shares = _allocate(Decimal('300'), [Decimal('100'), Decimal('200')])
        self.assertEqual(shares[0], Decimal('100.00'))
        self.assertEqual(shares[1], Decimal('200.00'))

    def test_zero_total_gives_zero_everywhere(self):
        self.assertEqual(
            _allocate(Decimal('0'), [Decimal('1'), Decimal('2')]),
            [Decimal('0'), Decimal('0')],
        )

    def test_zero_weights_do_not_divide_by_zero(self):
        self.assertEqual(
            _allocate(Decimal('100'), [Decimal('0'), Decimal('0')]),
            [Decimal('0'), Decimal('0')],
        )

    def test_no_weights_returns_empty(self):
        self.assertEqual(_allocate(Decimal('100'), []), [])

    def test_awkward_thirds_still_reconcile(self):
        """1000 / 3 cannot be represented exactly; the total must still hold."""
        weights = [Decimal('1'), Decimal('1'), Decimal('1')]
        shares = _allocate(Decimal('1000.00'), weights)
        self.assertEqual(sum(shares), Decimal('1000.00'))
        self.assertEqual(len(shares), 3)

    def test_tax_is_not_duplicated_across_lines(self):
        """The regression this guards against.

        The cashier view writes the whole order-level tax onto every SalesItem,
        multiplying tax by the line count. Allocation must divide, not repeat.
        """
        order_tax = Decimal('5500')
        weights = [Decimal('25000'), Decimal('25000')]
        shares = _allocate(order_tax, weights)
        self.assertEqual(sum(shares), order_tax)
        self.assertNotEqual(shares[0], order_tax)
        self.assertEqual(shares[0], Decimal('2750.00'))
