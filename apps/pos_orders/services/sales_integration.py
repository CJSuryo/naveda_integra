from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
from apps.sales.services import process_sales_fifo, create_sales_automated_journals
from apps.sales.services import reverse_sales_fifo, reverse_sales_automated_journals


def create_sales_from_order(order) -> SalesHeader:
    """Create SalesHeader + run FIFO + run journal automation for a completed order.

    Raises ValueError if:
    - order.status != COMPLETED
    - order.sales_header already set (idempotent guard)
    - merchant missing required accounting fields
    """
    if order.status != order.STATUS_COMPLETED:
        raise ValueError(
            f'Order {order.order_number} status must be COMPLETED, got {order.status}'
        )
    if order.sales_header_id is not None:
        raise ValueError(
            f'Order {order.order_number} already integrated: sales_header={order.sales_header_id}'
        )

    merchant = order.store.merchant_config
    _validate_merchant_accounting(merchant, order)

    with transaction.atomic():
        sales = SalesHeader.objects.create(
            tanggal=order.completed_at.date() if order.completed_at else timezone.localdate(),
            deskripsi=f'POS Order {order.order_number}',
        )

        lv2 = order.store.entitas_bisnis_lv2
        eb = lv2.entitas_bisnis

        payment_account = _get_payment_account(order, merchant)

        sales_eb = SalesEntitasBisnis.objects.create(
            sales_header=sales,
            entitas_bisnis=eb,
            entitas_bisnis_lv2=lv2,
            payment_account=payment_account,
        )

        active_items = order.items.filter(
            status__in=['PENDING', 'PREPARING', 'READY']
        ).select_related('product__item_master')

        for order_item in active_items:
            SalesItem.objects.create(
                sales_eb=sales_eb,
                item=order_item.product.item_master,
                sub_transaction_type=merchant.sub_transaction_type,
                quantity=order_item.quantity,
                selling_price=order_item.unit_price + order_item.modifier_total,
                offset_coa_account=merchant.offset_coa_account,
                revenue_account=merchant.revenue_account,
                payment_account=payment_account,
            )

        process_sales_fifo(sales)
        create_sales_automated_journals(sales)

        order.sales_header = sales
        order.save(update_fields=['sales_header'])

    return sales


def reverse_sales_for_refund(refund) -> None:
    """Reverse FIFO and journals for a completed refund.

    Raises ValueError if refund.order has no sales_header.
    """
    order = refund.order
    if not order.sales_header_id:
        raise ValueError(
            f'Order {order.order_number} has no sales_header — cannot reverse'
        )

    with transaction.atomic():
        reverse_sales_automated_journals(order.sales_header)
        reverse_sales_fifo(order.sales_header)

        order.status = order.STATUS_REFUNDED
        order.save(update_fields=['status'])


def _validate_merchant_accounting(merchant, order):
    missing = []
    if not merchant.revenue_account_id:
        missing.append('revenue_account')
    if not merchant.offset_coa_account_id:
        missing.append('offset_coa_account')
    if not merchant.sub_transaction_type_id:
        missing.append('sub_transaction_type')
    if missing:
        raise ValueError(
            f'MerchantPOSConfig for order {order.order_number} missing: {", ".join(missing)}. '
            f'Configure these in POS → Merchant Settings → Pengaturan Akuntansi.'
        )


def _get_payment_account(order, merchant):
    confirmed = order.payments.filter(is_confirmed=True).select_related(
        'payment_method__payment_account'
    ).first()
    if confirmed and confirmed.payment_method.payment_account_id:
        return confirmed.payment_method.payment_account
    return merchant.default_payment_account
