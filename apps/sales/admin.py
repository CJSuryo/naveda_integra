"""Sales admin."""
from django.contrib import admin
from .models import ItemMaster, SalesHeader, SalesDetail


class SalesDetailInline(admin.TabularInline):
    model = SalesDetail
    extra = 0
    raw_id_fields = ('item_master',)


@admin.register(ItemMaster)
class ItemMasterAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'satuan', 'harga_pokok')
    search_fields = ('kode', 'nama')


@admin.register(SalesHeader)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_invoice', 'entitas_bisnis', 'tanggal_transaksi', 'total_nilai', 'status_pengiriman')
    list_filter = ('status_pengiriman', 'tanggal_transaksi')
    search_fields = ('nomor_invoice',)
    list_select_related = ('entitas_bisnis',)
    raw_id_fields = ('entitas_bisnis',)
    inlines = (SalesDetailInline,)


@admin.register(SalesDetail)
class SalesDetailAdmin(admin.ModelAdmin):
    list_display = ('sales_header', 'item_master', 'kuantitas', 'harga_satuan', 'subtotal')
    list_select_related = ('sales_header', 'item_master')
    raw_id_fields = ('sales_header', 'item_master')
