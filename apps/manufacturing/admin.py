"""Manufacturing admin."""
from django.contrib import admin

from .models import BillOfMaterials, BOMLine, ProductionOrder, ProductionRMConsumption


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 0
    fields = ['raw_material', 'qty_required']
    autocomplete_fields = []
    show_change_link = True


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ['bom_id', 'finished_good', 'entitas_bisnis', 'tanggal_dibuat']
    list_filter = ['entitas_bisnis', 'tanggal_dibuat']
    search_fields = ['bom_id', 'finished_good__nama', 'finished_good__item_id']
    list_select_related = ['finished_good', 'entitas_bisnis']
    inlines = [BOMLineInline]
    readonly_fields = ['bom_id', 'created_at', 'updated_at']


class ProductionRMConsumptionInline(admin.TabularInline):
    model = ProductionRMConsumption
    extra = 0
    fields = ['bom_line', 'fifo_batch', 'qty_consumed', 'unit_cost', 'total_cost']
    readonly_fields = ['total_cost']
    show_change_link = False


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = [
        'production_id', 'tanggal', 'bom', 'entitas_bisnis',
        'qty_produced', 'status', 'is_processed',
    ]
    list_filter = ['status', 'is_processed', 'entitas_bisnis', 'tanggal']
    search_fields = ['production_id', 'bom__bom_id', 'bom__finished_good__nama']
    list_select_related = ['bom__finished_good', 'entitas_bisnis']
    readonly_fields = [
        'production_id', 'rm_cost', 'total_cost', 'unit_cost',
        'is_processed', 'created_at', 'updated_at',
    ]
    inlines = [ProductionRMConsumptionInline]
    raw_id_fields = ['bom', 'coa_produksi', 'coa_overhead_applied']
