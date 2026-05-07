import datetime
from decimal import Decimal
from django.db.models import Sum, Count
from django.db import transaction

from pos_orders.models import Order, OrderItem, OrderPayment
from pos_config.models import PaymentMethod
from apps.pos_reports.models import DailySalesSnapshot


def get_sales_summary(store, date_from: datetime.date, date_to: datetime.date) -> dict:
    """Aggregate completed orders for a date range."""
    orders = Order.objects.filter(
        store=store,
        status=Order.STATUS_COMPLETED,
        completed_at__date__gte=date_from,
        completed_at__date__lte=date_to,
    )
    agg = orders.aggregate(
        total_orders=Count('id'),
        gross_sales=Sum('subtotal'),
        total_discount=Sum('discount_amount'),
        total_tax=Sum('tax_amount'),
        total_service_charge=Sum('service_charge_amount'),
        net_sales=Sum('total_amount'),
    )
    return {
        'total_orders': agg['total_orders'] or 0,
        'gross_sales': agg['gross_sales'] or Decimal('0'),
        'total_discount': agg['total_discount'] or Decimal('0'),
        'total_tax': agg['total_tax'] or Decimal('0'),
        'total_service_charge': agg['total_service_charge'] or Decimal('0'),
        'net_sales': agg['net_sales'] or Decimal('0'),
    }


def get_top_products(store, date_from: datetime.date, date_to: datetime.date, limit: int = 10):
    """Return list of (POSProduct, total_qty, total_revenue) sorted by revenue desc."""
    from pos_catalog.models import POSProduct
    rows = (
        OrderItem.objects
        .filter(
            order__store=store,
            order__status=Order.STATUS_COMPLETED,
            order__completed_at__date__gte=date_from,
            order__completed_at__date__lte=date_to,
        )
        .values('product_id')
        .annotate(
            total_qty=Sum('quantity'),
            total_revenue=Sum('subtotal'),
        )
        .order_by('-total_revenue')[:limit]
    )
    product_ids = [r['product_id'] for r in rows]
    product_map = {p.pk: p for p in POSProduct.objects.filter(pk__in=product_ids)}
    return [
        (product_map[r['product_id']], r['total_qty'], r['total_revenue'])
        for r in rows
        if r['product_id'] in product_map
    ]


def get_payment_breakdown(store, date_from: datetime.date, date_to: datetime.date) -> dict:
    """Return dict of {method_type -> total_amount} for confirmed payments in period."""
    rows = (
        OrderPayment.objects
        .filter(
            order__store=store,
            order__status=Order.STATUS_COMPLETED,
            order__completed_at__date__gte=date_from,
            order__completed_at__date__lte=date_to,
            is_confirmed=True,
        )
        .values('payment_method__method_type')
        .annotate(total=Sum('amount'))
    )
    return {r['payment_method__method_type']: (r['total'] or Decimal('0')) for r in rows}


def get_laba_rugi(store, date_from: datetime.date, date_to: datetime.date) -> dict:
    """Return gross Laba/Rugi breakdown. COGS comes from SalesItem.cogs_amount via sales_header."""
    from apps.sales.models import SalesItem
    completed = Order.objects.filter(
        store=store,
        status=Order.STATUS_COMPLETED,
        completed_at__date__gte=date_from,
        completed_at__date__lte=date_to,
        sales_header__isnull=False,
    )
    net_sales = completed.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
    sales_header_ids = completed.values_list('sales_header_id', flat=True)
    cogs = (
        SalesItem.objects
        .filter(sales_eb__sales_header_id__in=sales_header_ids)
        .aggregate(s=Sum('cogs_amount'))['s'] or Decimal('0')
    )
    gross_profit = net_sales - cogs
    return {
        'net_sales': net_sales,
        'total_cogs': cogs,
        'gross_profit': gross_profit,
        'gross_margin_pct': (gross_profit / net_sales * 100) if net_sales else Decimal('0'),
    }


def generate_daily_snapshot(store, date: datetime.date, shift_log=None) -> DailySalesSnapshot:
    """Compute and persist (or update) a DailySalesSnapshot for store+date. Safe to call multiple times."""
    orders = Order.objects.filter(
        store=store,
        status=Order.STATUS_COMPLETED,
        completed_at__date=date,
    )
    agg = orders.aggregate(
        total_orders=Count('id'),
        gross_sales=Sum('subtotal'),
        total_discount=Sum('discount_amount'),
        total_tax=Sum('tax_amount'),
        total_service_charge=Sum('service_charge_amount'),
        net_sales=Sum('total_amount'),
        total_items=Sum('items__quantity'),
    )
    laba_rugi = get_laba_rugi(store, date, date)
    breakdown = get_payment_breakdown(store, date, date)
    refund_total = (
        Order.objects.filter(store=store, status=Order.STATUS_REFUNDED, completed_at__date=date)
        .aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
    )
    defaults = {
        'shift_log': shift_log,
        'total_orders': agg['total_orders'] or 0,
        'total_items': int(agg['total_items'] or 0),
        'gross_sales': agg['gross_sales'] or Decimal('0'),
        'total_discount': agg['total_discount'] or Decimal('0'),
        'total_tax': agg['total_tax'] or Decimal('0'),
        'total_service_charge': agg['total_service_charge'] or Decimal('0'),
        'net_sales': agg['net_sales'] or Decimal('0'),
        'total_cogs': laba_rugi['total_cogs'],
        'gross_profit': laba_rugi['gross_profit'],
        'cash_collected': breakdown.get(PaymentMethod.CASH, Decimal('0')),
        'qris_collected': breakdown.get(PaymentMethod.QRIS, Decimal('0')),
        'transfer_collected': breakdown.get(PaymentMethod.TRANSFER, Decimal('0')),
        'total_refunds': refund_total,
    }
    with transaction.atomic():
        snap, _ = DailySalesSnapshot.objects.update_or_create(
            store=store,
            date=date,
            defaults=defaults,
        )
    return snap
