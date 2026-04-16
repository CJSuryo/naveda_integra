"""Aset Lainnya admin."""
from django.contrib import admin
from .models import AsetLainnyaRecord


@admin.register(AsetLainnyaRecord)
class AsetLainnyaRecordAdmin(admin.ModelAdmin):
    list_display = (
        'aset_number', 'item', 'entitas_bisnis',
        'quantity', 'harga_perolehan', 'total_value',
        'akumulasi_amortisasi', 'tanggal_perolehan',
    )
    list_select_related = ('item', 'entitas_bisnis')
    list_filter = ('tanggal_perolehan', 'metode_amortisasi')
    search_fields = ('aset_number', 'item__nama', 'item__item_id')
    raw_id_fields = ('item', 'purchase_item', 'entitas_bisnis')
