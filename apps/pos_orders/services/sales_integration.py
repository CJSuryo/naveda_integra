"""sales_integration.py — deprecated for manual cashier flow.

Manual POS cashier now creates SalesHeader directly via /sales/pos/.
This module is kept as a stub for future Phase 6 aggregator integration,
where external platform orders may need staging via pos_orders.Order
before converting to SalesHeader.
"""
