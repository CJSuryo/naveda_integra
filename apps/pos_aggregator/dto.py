"""Canonical data transfer objects sitting between adapters and services.

Adapters translate an aggregator's payload into these shapes; services only ever
see these shapes. That boundary is what stops per-aggregator quirks leaking into
order handling and accounting.

**Money is always ``Decimal``.** Aggregators send minor units, tax-inclusive
totals and pre-applied discounts in inconsistent formats; float arithmetic on
those values silently corrupts financial records. ``money()`` is the single
conversion point.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .constants import OrderStatus, OrderType

#: Rupiah has no minor unit in practice, but modifiers and per-unit prices can
#: carry fractions before rounding, so amounts are carried at 2dp internally.
MONEY_QUANT = Decimal('0.01')


def money(value, *, divisor: Decimal | int = 1) -> Decimal:
    """Coerce any aggregator-supplied amount to a rounded ``Decimal``.

    ``divisor`` normalises minor units — GrabFood sends amounts multiplied by
    100, so ``money(raw, divisor=100)``.
    """
    if value is None or value == '':
        return Decimal('0')
    amount = Decimal(str(value))
    if divisor and divisor != 1:
        amount = amount / Decimal(str(divisor))
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class CanonicalModifier:
    """One selected add-on on an order line."""
    external_id: str
    name: str
    price: Decimal = Decimal('0')
    quantity: Decimal = Decimal('1')
    #: Resolved internal ItemMasterPurchase id, when the modifier maps to stock.
    item_id: int | None = None


@dataclass(slots=True)
class CanonicalOrderItem:
    external_id: str
    name: str
    quantity: Decimal
    #: Unit price *excluding* modifiers, net of tax.
    unit_price: Decimal
    modifiers: list[CanonicalModifier] = field(default_factory=list)
    notes: str = ''
    #: Resolved internal ItemMasterPurchase id. ``None`` means the aggregator
    #: sent an item we cannot map — ingestion records this rather than guessing.
    item_id: int | None = None

    @property
    def modifier_total(self) -> Decimal:
        return sum(
            (m.price * m.quantity for m in self.modifiers), Decimal('0')
        ).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @property
    def line_total(self) -> Decimal:
        return ((self.unit_price + self.modifier_total) * self.quantity).quantize(
            MONEY_QUANT, rounding=ROUND_HALF_UP
        )


@dataclass(slots=True)
class CanonicalOrder:
    """An aggregator order, normalised.

    ``subtotal``/``tax_amount``/``total_amount`` are net figures the adapter has
    already un-baked from the aggregator's tax-inclusive totals.
    """
    aggregator: str
    external_order_id: str
    external_store_id: str
    status: OrderStatus
    order_type: OrderType

    items: list[CanonicalOrderItem] = field(default_factory=list)

    subtotal: Decimal = Decimal('0')
    discount_amount: Decimal = Decimal('0')
    #: Portion of ``discount_amount`` funded by the merchant. Only this part
    #: reduces merchant revenue; aggregator-funded promos do not.
    merchant_funded_discount: Decimal = Decimal('0')
    tax_amount: Decimal = Decimal('0')
    delivery_fee: Decimal = Decimal('0')
    packaging_fee: Decimal = Decimal('0')
    total_amount: Decimal = Decimal('0')

    short_order_number: str = ''
    customer_name: str = ''
    customer_phone: str = ''
    delivery_address: str = ''
    driver_name: str = ''
    driver_phone: str = ''
    notes: str = ''

    placed_at: datetime | None = None
    #: Native aggregator status string, preserved for audit and debugging.
    external_status: str = ''
    raw_payload: dict = field(default_factory=dict)

    @property
    def has_unmapped_items(self) -> bool:
        return any(i.item_id is None for i in self.items)

    def computed_subtotal(self) -> Decimal:
        return sum((i.line_total for i in self.items), Decimal('0')).quantize(
            MONEY_QUANT, rounding=ROUND_HALF_UP
        )


@dataclass(slots=True)
class CanonicalStatusUpdate:
    """A lifecycle callback that is not a full order payload."""
    aggregator: str
    external_order_id: str
    status: OrderStatus
    external_status: str = ''
    driver_name: str = ''
    driver_phone: str = ''
    cancel_reason: str = ''
    raw_payload: dict = field(default_factory=dict)


@dataclass(slots=True)
class CanonicalMenuModifier:
    external_id: str
    name: str
    price: Decimal
    is_available: bool = True


@dataclass(slots=True)
class CanonicalMenuModifierGroup:
    external_id: str
    name: str
    min_selections: int
    max_selections: int
    is_required: bool
    options: list[CanonicalMenuModifier] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalMenuItem:
    external_id: str
    name: str
    description: str
    #: Channel price, already marked up for this aggregator's commission.
    price: Decimal
    is_available: bool
    image_url: str = ''
    display_order: int = 0
    category: str = 'Menu'
    modifier_groups: list[CanonicalMenuModifierGroup] = field(default_factory=list)


@dataclass(slots=True)
class CanonicalMenu:
    external_store_id: str
    currency: str = 'IDR'
    items: list[CanonicalMenuItem] = field(default_factory=list)

    def categories(self) -> dict[str, list[CanonicalMenuItem]]:
        grouped: dict[str, list[CanonicalMenuItem]] = {}
        for item in sorted(self.items, key=lambda i: (i.category, i.display_order, i.name)):
            grouped.setdefault(item.category, []).append(item)
        return grouped


@dataclass(slots=True)
class OutletInfo:
    """An outlet discovered on the merchant's aggregator account.

    Address matters more than name during onboarding: branch names are often
    near-identical ("Cabang 1", "Cabang 2") and mismatching them routes orders
    to the wrong kitchen.
    """
    external_id: str
    name: str
    address: str = ''
    phone: str = ''
    email: str = ''


@dataclass(slots=True)
class ConnectAction:
    """What the wizard should do next to connect an account.

    ``kind='redirect'`` sends the merchant to the aggregator to authorise.
    ``kind='form'`` means no consent flow exists and the listed fields must be
    supplied manually.
    """
    kind: str
    redirect_url: str = ''
    fields: list[str] = field(default_factory=list)
    message: str = ''


@dataclass(slots=True)
class CheckResult:
    """One pre-flight check outcome."""
    code: str
    label: str
    passed: bool
    detail: str = ''
    #: What the operator should do about a failure, in plain language.
    remedy: str = ''
