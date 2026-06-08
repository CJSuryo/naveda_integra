"""Piutang admin."""
from django.contrib import admin
from .models import (
    PiutangHeader, PiutangDetail, PiutangPenerimaan,
    PiutangReklasifikasi, PiutangWriteOff, PiutangAttachment, PiutangAuditLog,
)


class PiutangDetailInline(admin.TabularInline):
    model = PiutangDetail
    extra = 0


class PiutangPenerimaanInline(admin.TabularInline):
    model = PiutangPenerimaan
    extra = 0


@admin.register(PiutangHeader)
class PiutangHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_piutang', 'tanggal', 'debitur', 'jumlah_pokok', 'status')
    list_filter = ('status', 'jenis_jangka_waktu', 'source_type')
    search_fields = ('nomor_piutang', 'debitur', 'deskripsi')
    list_select_related = ('entitas_bisnis',)
    raw_id_fields = ('entitas_bisnis', 'coa_piutang_account', 'created_by', 'approved_by')
    inlines = (PiutangDetailInline, PiutangPenerimaanInline)
    readonly_fields = ('nomor_piutang', 'created_at', 'updated_at')


@admin.register(PiutangDetail)
class PiutangDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'deskripsi', 'jumlah')
    list_select_related = ('piutang_header',)
    raw_id_fields = ('piutang_header', 'revenue_account')


@admin.register(PiutangPenerimaan)
class PiutangPenerimaanAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'tanggal_terima', 'jumlah_diterima', 'metode_penerimaan')
    list_select_related = ('piutang_header',)
    raw_id_fields = ('piutang_header', 'payment_account', 'jurnal_header', 'created_by')


@admin.register(PiutangReklasifikasi)
class PiutangReklasifikasiAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'tanggal', 'jumlah')
    list_select_related = ('piutang_header',)
    raw_id_fields = ('piutang_header', 'dari_akun', 'ke_akun', 'jurnal', 'created_by')


@admin.register(PiutangWriteOff)
class PiutangWriteOffAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'tanggal', 'jumlah_dihapus', 'metode')
    list_select_related = ('piutang_header',)
    raw_id_fields = ('piutang_header', 'bad_debt_account', 'allowance_account', 'jurnal', 'created_by')


@admin.register(PiutangAttachment)
class PiutangAttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'file_name', 'jenis_dokumen', 'uploaded_at')
    list_select_related = ('piutang_header',)
    raw_id_fields = ('piutang_header', 'uploaded_by')


@admin.register(PiutangAuditLog)
class PiutangAuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'nomor_piutang', 'action', 'user', 'timestamp')
    list_filter = ('action',)
    search_fields = ('nomor_piutang',)
    raw_id_fields = ('piutang_header', 'user')
    readonly_fields = ('timestamp', 'before_json', 'after_json')
