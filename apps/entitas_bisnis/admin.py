"""EntitasBisnis admin."""
from django.contrib import admin
from .models import TipeEntitas, EntitasBisnis, CabangEntitasBisnis


class CabangInline(admin.TabularInline):
    model = CabangEntitasBisnis
    extra = 0


@admin.register(TipeEntitas)
class TipeEntitasAdmin(admin.ModelAdmin):
    list_display = ('nama',)
    search_fields = ('nama',)


@admin.register(EntitasBisnis)
class EntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('nama', 'tipe_entitas', 'relasi', 'email', 'telepon', 'status_aktif')
    list_filter = ('tipe_entitas', 'relasi', 'status_aktif')
    search_fields = ('nama', 'email', 'tax_id')
    list_select_related = ('tipe_entitas',)
    filter_horizontal = ('users',)
    inlines = (CabangInline,)


@admin.register(CabangEntitasBisnis)
class CabangEntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('nama', 'entitas_bisnis', 'email', 'telepon', 'status_aktif')
    list_filter = ('status_aktif', 'entitas_bisnis')
    search_fields = ('nama', 'email')
    list_select_related = ('entitas_bisnis',)
