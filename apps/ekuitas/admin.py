from django.contrib import admin
from .models import ModalDisetor, ModalDisetorDebit, Pemilik


@admin.register(Pemilik)
class PemilikAdmin(admin.ModelAdmin):
    list_display = ('nama', 'keterangan', 'created_at')
    search_fields = ('nama',)


class ModalDisetorDebitInline(admin.TabularInline):
    model = ModalDisetorDebit
    extra = 0
    raw_id_fields = ('akun',)
    readonly_fields = ('akun', 'jumlah')


@admin.register(ModalDisetor)
class ModalDisetorAdmin(admin.ModelAdmin):
    list_display = ('pemilik', 'entitas_bisnis', 'jumlah_modal', 'tanggal_setor', 'jurnal_header')
    list_filter = ('entitas_bisnis', 'tanggal_setor')
    search_fields = ('pemilik__nama', 'entitas_bisnis__nama')
    list_select_related = ('entitas_bisnis', 'pemilik', 'jurnal_header')
    raw_id_fields = ('jurnal_header',)
    inlines = [ModalDisetorDebitInline]
