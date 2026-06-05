from django.contrib import admin
from .models import ModifierGroup, ModifierOption, ProductModifierGroup, CatalogItem, CatalogItemLog


admin.site.register(ModifierGroup)
admin.site.register(ModifierOption)
admin.site.register(ProductModifierGroup)


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ('item', 'entitas_bisnis', 'selling_price', 'is_active', 'display_order')
    list_select_related = ('item', 'entitas_bisnis')
    list_filter = ('is_active', 'entitas_bisnis')
    search_fields = ('item__nama', 'display_name')
    extra = 0


@admin.register(CatalogItemLog)
class CatalogItemLogAdmin(admin.ModelAdmin):
    list_display = ('catalog_item', 'field_name', 'old_value', 'new_value', 'changed_at', 'changed_by')
    list_select_related = ('catalog_item__item', 'changed_by')
    list_filter = ('field_name',)
    search_fields = ('catalog_item__item__nama',)
    readonly_fields = ('catalog_item', 'field_name', 'old_value', 'new_value', 'changed_at', 'changed_by')
