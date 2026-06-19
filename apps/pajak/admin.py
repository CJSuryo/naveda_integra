from django.contrib import admin
from .models import TarifPajak, BracketPPhOP, MasaPajak, PajakTransaksi


@admin.register(TarifPajak)
class TarifPajakAdmin(admin.ModelAdmin):
    list_display  = ('jenis_pajak', 'tarif_persen', 'faktor_dpp', 'berlaku_mulai', 'berlaku_sampai')
    list_filter   = ('jenis_pajak',)
    ordering      = ('jenis_pajak', '-berlaku_mulai')


@admin.register(BracketPPhOP)
class BracketPPhOPAdmin(admin.ModelAdmin):
    list_display = ('batas_bawah', 'batas_atas', 'tarif_persen', 'berlaku_mulai')
    ordering     = ('berlaku_mulai', 'batas_bawah')


@admin.register(MasaPajak)
class MasaPajakAdmin(admin.ModelAdmin):
    list_display = ('tahun', 'bulan', 'status')
    list_filter  = ('status',)
    ordering     = ('-tahun', '-bulan')


@admin.register(PajakTransaksi)
class PajakTransaksiAdmin(admin.ModelAdmin):
    list_display    = ('source_type', 'source_id', 'jenis_pajak', 'masa_pajak', 'jumlah_pajak', 'sifat_pajak', 'status', 'is_overridden')
    list_filter     = ('status', 'jenis_pajak', 'sifat_pajak', 'source_type')
    search_fields   = ('source_id',)
    readonly_fields = ('created_at', 'modified_at', 'modified_by')
