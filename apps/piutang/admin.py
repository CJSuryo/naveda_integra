from django.contrib import admin

from .models import (
    PiutangAttachment, PiutangAuditLog, PiutangDetail, PiutangHeader,
    PiutangPenerimaan, PiutangReklasifikasi, PiutangWriteOff,
)


class PiutangDetailInline(admin.TabularInline):
    model = PiutangDetail
    extra = 0


class PiutangPenerimaanInline(admin.TabularInline):
    model = PiutangPenerimaan
    extra = 0
    readonly_fields = ('jurnal_header',)


@admin.register(PiutangHeader)
class PiutangHeaderAdmin(admin.ModelAdmin):
    list_display = ('nomor_piutang', 'tanggal', 'debitur', 'entitas_bisnis', 'jumlah_pokok', 'status')
    list_filter = ('status', 'source_type', 'jenis_jangka_waktu')
    search_fields = ('nomor_piutang', 'debitur', 'deskripsi')
    readonly_fields = ('nomor_piutang', 'created_at', 'updated_at')
    inlines = [PiutangDetailInline, PiutangPenerimaanInline]


@admin.register(PiutangAuditLog)
class PiutangAuditLogAdmin(admin.ModelAdmin):
    list_display = ('nomor_piutang', 'action', 'user', 'timestamp')
    list_filter = ('action',)
    readonly_fields = ('timestamp',)
