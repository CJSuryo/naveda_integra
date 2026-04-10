"""Inventory admin."""
from django.contrib import admin
from .models import MutasiInventoryHeader, MutasiInventoryDetail


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
