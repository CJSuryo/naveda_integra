"""Manufacturing admin."""
from django import forms
from django.contrib import admin

from .forms import BULK_TIPE_ITEM
from .models import (
    BillOfMaterials, BOMLine, ProductionOrder, ProductionRMConsumption,
    OverheadCategory, OverheadRate, OverheadApplied, PeriodClosing,
)


class BOMLineAdminForm(forms.ModelForm):
    """Blocks bulk items (RMB/FGB/ITMB) as raw_material — they have no
    defined qty_required semantics for BOM consumption. See BULK_TIPE_ITEM
    in apps.manufacturing.forms for the underlying financial-corruption risk.
    """

    class Meta:
        model = BOMLine
        fields = '__all__'

    def clean_raw_material(self):
        raw_material = self.cleaned_data.get('raw_material')
        if raw_material is not None and raw_material.tipe_item in BULK_TIPE_ITEM:
            raise forms.ValidationError(
                'Item bulk (RMB/FGB/ITMB) belum didukung sebagai bahan baku BOM.'
            )
        return raw_material


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    form = BOMLineAdminForm
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


class OverheadAppliedInline(admin.TabularInline):
    model = OverheadApplied
    extra = 0
    fields = ['overhead_category', 'periode_bulan', 'driver_value', 'rate_per_driver', 'amount_applied']
    readonly_fields = ['amount_applied']


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = [
        'production_id', 'tanggal', 'bom', 'entitas_bisnis',
        'qty_produced', 'overhead_cost', 'status', 'is_processed',
    ]
    list_filter = ['status', 'is_processed', 'entitas_bisnis', 'tanggal']
    search_fields = ['production_id', 'bom__bom_id', 'bom__finished_good__nama']
    list_select_related = ['bom__finished_good', 'entitas_bisnis']
    readonly_fields = [
        'production_id', 'rm_cost', 'overhead_cost', 'total_cost', 'unit_cost',
        'is_processed', 'created_at', 'updated_at',
    ]
    inlines = [ProductionRMConsumptionInline, OverheadAppliedInline]
    raw_id_fields = ['bom', 'coa_produksi']


@admin.register(OverheadCategory)
class OverheadCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'overhead_type', 'cost_driver', 'coa_expense', 'coa_overhead_applied', 'is_active']
    list_filter = ['overhead_type', 'is_active']
    search_fields = ['name']
    list_select_related = ['coa_expense', 'coa_overhead_applied']


class OverheadRateInline(admin.TabularInline):
    model = OverheadRate
    extra = 0
    fields = ['periode_bulan', 'estimasi_total', 'estimasi_volume', 'rate_per_driver', 'aktual_total']
    readonly_fields = ['rate_per_driver']


@admin.register(OverheadRate)
class OverheadRateAdmin(admin.ModelAdmin):
    list_display = ['overhead_category', 'periode_bulan', 'estimasi_total', 'estimasi_volume', 'rate_per_driver', 'aktual_total']
    list_filter = ['periode_bulan', 'overhead_category__overhead_type']
    search_fields = ['overhead_category__name', 'periode_bulan']
    list_select_related = ['overhead_category']
    readonly_fields = ['rate_per_driver', 'created_at', 'updated_at']


@admin.register(OverheadApplied)
class OverheadAppliedAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'overhead_category', 'periode_bulan', 'driver_value', 'rate_per_driver', 'amount_applied']
    list_filter = ['periode_bulan', 'overhead_category']
    search_fields = ['production_order__production_id', 'overhead_category__name']
    list_select_related = ['production_order', 'overhead_category']
    readonly_fields = ['amount_applied']


@admin.register(PeriodClosing)
class PeriodClosingAdmin(admin.ModelAdmin):
    list_display = ['periode_bulan', 'closed_at', 'closed_by', 'coa_cogs']
    list_filter = ['closed_at', 'closed_by']
    search_fields = ['periode_bulan', 'closed_by__email']
    list_select_related = ['closed_by', 'coa_cogs']
    readonly_fields = ['closed_at']

