"""Jurnal admin."""
from django.contrib import admin
from .models import JurnalHeader, JurnalDetail


class JurnalDetailInline(admin.TabularInline):
    model = JurnalDetail
    extra = 0
    raw_id_fields = ('akun',)


@admin.register(JurnalHeader)
class JurnalHeaderAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'uraian_transaksi', 'tipe_transaksi', 'entitas_bisnis')
    list_filter = ('tipe_transaksi', 'tanggal')
    search_fields = ('uraian_transaksi',)
    list_select_related = ('tipe_transaksi', 'entitas_bisnis')
    raw_id_fields = ('entitas_bisnis', 'no_bukti', 'item')
    inlines = (JurnalDetailInline,)


@admin.register(JurnalDetail)
class JurnalDetailAdmin(admin.ModelAdmin):
    list_display = ('jurnal_header', 'akun', 'debit', 'kredit')
    list_select_related = ('jurnal_header', 'akun')
    raw_id_fields = ('jurnal_header', 'akun')
