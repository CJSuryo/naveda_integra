from django.contrib import admin

from .models import UtangHeader, UtangDetail, UtangPembayaran, UtangTerhapus


class UtangDetailInline(admin.TabularInline):
    model = UtangDetail
    extra = 0
    raw_id_fields = ('purchase_item', 'coa_utang_account')


class UtangPembayaranInline(admin.TabularInline):
    model = UtangPembayaran
    extra = 0
    raw_id_fields = ('utang_detail', 'coa_account', 'jurnal_header')


@admin.register(UtangHeader)
class UtangHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_utang', 'tanggal', 'entitas_bisnis', 'total_amount', 'status')
    list_filter = ('status', 'tanggal')
    search_fields = ('nomor_utang', 'deskripsi')
    inlines = (UtangDetailInline, UtangPembayaranInline)
    raw_id_fields = ('purchase_header', 'entitas_bisnis')


@admin.register(UtangDetail)
class UtangDetailAdmin(admin.ModelAdmin):
    list_display = ('utang_header', 'coa_utang_account', 'amount', 'description')
    list_select_related = ('utang_header', 'coa_utang_account', 'purchase_item')
    raw_id_fields = ('utang_header', 'purchase_item', 'coa_utang_account')


@admin.register(UtangPembayaran)
class UtangPembayaranAdmin(admin.ModelAdmin):
    list_display = ('utang_header', 'tanggal', 'jumlah', 'coa_account')
    list_filter = ('tanggal',)
    search_fields = ('utang_header__nomor_utang',)
    raw_id_fields = ('utang_header', 'utang_detail', 'coa_account', 'jurnal_header')


@admin.register(UtangTerhapus)
class UtangTerhapusAdmin(admin.ModelAdmin):
    list_display = ('nomor_utang', 'tanggal', 'deleted_at', 'deleted_by')
    readonly_fields = ('snapshot',)
