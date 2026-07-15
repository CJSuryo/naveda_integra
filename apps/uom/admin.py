from django.contrib import admin

from .models import UnitOfMeasure, ItemUOM


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'dimension', 'factor_to_base',
                    'is_base', 'is_system', 'is_active')
    list_filter = ('dimension', 'is_base', 'is_system', 'is_active')
    search_fields = ('kode', 'nama')

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ItemUOM)
class ItemUOMAdmin(admin.ModelAdmin):
    list_display = ('item', 'uom', 'qty_in_stock_uom')
    search_fields = ('item__nama', 'uom__kode')
    autocomplete_fields = ('item', 'uom')
