from django.contrib import admin
from .models import ModalDisetor


@admin.register(ModalDisetor)
class ModalDisetorAdmin(admin.ModelAdmin):
    list_display = ('nama_pemilik', 'entitas_bisnis', 'jumlah_modal', 'persentase_kepemilikan', 'tanggal_setor')
    list_filter = ('entitas_bisnis', 'tanggal_setor')
    search_fields = ('nama_pemilik', 'entitas_bisnis__nama')
    list_select_related = ('entitas_bisnis',)
