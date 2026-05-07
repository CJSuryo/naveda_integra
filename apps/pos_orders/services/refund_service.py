from decimal import Decimal
from django.db import transaction

from pos_orders.models import Order, Refund, RefundItem
from pos_orders.services.sales_integration import reverse_sales_for_refund


def initiate_refund(
    order: Order,
    by_user,
    reason: str,
    refund_type: str,
    refund_method,
    items: list | None = None,
) -> Refund:
    """Create a Refund in PENDING status.

    items: list of {order_item_id, quantity, amount} for partial refunds.
    Pass None or empty list for full refund — amount computed automatically.
    """
    if order.status != Order.STATUS_COMPLETED:
        raise ValueError(
            f'Order {order.order_number} must be COMPLETED to initiate refund, '
            f'got {order.status}'
        )

    with transaction.atomic():
        if refund_type == Refund.REFUND_FULL or not items:
            amount = order.total_amount
        else:
            amount = sum(Decimal(str(i['amount'])) for i in items)

        refund = Refund.objects.create(
            order=order,
            initiated_by=by_user,
            reason=reason,
            refund_type=refund_type,
            amount=amount,
            refund_method=refund_method,
            status=Refund.REFUND_STATUS_PENDING,
        )

        if refund_type == Refund.REFUND_PARTIAL and items:
            from pos_orders.models import OrderItem
            for item_data in items:
                order_item = OrderItem.objects.get(
                    pk=item_data['order_item_id'], order=order
                )
                RefundItem.objects.create(
                    refund=refund,
                    order_item=order_item,
                    quantity=Decimal(str(item_data['quantity'])),
                    amount=Decimal(str(item_data['amount'])),
                )

    try:
        from pos_orders.services.push_service import send_push_to_store
        from pos_config.models import WebPushSubscription
        send_push_to_store(
            store_id=order.store_id,
            role=WebPushSubscription.ROLE_MANAGER,
            title='Permintaan Refund',
            body=f'Order {order.order_number} — {reason[:60]}',
            data={'url': f'/pos/orders/{order.pk}/refund/'},
        )
    except Exception:
        pass

    return refund


def approve_refund(refund: Refund, approved_by) -> Refund:
    if refund.status != Refund.REFUND_STATUS_PENDING:
        raise ValueError(f'Refund {refund.pk} is not PENDING — cannot approve')
    refund.status = Refund.REFUND_STATUS_APPROVED
    refund.approved_by = approved_by
    refund.save(update_fields=['status', 'approved_by'])
    return refund


def complete_refund(refund: Refund) -> Refund:
    """Reverse FIFO + journals and mark order REFUNDED.

    Must be called only after approve_refund().
    """
    if refund.status != Refund.REFUND_STATUS_APPROVED:
        raise ValueError(f'Refund {refund.pk} must be APPROVED before completing')
    with transaction.atomic():
        reverse_sales_for_refund(refund)
        refund.status = Refund.REFUND_STATUS_COMPLETED
        refund.save(update_fields=['status'])

        try:
            from pos_crm.services.member_service import deduct_points_for_refund
            order = refund.order
            if getattr(order, 'member_id', None):
                deduct_points_for_refund(order.member, order)
        except ImportError:
            pass

    return refund
