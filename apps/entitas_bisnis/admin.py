"""EntitasBisnis admin."""
from django.contrib import admin
from .models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3


class EntitasBisnisLv2Inline(admin.TabularInline):
    model = EntitasBisnisLv2
    extra = 0


class EntitasBisnisLv3Inline(admin.TabularInline):
    model = EntitasBisnisLv3
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
    inlines = (EntitasBisnisLv2Inline,)


@admin.register(EntitasBisnisLv2)
class EntitasBisnisLv2Admin(admin.ModelAdmin):
    list_display = ('nama', 'entitas_bisnis', 'email', 'telepon', 'status_aktif')
    list_filter = ('status_aktif', 'entitas_bisnis')
    search_fields = ('nama', 'email')
    list_select_related = ('entitas_bisnis',)
    inlines = (EntitasBisnisLv3Inline,)


@admin.register(EntitasBisnisLv3)
class EntitasBisnisLv3Admin(admin.ModelAdmin):
    list_display = ('nama', 'parent_lv2', 'email', 'telepon', 'status_aktif')
    list_filter = ('status_aktif',)
    search_fields = ('nama', 'email')
    list_select_related = ('parent_lv2',)
