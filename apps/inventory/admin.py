"""Inventory admin."""
from django.contrib import admin
from .models import MutasiInventoryHeader, MutasiInventoryDetail, InventoryRecord
from apps.inventory.models import StockMovement, StockConsumption


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


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('item', 'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
                    'tanggal', 'movement_type', 'qty', 'unit_cost', 'remaining_qty')
    list_filter = ('movement_type', 'tanggal')
    search_fields = ('item__nama', 'item__item_id')
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(StockConsumption)
class StockConsumptionAdmin(admin.ModelAdmin):
    list_display = ('out_movement', 'in_movement', 'qty', 'unit_cost')

    def has_add_permission(self, request):
        return False
