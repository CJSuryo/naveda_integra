"""Purchase admin."""
from django.contrib import admin
from .models import (
    KategoriItem, ItemMasterPurchase, SubTransactionType,
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, FIFOBatch,
)


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    raw_id_fields = ('item', 'coa_account', 'offset_coa_account', 'sub_transaction_type')


class PurchaseEntitasBisnisInline(admin.TabularInline):
    model = PurchaseEntitasBisnis
    extra = 0
    raw_id_fields = ('entitas_bisnis',)


@admin.register(KategoriItem)
class KategoriItemAdmin(admin.ModelAdmin):
    list_display = ('nama',)
    search_fields = ('nama',)


@admin.register(ItemMasterPurchase)
class ItemMasterPurchaseAdmin(admin.ModelAdmin):
    list_display = ('item_id', 'nama', 'tipe_item', 'kategori', 'coa_account')
    list_filter = ('tipe_item', 'velocity_category')
    search_fields = ('item_id', 'nama')
    list_select_related = ('kategori', 'coa_account')
    raw_id_fields = ('coa_account',)


@admin.register(SubTransactionType)
class SubTransactionTypeAdmin(admin.ModelAdmin):
    list_display = ('nama', 'direction', 'default_offset_account')
    list_filter = ('direction',)
    search_fields = ('nama',)
    list_select_related = ('default_offset_account',)
    raw_id_fields = ('default_offset_account',)


@admin.register(PurchaseHeader)
class PurchaseHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'deskripsi', 'is_locked')
    list_filter = ('is_locked', 'tanggal')
    search_fields = ('transaction_id', 'deskripsi')
    inlines = (PurchaseEntitasBisnisInline,)


@admin.register(PurchaseEntitasBisnis)
class PurchaseEntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('purchase_header', 'entitas_bisnis')
    list_select_related = ('purchase_header', 'entitas_bisnis')
    raw_id_fields = ('purchase_header', 'entitas_bisnis')
    inlines = (PurchaseItemInline,)


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ('purchase_eb', 'item', 'quantity', 'unit_price', 'total_value')
    list_select_related = ('purchase_eb__purchase_header', 'purchase_eb__entitas_bisnis', 'item')
    raw_id_fields = ('purchase_eb', 'item', 'coa_account', 'offset_coa_account', 'sub_transaction_type')


@admin.register(FIFOBatch)
class FIFOBatchAdmin(admin.ModelAdmin):
    list_display = ('item', 'tanggal', 'quantity_in', 'unit_price', 'remaining_qty', 'batch_value')
    list_filter = ('tanggal',)
    search_fields = ('item__item_id', 'item__nama')
    list_select_related = ('item',)
    raw_id_fields = ('item', 'purchase_item')
