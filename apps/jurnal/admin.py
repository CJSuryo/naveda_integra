"""Jurnal admin."""
from django.contrib import admin
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)


class JurnalDetailInline(admin.TabularInline):
    model = JurnalDetail
    extra = 0
    raw_id_fields = ('akun',)


class JurnalAutomasiAkunInline(admin.TabularInline):
    model = JurnalAutomasiAkun
    extra = 0
    raw_id_fields = ('akun',)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')


@admin.register(TransactionPrefix)
class TransactionPrefixAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')


@admin.register(JurnalHeader)
class JurnalHeaderAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'nomor_transaksi', 'uraian_transaksi', 'tipe_transaksi', 'entitas_bisnis')
    list_filter = ('tipe_transaksi', 'tanggal')
    search_fields = ('uraian_transaksi', 'nomor_transaksi')
    list_select_related = ('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix')
    raw_id_fields = ('entitas_bisnis', 'no_bukti', 'item', 'transaction_prefix')
    inlines = (JurnalDetailInline,)


@admin.register(JurnalDetail)
class JurnalDetailAdmin(admin.ModelAdmin):
    list_display = ('jurnal_header', 'akun', 'debit', 'kredit')
    list_select_related = ('jurnal_header', 'akun')
    raw_id_fields = ('jurnal_header', 'akun')


@admin.register(JurnalAutomasi)
class JurnalAutomasiAdmin(admin.ModelAdmin):
    list_display = ('nama',)
    search_fields = ('nama',)
    inlines = (JurnalAutomasiAkunInline,)


@admin.register(JurnalAutomasiAkun)
class JurnalAutomasiAkunAdmin(admin.ModelAdmin):
    list_display = ('automasi', 'akun')
    list_select_related = ('automasi', 'akun')
    raw_id_fields = ('automasi', 'akun')
