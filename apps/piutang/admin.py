"""Piutang admin."""
from django.contrib import admin
from .models import PiutangHeader, PiutangDetail


class PiutangDetailInline(admin.TabularInline):
    model = PiutangDetail
    extra = 0


@admin.register(PiutangHeader)
class PiutangHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'entitas_bisnis', 'dll')
    list_select_related = ('entitas_bisnis',)
    raw_id_fields = ('entitas_bisnis',)
    inlines = (PiutangDetailInline,)


@admin.register(PiutangDetail)
class PiutangDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'dll')
    list_select_related = ('piutang_header',)
