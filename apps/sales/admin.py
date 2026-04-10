"""Sales admin."""
from django.contrib import admin
from .models import ItemMaster, SalesHeader, SalesDetail


class SalesDetailInline(admin.TabularInline):
    model = SalesDetail
    extra = 0


@admin.register(ItemMaster)
class ItemMasterAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'satuan', 'harga_pokok')
    search_fields = ('kode', 'nama')


@admin.register(SalesHeader)
class SalesHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_invoice', 'entitas_bisnis', 'tanggal_transaksi', 'total_nilai', 'status_pengiriman')
    list_filter = ('status_pengiriman', 'tanggal_transaksi')
    search_fields = ('nomor_invoice',)
    inlines = (SalesDetailInline,)


@admin.register(SalesDetail)
class SalesDetailAdmin(admin.ModelAdmin):
    list_display = ('sales_header', 'item_master', 'kuantitas', 'harga_satuan', 'subtotal')
