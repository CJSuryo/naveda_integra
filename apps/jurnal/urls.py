"""Jurnal URLs."""
from django.urls import path
from . import views

app_name = 'jurnal'

urlpatterns = [
    # Rekap Jurnal (read-only journal index with date filtering)
    path('rekap/', views.rekap_jurnal, name='rekap_jurnal'),

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

    # Neraca Saldo (Trial Balance)
    path('neraca-saldo/', views.neraca_saldo, name='neraca_saldo'),

    # Manual Jurnal (direct spreadsheet-style entry)
    path('manual-jurnal/', views.manual_jurnal_create, name='manual_jurnal'),

    # API
    path('api/akun-autocomplete/', views.akun_autocomplete, name='akun_autocomplete'),
]
