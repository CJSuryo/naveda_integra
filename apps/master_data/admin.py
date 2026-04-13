"""Master data admin."""
from django.contrib import admin
from .models import (
    AsetLv1, AsetLv2,
    KewajibanLv1, KewajibanLv2,
    EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2,
    BebanLv1, BebanLv2,
    Akun, TipeTransaksi, Bukti,
)


class Lv2InlineBase(admin.TabularInline):
    extra = 0


class AsetLv2Inline(Lv2InlineBase):
    model = AsetLv2


class KewajibanLv2Inline(Lv2InlineBase):
    model = KewajibanLv2


class EkuitasLv2Inline(Lv2InlineBase):
    model = EkuitasLv2


class PendapatanLv2Inline(Lv2InlineBase):
    model = PendapatanLv2


class BebanLv2Inline(Lv2InlineBase):
    model = BebanLv2


@admin.register(AsetLv1)
class AsetLv1Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')
    inlines = (AsetLv2Inline,)


@admin.register(AsetLv2)
class AsetLv2Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'aset')
    search_fields = ('kode', 'nama')
    list_filter = ('aset',)


@admin.register(KewajibanLv1)
class KewajibanLv1Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')
    inlines = (KewajibanLv2Inline,)


@admin.register(KewajibanLv2)
class KewajibanLv2Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'kewajiban')
    search_fields = ('kode', 'nama')
    list_filter = ('kewajiban',)


@admin.register(EkuitasLv1)
class EkuitasLv1Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')
    inlines = (EkuitasLv2Inline,)


@admin.register(EkuitasLv2)
class EkuitasLv2Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'ekuitas')
    search_fields = ('kode', 'nama')
    list_filter = ('ekuitas',)


@admin.register(PendapatanLv1)
class PendapatanLv1Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')
    inlines = (PendapatanLv2Inline,)


@admin.register(PendapatanLv2)
class PendapatanLv2Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'pendapatan')
    search_fields = ('kode', 'nama')
    list_filter = ('pendapatan',)


@admin.register(BebanLv1)
class BebanLv1Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama')
    search_fields = ('kode', 'nama')
    inlines = (BebanLv2Inline,)


@admin.register(BebanLv2)
class BebanLv2Admin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'beban')
    search_fields = ('kode', 'nama')
    list_filter = ('beban',)


@admin.register(Akun)
class AkunAdmin(admin.ModelAdmin):
    list_display = ('id', 'kategori_id', 'kategori_akun', 'nama')
    list_filter = ('kategori_id',)
    search_fields = ('nama',)


@admin.register(TipeTransaksi)
class TipeTransaksiAdmin(admin.ModelAdmin):
    list_display = ('kode_transaksi', 'nama')
    search_fields = ('kode_transaksi', 'nama')


@admin.register(Bukti)
class BuktiAdmin(admin.ModelAdmin):
    list_display = ('referensi_eksternal', 'tipe_dokumen', 'uploaded_at')
    search_fields = ('referensi_eksternal',)
