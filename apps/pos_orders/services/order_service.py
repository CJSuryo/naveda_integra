from decimal import Decimal
from typing import List, Optional
from django.utils import timezone
from pos_config.models import StorePOSConfig, PaymentMethod, ShiftLog
from pos_catalog.models import POSProduct, ModifierOption
from pos_orders.models import Order, OrderItem, OrderItemModifier, OrderPayment
from pos_orders.services.order_number import generate_order_number


def create_order(
    store: StorePOSConfig,
    cashier,
    order_type: str,
    source: str = Order.SOURCE_POS,
    shift_log: Optional[ShiftLog] = None,
    table_number: str = '',
    customer_name: str = '',
) -> Order:
    return Order.objects.create(
        store=store,
        cashier=cashier,
        order_type=order_type,
        source=source,
        shift_log=shift_log,
        table_number=table_number,
        customer_name=customer_name,
        order_number=None,
        status=Order.STATUS_DRAFT,
    )


def add_item(
    order: Order,
    product: POSProduct,
    quantity: Decimal,
    selected_modifier_option_ids: List[int],
    notes: str = '',
) -> OrderItem:
    try:
        override = product.store_availability.get(store=order.store)
        unit_price = override.selling_price_override or product.selling_price
    except Exception:
        unit_price = product.selling_price

    modifier_total = Decimal('0')
    options = []
    if selected_modifier_option_ids:
        options = list(
            ModifierOption.objects.filter(pk__in=selected_modifier_option_ids).select_related('group')
        )
        modifier_total = sum(opt.additional_price for opt in options)

    subtotal = (unit_price + modifier_total) * quantity

    item = OrderItem.objects.create(
        order=order,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        modifier_total=modifier_total,
        subtotal=subtotal,
        notes=notes,
        status=OrderItem.ITEM_STATUS_PENDING,
    )

    for opt in options:
        OrderItemModifier.objects.create(
            order_item=item,
            modifier_option=opt,
            option_name_snapshot=opt.name,
            group_name_snapshot=opt.group.name,
            price_snapshot=opt.additional_price,
        )

    order.recalculate_totals()
    return item


def remove_item(order_item: OrderItem) -> None:
    order = order_item.order
    order_item.delete()
    order.recalculate_totals()


def update_item_quantity(order_item: OrderItem, new_qty: Decimal) -> OrderItem:
    modifier_total = order_item.modifier_total
    order_item.quantity = new_qty
    order_item.subtotal = (order_item.unit_price + modifier_total) * new_qty
    order_item.save(update_fields=['quantity', 'subtotal'])
    order_item.order.recalculate_totals()
    return order_item


def submit_order(order: Order) -> Order:
    if not order.can_transition_to(Order.STATUS_OPEN):
        raise ValueError(f'Cannot submit order with status {order.status}')
    order.order_number = generate_order_number(order.store)
    order.status = Order.STATUS_OPEN
    order.save(update_fields=['order_number', 'status', 'updated_at'])
    _broadcast_order_event(order, 'order.new')
    _push_new_order(order)
    return order


def transition_status(order: Order, new_status: str, by_user) -> Order:
    if not order.can_transition_to(new_status):
        raise ValueError(f'Invalid transition: {order.status} → {new_status}')
    order.status = new_status
    if new_status == Order.STATUS_COMPLETED:
        order.completed_at = timezone.now()
    order.save(update_fields=['status', 'completed_at', 'updated_at'])
    _broadcast_order_event(order, 'order.status')
    if new_status == Order.STATUS_READY:
        _push_order_ready(order)
    return order


def process_payment(
    order: Order,
    payment_method: PaymentMethod,
    amount: Decimal,
    reference_number: str = '',
) -> OrderPayment:
    auto_confirm = payment_method.method_type == PaymentMethod.CASH
    op = OrderPayment.objects.create(
        order=order,
        payment_method=payment_method,
        amount=amount,
        reference_number=reference_number,
        is_confirmed=auto_confirm,
    )
    return op


def confirm_payment(order_payment: OrderPayment, confirmed_by) -> bool:
    order_payment.is_confirmed = True
    order_payment.confirmed_at = timezone.now()
    order_payment.confirmed_by = confirmed_by
    order_payment.save(update_fields=['is_confirmed', 'confirmed_at', 'confirmed_by'])
    order = order_payment.order
    _broadcast_order_event(order, 'order.payment_confirmed')
    _push_payment_confirmed(order)
    return order.is_fully_paid()


def complete_order(order: Order) -> Order:
    if not order.is_fully_paid():
        raise ValueError('Cannot complete unpaid order')
    if not order.can_transition_to(Order.STATUS_COMPLETED):
        raise ValueError(f'Cannot complete order with status {order.status}')

    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        order.status = Order.STATUS_COMPLETED
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at', 'updated_at'])

        from pos_orders.services.sales_integration import create_sales_from_order
        create_sales_from_order(order)

        try:
            if getattr(order, 'member_id', None):
                from pos_crm.services.member_service import add_points
                add_points(order.member, order)
        except ImportError:
            pass

    _broadcast_order_event(order, 'order.completed')
    return order


def cancel_order(order: Order, reason: str, by_user) -> Order:
    if not order.can_transition_to(Order.STATUS_CANCELLED):
        raise ValueError(f'Cannot cancel order with status {order.status}')
    order.status = Order.STATUS_CANCELLED
    order.notes = f'{order.notes}\n[DIBATALKAN oleh {by_user.name}: {reason}]'.strip()
    order.save(update_fields=['status', 'notes', 'updated_at'])
    _broadcast_order_event(order, 'order.cancelled')
    return order


def close_shift(shift_log: ShiftLog) -> ShiftLog:
    """Mark a shift as closed and trigger daily snapshot generation."""
    shift_log.clock_out = timezone.now()
    shift_log.save(update_fields=['clock_out'])
    try:
        from apps.pos_reports.services.report_service import generate_daily_snapshot
        generate_daily_snapshot(shift_log.store, timezone.localdate(), shift_log=shift_log)
    except ImportError:
        pass
    return shift_log


def _broadcast_order_event(order: Order, event_type: str) -> None:
    try:
        from asgiref.sync import async_to_sync
        from pos_orders.events import broadcast
        store_id = order.store_id
        data = {
            'order_number': order.order_number,
            'status': order.status,
            'source': order.source,
            'table': order.table_number,
            'total': str(order.total_amount),
        }
        async_to_sync(broadcast)(store_id, 'cashier', event_type, data)
        async_to_sync(broadcast)(store_id, 'kitchen', event_type, data)
    except Exception:
        pass


def _push_new_order(order: Order) -> None:
    try:
        from pos_orders.services.push_service import send_push_to_store
        from pos_config.models import WebPushSubscription
        title = f'Pesanan Baru — {order.order_number}'
        items_preview = ', '.join(
            f'{i.product.pos_name} x{int(i.quantity)}'
            for i in order.items.all()[:3]
        )
        body = f'{order.get_source_display()} · {items_preview}'
        url = f'/pos/cashier/{order.store_id}/'
        send_push_to_store(order.store_id, WebPushSubscription.ROLE_CASHIER, title, body, {'url': url, 'order_number': order.order_number})
        send_push_to_store(order.store_id, WebPushSubscription.ROLE_KITCHEN, title, body, {'url': f'/pos/queue/{order.store_id}/', 'order_number': order.order_number})
    except Exception:
        pass


def _push_order_ready(order: Order) -> None:
    try:
        from pos_orders.services.push_service import send_push_to_store
        from pos_config.models import WebPushSubscription
        send_push_to_store(
            order.store_id, WebPushSubscription.ROLE_CASHIER,
            f'Pesanan Siap — {order.order_number}',
            f'Meja {order.table_number or "—"} siap diambil',
            {'url': f'/pos/cashier/{order.store_id}/', 'order_number': order.order_number},
        )
    except Exception:
        pass


def _push_payment_confirmed(order: Order) -> None:
    try:
        from pos_orders.services.push_service import send_push_to_store
        from pos_config.models import WebPushSubscription
        send_push_to_store(
            order.store_id, WebPushSubscription.ROLE_CASHIER,
            f'Pembayaran Dikonfirmasi — {order.order_number}',
            f'Total: Rp {order.total_amount:,.0f}',
            {'url': f'/pos/cashier/{order.store_id}/', 'order_number': order.order_number},
        )
    except Exception:
        pass
