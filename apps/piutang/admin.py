"""Piutang admin."""
from django.contrib import admin
from .models import PiutangHeader, PiutangDetail


class PiutangDetailInline(admin.TabularInline):
    model = PiutangDetail
    extra = 0


@admin.register(PiutangHeader)
class PiutangHeaderAdmin(admin.ModelAdmin):
    list_display = ('id', 'entitas_bisnis', 'dll')
    inlines = (PiutangDetailInline,)


@admin.register(PiutangDetail)
class PiutangDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'piutang_header', 'dll')
