from django.contrib import admin
from .models import Order, OrderItem, OrderPayment, Refund


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'store', 'status', 'source', 'total_amount', 'created_at']
    list_filter = ['status', 'source', 'order_type']
    search_fields = ['order_number', 'customer_name']


admin.site.register(OrderItem)
admin.site.register(OrderPayment)
admin.site.register(Refund)
