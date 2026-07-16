"""Hybrid UOM conversion engine.

- Physical universal conversions (kg<->g, L<->mL) use UnitOfMeasure.factor_to_base
  within one dimension; no item context needed.
- Packaging conversions (carton->pcs) differ per product and use ItemUOM keyed
  to the item's stock_uom.
"""
from decimal import Decimal

from .models import ItemUOM


class ConversionError(Exception):
    """Raised when a conversion cannot be resolved."""


def _universal(qty, from_uom, to_uom):
    """qty in from_uom -> to_uom via global factors (same dimension). None if N/A."""
    if (from_uom.dimension == to_uom.dimension
            and from_uom.factor_to_base is not None
            and to_uom.factor_to_base is not None):
        return qty * from_uom.factor_to_base / to_uom.factor_to_base
    return None


def to_stock_uom(qty: Decimal, from_uom, item) -> Decimal:
    """Convert qty expressed in from_uom into the item's stock_uom."""
    stock = item.stock_uom if item is not None else None
    if stock is None:
        raise ConversionError('Item tidak memiliki stock_uom.')
    if from_uom.pk == stock.pk:
        return qty
    iu = ItemUOM.objects.filter(item=item, uom=from_uom).first()
    if iu is not None:
        return qty * iu.qty_in_stock_uom
    universal = _universal(qty, from_uom, stock)
    if universal is not None:
        return universal
    raise ConversionError(
        f'Tidak dapat mengonversi {from_uom.kode} ke stock_uom {stock.kode} '
        f'untuk item {item.nama}.'
    )


def from_stock_uom(qty: Decimal, to_uom, item) -> Decimal:
    """Convert qty expressed in the item's stock_uom into to_uom."""
    stock = item.stock_uom if item is not None else None
    if stock is None:
        raise ConversionError('Item tidak memiliki stock_uom.')
    if to_uom.pk == stock.pk:
        return qty
    iu = ItemUOM.objects.filter(item=item, uom=to_uom).first()
    if iu is not None:
        if iu.qty_in_stock_uom == 0:
            raise ConversionError('qty_in_stock_uom tidak boleh 0.')
        return qty / iu.qty_in_stock_uom
    universal = _universal(qty, stock, to_uom)
    if universal is not None:
        return universal
    raise ConversionError(
        f'Tidak dapat mengonversi stock_uom {stock.kode} ke {to_uom.kode} '
        f'untuk item {item.nama}.'
    )


def convert_input_to_base(item, input_uom, input_qty, input_price):
    """Konversi (qty, harga) dalam input_uom ke base/stock_uom item.

    Return (qty_base, unit_price_base). Bila input_uom None -> passthrough.
    total_value (input_qty * input_price) dipertahankan sebagai sumber kebenaran;
    unit_price_base diturunkan dari total / qty_base.
    """
    input_qty = Decimal(str(input_qty))
    input_price = Decimal(str(input_price))
    if input_uom is None:
        return input_qty, input_price
    qty_base = to_stock_uom(input_qty, input_uom, item)
    total = input_qty * input_price
    unit_price_base = (total / qty_base) if qty_base else Decimal('0')
    return qty_base, unit_price_base


def convert(qty: Decimal, from_uom, to_uom, item=None) -> Decimal:
    """Convert qty from one UOM to another.

    Universal (physical, same dimension) conversions ignore ``item``.
    Packaging conversions require ``item``. Raises ConversionError if unresolved.
    """
    if from_uom.pk == to_uom.pk:
        return qty
    universal = _universal(qty, from_uom, to_uom)
    if universal is not None:
        return universal
    if item is None:
        raise ConversionError(
            f'Konversi {from_uom.kode} -> {to_uom.kode} membutuhkan konteks item '
            f'(satuan kemasan).'
        )
    base_qty = to_stock_uom(qty, from_uom, item)
    return from_stock_uom(base_qty, to_uom, item)
