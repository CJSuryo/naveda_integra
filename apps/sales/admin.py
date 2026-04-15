"""Sales admin."""
from django.contrib import admin
from .models import SalesHeader, SalesItem


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    raw_id_fields = ('item', 'sub_transaction_type', 'offset_coa_account',
                     'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')


@admin.register(SalesHeader)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'entitas_bisnis', 'tanggal', 'payment_account', 'is_locked')
    list_filter = ('is_locked', 'tanggal')
    search_fields = ('transaction_id',)
    list_select_related = ('entitas_bisnis', 'payment_account')
    raw_id_fields = ('entitas_bisnis', 'payment_account')
    inlines = (SalesItemInline,)


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = ('sales_header', 'item', 'quantity', 'selling_price', 'total_sales', 'cogs_amount')
    list_select_related = ('sales_header', 'item')
    raw_id_fields = ('sales_header', 'item', 'sub_transaction_type',
                     'offset_coa_account', 'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')
