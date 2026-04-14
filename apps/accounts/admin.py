"""Admin for accounts app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Role, NiPermission, UserEntitasBisnis


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'deskripsi')
    search_fields = ('kode', 'nama')


@admin.register(NiPermission)
class NiPermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'module')
    list_filter = ('module',)
    search_fields = ('code', 'name')


class UserEntitasBisnisInline(admin.TabularInline):
    model = UserEntitasBisnis
    extra = 0
    raw_id_fields = ('entitas_bisnis',)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('name', 'role')}),
        ('App Permissions', {'fields': ('ni_permissions',)}),
        ('Django Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'name', 'role', 'password1', 'password2')}),
    )
    list_display = ('email', 'name', 'role', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'role')
    search_fields = ('email', 'name')
    ordering = ('email',)
    list_select_related = ('role',)
    filter_horizontal = ('ni_permissions',)
    inlines = (UserEntitasBisnisInline,)


@admin.register(UserEntitasBisnis)
class UserEntitasBisnisAdmin(admin.ModelAdmin):
    list_display = ('user', 'entitas_bisnis')
    list_select_related = ('user', 'entitas_bisnis')
    raw_id_fields = ('user', 'entitas_bisnis')
