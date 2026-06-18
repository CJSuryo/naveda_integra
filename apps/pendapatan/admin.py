from django.contrib import admin
from .models import (
    PendapatanHeader, PendapatanEntitasBisnis, KewajibabPelaksanaan,
    PendapatanEventLog, RecurringTemplate,
    JadwalPengakuan, EntriPengakuan, AsetKontrak,
)

# Backward-compat: PendapatanItem is an alias for KewajibabPelaksanaan in models.py


class PendapatanEBInline(admin.TabularInline):
    model = PendapatanEntitasBisnis
    extra = 0


class PendapatanEventLogInline(admin.TabularInline):
    model = PendapatanEventLog
    extra = 0
    readonly_fields = ('event_type', 'description', 'actor', 'timestamp')


@admin.register(PendapatanHeader)
class PendapatanHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'payment_type', 'standar_akuntansi', 'status', 'source_type')
    list_filter = ('status', 'payment_type', 'standar_akuntansi', 'source_type')
    search_fields = ('transaction_id', 'deskripsi')
    readonly_fields = ('transaction_id', 'created_at', 'updated_at')
    inlines = [PendapatanEBInline, PendapatanEventLogInline]


@admin.register(RecurringTemplate)
class RecurringTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'nama', 'entitas_bisnis', 'frekuensi', 'jumlah',
        'tanggal_berikutnya', 'auto_confirm', 'is_active',
    ]
    list_filter = ['frekuensi', 'is_active', 'auto_confirm', 'payment_type']
    search_fields = ['nama', 'entitas_bisnis__nama']
    readonly_fields = ['tanggal_berikutnya', 'created_at', 'updated_at', 'created_by']


class EntriPengakuanInline(admin.TabularInline):
    model = EntriPengakuan
    extra = 0
    readonly_fields = ['nilai_diakui', 'status', 'jurnal_header']


@admin.register(JadwalPengakuan)
class JadwalPengakuanAdmin(admin.ModelAdmin):
    list_display = ['kp', 'tipe_aliran', 'progress_method', 'nilai_total', 'nilai_diakui', 'status']
    list_filter = ['tipe_aliran', 'status']
    inlines = [EntriPengakuanInline]


@admin.register(AsetKontrak)
class AsetKontrakAdmin(admin.ModelAdmin):
    list_display = ['kp', 'tanggal', 'nilai', 'nilai_tersisa', 'status']
    list_filter = ['status']
