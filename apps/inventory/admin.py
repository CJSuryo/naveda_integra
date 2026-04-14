"""Inventory admin."""
from django.contrib import admin
from .models import MutasiInventoryHeader, MutasiInventoryDetail, InventoryRecord


class MutasiInventoryDetailInline(admin.TabularInline):
    model = MutasiInventoryDetail
    extra = 0


@admin.register(MutasiInventoryHeader)
class MutasiInventoryHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'entitas_bisnis', 'dll')
    list_select_related = ('entitas_bisnis',)
    raw_id_fields = ('entitas_bisnis',)
    inlines = (MutasiInventoryDetailInline,)


@admin.register(MutasiInventoryDetail)
class MutasiInventoryDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'mutasi_inventory_header', 'dll')
    list_select_related = ('mutasi_inventory_header',)


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ('inventory_number', 'item', 'entitas_bisnis', 'quantity', 'unit_price', 'total_value', 'tanggal')
    list_select_related = ('item', 'entitas_bisnis')
    list_filter = ('tanggal', 'metode_alokasi')
    search_fields = ('inventory_number', 'item__nama', 'item__item_id')
    raw_id_fields = ('item', 'purchase_item', 'entitas_bisnis')
