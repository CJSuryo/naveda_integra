"""Authoritative stock ledger engine — inflow, consumption, reversal, queries.

All quantities are in the item's base uom (Decimal). Bulk items (RMB/FGB/ITMB)
use the existing value-based convention (qty=1, unit_cost=total_value).
"""
from decimal import Decimal


class InsufficientStockError(ValueError):
    """Raised when consumption cannot be satisfied within the EB hierarchy."""
