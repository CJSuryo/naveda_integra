"""Jurnal admin."""
from django.contrib import admin
from .models import JurnalHeader, JurnalDetail


class JurnalDetailInline(admin.TabularInline):
    model = JurnalDetail
    extra = 0


@admin.register(JurnalHeader)
class JurnalHeaderAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'uraian_transaksi', 'tipe_transaksi', 'entitas_bisnis')
    list_filter = ('tipe_transaksi', 'tanggal')
    search_fields = ('uraian_transaksi',)
    inlines = (JurnalDetailInline,)


@admin.register(JurnalDetail)
class JurnalDetailAdmin(admin.ModelAdmin):
    list_display = ('jurnal_header', 'akun', 'debit', 'kredit')
