from django.contrib import admin
from .models import PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog


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
