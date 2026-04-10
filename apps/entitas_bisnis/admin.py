"""EntitasBisnis admin."""
from django.contrib import admin
from .models import EntitasBisnis


@admin.register(EntitasBisnis)
class EntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('nama', 'tipe_entitas', 'email', 'telepon', 'status_aktif')
    list_filter = ('tipe_entitas', 'status_aktif')
    search_fields = ('nama', 'email', 'tax_id')
    filter_horizontal = ('users',)
