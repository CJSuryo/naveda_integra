from django.urls import path
from . import views

app_name = 'pos_orders'

urlpatterns = [
    # Push notification endpoints
    path('push/vapid-key/', views.vapid_public_key, name='vapid_key'),
    path('push/subscribe/<int:store_id>/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),

    # Cashier and queue screens
    path('cashier/<int:store_id>/', views.cashier, name='cashier'),
    path('queue/<int:store_id>/', views.queue, name='queue'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('shifts/<int:store_id>/open/', views.shift_open, name='shift_open'),
    path('shifts/<int:store_id>/close/', views.shift_close, name='shift_close'),

    # Refund management
    path('orders/<int:order_pk>/refund/initiate/', views.refund_initiate, name='refund_initiate'),
    path('orders/<int:order_pk>/refund/<int:refund_pk>/', views.refund_detail, name='refund_detail'),
    path('orders/<int:order_pk>/refund/<int:refund_pk>/approve/', views.refund_approve, name='refund_approve'),
    path('orders/<int:order_pk>/refund/<int:refund_pk>/complete/', views.refund_complete, name='refund_complete'),
    path('refunds/', views.refund_list, name='refund_list'),

    # Receipt
    path('orders/<int:order_pk>/receipt/', views.receipt_preview, name='receipt_preview'),
    path('orders/<int:order_pk>/print/', views.receipt_print, name='receipt_print'),

    # AJAX order management
    path('api/orders/create/', views.api_create_order, name='api_create_order'),
    path('api/orders/<int:pk>/add-item/', views.api_add_item, name='api_add_item'),
    path('api/orders/<int:pk>/remove-item/', views.api_remove_item, name='api_remove_item'),
    path('api/orders/<int:pk>/update-qty/', views.api_update_qty, name='api_update_qty'),
    path('api/orders/<int:pk>/submit/', views.api_submit_order, name='api_submit_order'),
    path('api/orders/<int:pk>/pay/', views.api_process_payment, name='api_process_payment'),
    path('api/orders/<int:pk>/confirm-payment/', views.api_confirm_payment, name='api_confirm_payment'),
    path('api/orders/<int:pk>/complete/', views.api_complete_order, name='api_complete_order'),
    path('api/orders/<int:pk>/cancel/', views.api_cancel_order, name='api_cancel_order'),
    path('api/orders/<int:pk>/transition/', views.api_transition_order, name='api_transition_order'),
    path('api/payments/<int:pk>/confirm/', views.api_confirm_single_payment, name='api_confirm_single_payment'),
]
