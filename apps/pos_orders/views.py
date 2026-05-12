import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings

from django.contrib import messages

from apps.accounts.views import _check_perm
from pos_config.models import StorePOSConfig, PaymentMethod, WebPushSubscription
from pos_catalog.services.product_service import validate_modifier_selections
from pos_orders.models import Order, OrderItem, OrderPayment, Refund
from pos_orders.services.order_service import (
    create_order, add_item, remove_item, update_item_quantity,
    submit_order, process_payment, confirm_payment, complete_order, cancel_order,
    transition_status,
)


def _json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse({'error': 'Invalid JSON'}, status=400)


# ─── Push Notification Endpoints ─────────────────────────────────────────────

@require_GET
def vapid_public_key(request):
    return JsonResponse({'public_key': getattr(settings, 'VAPID_PUBLIC_KEY', '')})


@login_required
@require_POST
def push_subscribe(request, store_id):
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    data, err = _json_body(request)
    if err:
        return err
    WebPushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=data['endpoint'],
        defaults={
            'store': store,
            'p256dh_key': data['p256dh'],
            'auth_key': data['auth'],
            'role': data.get('role', WebPushSubscription.ROLE_CASHIER),
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:300],
            'is_active': True,
        }
    )
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def push_unsubscribe(request):
    data, err = _json_body(request)
    if err:
        return err
    WebPushSubscription.objects.filter(
        user=request.user, endpoint=data.get('endpoint', '')
    ).update(is_active=False)
    return JsonResponse({'status': 'ok'})


# ─── Cashier + Queue Screen Views ────────────────────────────────────────────

@login_required
def cashier(request, store_id):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    from apps.purchase.models import ItemMasterPurchase
    products = ItemMasterPurchase.objects.all().order_by('nama')
    categories = store.merchant_config.categories.filter(is_active=True).order_by('display_order')
    active_orders = Order.objects.filter(
        store=store,
        status__in=[Order.STATUS_OPEN, Order.STATUS_IN_QUEUE, Order.STATUS_PREPARING, Order.STATUS_READY]
    ).order_by('-created_at')[:20]
    payment_methods = store.merchant_config.payment_methods.filter(is_active=True).order_by('display_order')
    return render(request, 'pos_orders/cashier.html', {
        'store': store,
        'products': products,
        'categories': categories,
        'active_orders': active_orders,
        'payment_methods': payment_methods,
    })


@login_required
def queue(request, store_id):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    pending = Order.objects.filter(store=store, status=Order.STATUS_OPEN).order_by('created_at')
    preparing = Order.objects.filter(
        store=store, status__in=[Order.STATUS_IN_QUEUE, Order.STATUS_PREPARING]
    ).order_by('created_at')
    ready = Order.objects.filter(store=store, status=Order.STATUS_READY).order_by('created_at')
    return render(request, 'pos_orders/queue.html', {
        'store': store, 'pending': pending, 'preparing': preparing, 'ready': ready,
    })


@login_required
def order_list(request):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    orders = Order.objects.select_related('store', 'cashier').order_by('-created_at')[:100]
    return render(request, 'pos_orders/order_list.html', {'orders': orders})


@login_required
def order_detail(request, pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'pos_orders/order_detail.html', {'order': order})


@login_required
def shift_open(request, store_id):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    from pos_config.models import WorkShift, ShiftLog
    from django.utils import timezone
    from django.contrib import messages
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    shifts = store.shifts.filter(is_active=True)
    if request.method == 'POST':
        shift_id = request.POST.get('shift')
        opening_cash = Decimal(request.POST.get('opening_cash', '0'))
        shift = get_object_or_404(WorkShift, pk=shift_id, store=store)
        ShiftLog.objects.create(
            store=store, shift=shift, employee=request.user,
            clock_in=timezone.now(), opening_cash=opening_cash,
        )
        messages.success(request, f'Shift {shift.name} dibuka.')
        return redirect('pos_orders:cashier', store_id=store_id)
    return render(request, 'pos_orders/shift_open.html', {'store': store, 'shifts': shifts})


@login_required
def shift_close(request, store_id):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    from pos_config.models import ShiftLog
    from django.utils import timezone
    from django.contrib import messages
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    log = ShiftLog.objects.filter(store=store, clock_out__isnull=True).order_by('-clock_in').first()
    if request.method == 'POST' and log:
        log.closing_cash = Decimal(request.POST.get('closing_cash', '0'))
        log.notes = request.POST.get('notes', '')
        log.clock_out = timezone.now()
        log.save()
        try:
            from pos_reports.services.report_service import generate_daily_snapshot
            import datetime
            generate_daily_snapshot(store, datetime.date.today())
        except ImportError:
            pass
        messages.success(request, 'Shift ditutup.')
        return redirect('pos_orders:cashier', store_id=store_id)
    return render(request, 'pos_orders/shift_close.html', {'store': store, 'active_log': log})


# ─── AJAX Order API Views ─────────────────────────────────────────────────────

@login_required
@require_POST
def api_create_order(request):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    data, err = _json_body(request)
    if err:
        return err
    store = get_object_or_404(StorePOSConfig, pk=data['store_id'])
    order = create_order(
        store, request.user,
        data.get('order_type', Order.ORDER_TYPE_DINE_IN),
        data.get('source', Order.SOURCE_POS),
        table_number=data.get('table_number', ''),
        customer_name=data.get('customer_name', ''),
    )
    return JsonResponse({'order_id': order.pk, 'status': order.status})


@login_required
@require_POST
def api_add_item(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk, cashier=request.user)
    data, err = _json_body(request)
    if err:
        return err
    from apps.purchase.models import ItemMasterPurchase
    product = get_object_or_404(ItemMasterPurchase, pk=data['product_id'])
    errors = validate_modifier_selections(product, data.get('modifier_option_ids', []))
    if errors:
        return JsonResponse({'errors': errors}, status=400)
    item = add_item(
        order, product, Decimal(str(data['quantity'])),
        data.get('modifier_option_ids', []), data.get('notes', '')
    )
    order.refresh_from_db()
    return JsonResponse({'item_id': item.pk, 'subtotal': str(item.subtotal), 'order_total': str(order.total_amount)})


@login_required
@require_POST
def api_remove_item(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    item = get_object_or_404(OrderItem, pk=pk, order__cashier=request.user)
    order = item.order
    remove_item(item)
    order.refresh_from_db()
    return JsonResponse({'order_total': str(order.total_amount)})


@login_required
@require_POST
def api_update_qty(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    item = get_object_or_404(OrderItem, pk=pk, order__cashier=request.user)
    data, err = _json_body(request)
    if err:
        return err
    item = update_item_quantity(item, Decimal(str(data['quantity'])))
    return JsonResponse({'subtotal': str(item.subtotal), 'order_total': str(item.order.total_amount)})


@login_required
@require_POST
def api_submit_order(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk, cashier=request.user)
    order = submit_order(order)
    return JsonResponse({'order_number': order.order_number, 'status': order.status})


@login_required
@require_POST
def api_process_payment(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    data, err = _json_body(request)
    if err:
        return err
    method = get_object_or_404(PaymentMethod, pk=data['payment_method_id'])
    op = process_payment(order, method, Decimal(str(data['amount'])), data.get('reference_number', ''))
    return JsonResponse({'payment_id': op.pk, 'is_confirmed': op.is_confirmed, 'is_fully_paid': order.is_fully_paid()})


@login_required
@require_POST
def api_confirm_payment(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    data, err = _json_body(request)
    if err:
        return err
    payment_id = data.get('payment_id')
    op = get_object_or_404(OrderPayment, pk=payment_id, order=order)
    is_paid = confirm_payment(op, request.user)
    return JsonResponse({'is_confirmed': True, 'is_fully_paid': is_paid})


@login_required
@require_POST
def api_confirm_single_payment(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    op = get_object_or_404(OrderPayment, pk=pk)
    is_paid = confirm_payment(op, request.user)
    return JsonResponse({'is_confirmed': True, 'is_fully_paid': is_paid})


@login_required
@require_POST
def api_complete_order(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    try:
        order = complete_order(order)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'status': order.status, 'order_number': order.order_number})


@login_required
@require_POST
def api_cancel_order(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    data, err = _json_body(request)
    if err:
        return err
    try:
        order = cancel_order(order, data.get('reason', ''), request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'status': order.status})


@login_required
@require_POST
def api_transition_order(request, pk):
    denied = _check_perm(request.user, 'pos_cashier')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=pk)
    data, err = _json_body(request)
    if err:
        return err
    try:
        order = transition_status(order, data['status'], request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'status': order.status})


# ─── Refund Views ─────────────────────────────────────────────────────────────

@login_required
def refund_initiate(request, order_pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    from pos_orders.services.refund_service import initiate_refund
    order = get_object_or_404(Order, pk=order_pk)
    if order.status != Order.STATUS_COMPLETED:
        messages.error(request, 'Hanya order COMPLETED yang bisa direfund.')
        return redirect('pos_orders:order_detail', pk=order_pk)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        refund_type = request.POST.get('refund_type', Refund.REFUND_FULL)
        refund_method_id = request.POST.get('refund_method_id')
        if not reason:
            messages.error(request, 'Alasan refund wajib diisi.')
            return redirect('pos_orders:refund_initiate', order_pk=order_pk)
        pm = get_object_or_404(PaymentMethod, pk=refund_method_id)
        try:
            refund = initiate_refund(
                order=order, by_user=request.user, reason=reason,
                refund_type=refund_type, refund_method=pm,
            )
            messages.success(request, f'Refund #{refund.pk} berhasil diajukan.')
            return redirect('pos_orders:refund_detail', order_pk=order_pk, refund_pk=refund.pk)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('pos_orders:refund_initiate', order_pk=order_pk)
    payment_methods = order.store.merchant_config.payment_methods.filter(is_active=True)
    return render(request, 'pos_orders/refund_initiate.html', {
        'order': order, 'payment_methods': payment_methods,
    })


@login_required
def refund_detail(request, order_pk, refund_pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    order = get_object_or_404(Order, pk=order_pk)
    refund = get_object_or_404(Refund, pk=refund_pk, order=order)
    return render(request, 'pos_orders/refund_detail.html', {'order': order, 'refund': refund})


@login_required
@require_POST
def refund_approve(request, order_pk, refund_pk):
    denied = _check_perm(request.user, 'pos_refund_approve')
    if denied:
        return denied
    from pos_orders.services.refund_service import approve_refund
    order = get_object_or_404(Order, pk=order_pk)
    refund = get_object_or_404(Refund, pk=refund_pk, order=order)
    try:
        approve_refund(refund, approved_by=request.user)
        messages.success(request, 'Refund disetujui.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('pos_orders:refund_detail', order_pk=order_pk, refund_pk=refund_pk)


@login_required
@require_POST
def refund_complete(request, order_pk, refund_pk):
    denied = _check_perm(request.user, 'pos_refund_approve')
    if denied:
        return denied
    from pos_orders.services.refund_service import complete_refund
    order = get_object_or_404(Order, pk=order_pk)
    refund = get_object_or_404(Refund, pk=refund_pk, order=order)
    try:
        complete_refund(refund)
        messages.success(request, 'Refund selesai. Stok dan jurnal sudah dikembalikan.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('pos_orders:refund_detail', order_pk=order_pk, refund_pk=refund_pk)


@login_required
def refund_list(request):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    store_id = request.GET.get('store')
    refunds = Refund.objects.select_related(
        'order__store', 'initiated_by', 'approved_by'
    ).order_by('-id')
    if store_id:
        refunds = refunds.filter(order__store_id=store_id)
    return render(request, 'pos_orders/refund_list.html', {'refunds': refunds})


@login_required
def receipt_preview(request, order_pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    from pos_orders.services.receipt_service import generate_receipt_text
    order = get_object_or_404(Order, pk=order_pk)
    text = generate_receipt_text(order)
    return render(request, 'pos_orders/receipt_preview.html', {
        'order': order, 'receipt_text': text,
    })


@login_required
@require_POST
def receipt_print(request, order_pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied
    from pos_orders.services.receipt_service import generate_receipt_text, send_to_printer
    order = get_object_or_404(Order, pk=order_pk)
    text = generate_receipt_text(order)
    send_to_printer(order.store, text)
    return JsonResponse({'ok': True})
