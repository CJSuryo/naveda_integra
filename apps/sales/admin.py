"""Sales admin."""
from django.contrib import admin
from .models import SalesHeader, SalesEntitasBisnis, SalesItem


class SalesEntitasBisnisInline(admin.TabularInline):
    model = SalesEntitasBisnis
    extra = 0
    raw_id_fields = ('entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
                     'payment_account')


class SalesItemInline(admin.TabularInline):
    model = SalesItem
    extra = 0
    raw_id_fields = ('item', 'sub_transaction_type', 'offset_coa_account',
                     'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')


@admin.register(SalesHeader)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'is_locked')
    list_filter = ('is_locked', 'tanggal')
    search_fields = ('transaction_id',)
    inlines = (SalesEntitasBisnisInline,)


@admin.register(SalesEntitasBisnis)
class SalesEntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                    'entitas_bisnis_lv3', 'payment_account')
    list_filter = ('entitas_bisnis',)
    search_fields = ('sales_header__transaction_id',)
    list_select_related = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                           'entitas_bisnis_lv3', 'payment_account')
    raw_id_fields = ('sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                     'entitas_bisnis_lv3', 'payment_account')
    inlines = (SalesItemInline,)


@admin.register(SalesItem)
class SalesItemAdmin(admin.ModelAdmin):
    list_display = ('sales_eb', 'item', 'quantity', 'selling_price', 'total_sales', 'cogs_amount')
    list_select_related = ('sales_eb', 'item')
    raw_id_fields = ('sales_eb', 'item', 'sub_transaction_type',
                     'offset_coa_account', 'revenue_account', 'inventory_account',
                     'tax_account', 'tax_payment_account')
