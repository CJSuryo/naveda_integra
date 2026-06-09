from django.contrib import admin
from .models import (
    PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog,
    RecurringTemplate, DeferredRevenueSchedule, DeferredRevenueEntry,
)


class PendapatanEBInline(admin.TabularInline):
    model = PendapatanEntitasBisnis
    extra = 0


class PendapatanEventLogInline(admin.TabularInline):
    model = PendapatanEventLog
    extra = 0
    readonly_fields = ('event_type', 'description', 'actor', 'timestamp')


@admin.register(PendapatanHeader)
class PendapatanHeaderAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'tanggal', 'payment_type', 'status', 'source_type')
    list_filter = ('status', 'payment_type', 'source_type')
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


@admin.register(DeferredRevenueSchedule)
class DeferredRevenueScheduleAdmin(admin.ModelAdmin):
    list_display = ['id', 'pendapatan_item', 'jumlah_total', 'metode']
    list_filter = ['metode']
    search_fields = ['pendapatan_item__id']
    readonly_fields = ['created_at']


@admin.register(DeferredRevenueEntry)
class DeferredRevenueEntryAdmin(admin.ModelAdmin):
    list_display = ['id', 'schedule', 'periode', 'jumlah', 'status']
    list_filter = ['status', 'periode']
    search_fields = ['schedule__id']
    readonly_fields = []
