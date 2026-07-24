"""Aset Tetap admin."""
from django.contrib import admin
from .models import AsetTetapRecord, LokasiAset


@admin.register(AsetTetapRecord)
class AsetTetapRecordAdmin(admin.ModelAdmin):
    list_display = (
        'aset_number', 'item', 'entitas_bisnis',
        'quantity', 'harga_perolehan', 'total_value',
        'akumulasi_penyusutan', 'tanggal_perolehan', 'kondisi',
    )
    list_select_related = ('item', 'entitas_bisnis')
    list_filter = ('tanggal_perolehan', 'kondisi', 'metode_penyusutan')
    search_fields = ('aset_number', 'item__nama', 'item__item_id', 'lokasi_legacy')
    raw_id_fields = ('item', 'purchase_item', 'entitas_bisnis')


@admin.register(LokasiAset)
class LokasiAsetAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'entitas_bisnis', 'is_active')
    list_select_related = ('entitas_bisnis',)
    list_filter = ('is_active', 'entitas_bisnis')
    search_fields = ('kode', 'nama')
