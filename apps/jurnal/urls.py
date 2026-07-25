"""Jurnal URLs."""
from django.urls import path
from . import views

app_name = 'jurnal'

urlpatterns = [
    # Rekap Jurnal (read-only journal index with date filtering)
    path('rekap/', views.rekap_jurnal, name='rekap_jurnal'),
    path('rekap/export/', views.rekap_jurnal_export, name='rekap_jurnal_export'),

    # JurnalHeader detail (read-only)
    path('header/<int:pk>/', views.header_detail, name='header_detail'),

    # Jurnal Manual (renamed from Automasi)
    path('manual/', views.automasi_list, name='automasi_list'),
    path('manual/create/', views.automasi_create, name='automasi_create'),
    path('manual/<int:pk>/', views.automasi_detail, name='automasi_detail'),
    path('manual/<int:pk>/edit/', views.automasi_update, name='automasi_update'),
    path('manual/<int:pk>/delete/', views.automasi_delete, name='automasi_delete'),
    path('manual/<int:pk>/add-akun/', views.automasi_add_akun, name='automasi_add_akun'),
    path('manual/<int:pk>/remove-akun/<int:mapping_pk>/', views.automasi_remove_akun, name='automasi_remove_akun'),
    path('manual/<int:pk>/entry/', views.automasi_entry, name='automasi_entry'),

    # Laporan Keuangan (hub)
    path('laporan-keuangan/', views.laporan_keuangan_hub, name='laporan_keuangan_hub'),

    # Neraca Saldo (Trial Balance)
    path('neraca-saldo/', views.neraca_saldo, name='neraca_saldo'),

    # Buku Besar (General Ledger)
    path('buku-besar/', views.buku_besar, name='buku_besar'),

    # Laporan Laba Rugi (Income Statement)
    path('laporan-laba-rugi/', views.laporan_laba_rugi, name='laporan_laba_rugi'),

    # Neraca (Balance Sheet)
    path('neraca/', views.neraca, name='neraca'),

    # Laporan Perubahan Ekuitas
    path('laporan-perubahan-ekuitas/', views.laporan_perubahan_ekuitas, name='laporan_perubahan_ekuitas'),
    path('analisis-keuangan/', views.analisis_keuangan, name='analisis_keuangan'),

    # Saldo Awal (Opening Balance) — CRUD
    path('saldo-awal/', views.saldo_awal_list, name='saldo_awal_list'),
    path('saldo-awal/create/', views.saldo_awal, name='saldo_awal'),
    path('saldo-awal/<int:pk>/edit/', views.saldo_awal_edit, name='saldo_awal_edit'),
    path('saldo-awal/<int:pk>/delete/', views.saldo_awal_delete, name='saldo_awal_delete'),

    # Manual Jurnal (direct spreadsheet-style entry)
    path('manual-jurnal/', views.manual_jurnal_create, name='manual_jurnal'),

    # History Jurnal Terhapus
    path('jurnal-terhapus/', views.jurnal_terhapus_list, name='jurnal_terhapus'),

    # Rekap Jurnal CRUD API
    path('api/rekap/<int:pk>/', views.rekap_jurnal_get, name='rekap_jurnal_get'),
    path('api/rekap/<int:pk>/update/', views.rekap_jurnal_update, name='rekap_jurnal_update'),
    path('api/rekap/<int:pk>/delete/', views.rekap_jurnal_delete, name='rekap_jurnal_delete'),

    # API
    path('api/akun-autocomplete/', views.akun_autocomplete, name='akun_autocomplete'),
]
