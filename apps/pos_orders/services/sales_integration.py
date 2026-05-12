"""sales_integration.py — deprecated for manual cashier flow.

Manual POS cashier now creates SalesHeader directly via /sales/pos/.
This module is kept as a stub for future Phase 6 aggregator integration,
where external platform orders may need staging via pos_orders.Order
before converting to SalesHeader.
"""


def create_sales_from_order(order):
    raise NotImplementedError(
        'create_sales_from_order is deprecated. Manual cashier uses /sales/pos/ directly. '
        'Aggregator integration is planned for Phase 6.'
    )


def reverse_sales_for_refund(refund):
    raise NotImplementedError(
        'reverse_sales_for_refund is deprecated. '
        'Refund reversal via aggregator path is planned for Phase 6.'
    )
