"""Master data URLs."""
from django.urls import path
from . import views

app_name = 'master_data'

urlpatterns = [
    # Aset Level 1
    path('aset/create/', views.aset_lv1_create, name='aset_lv1_create'),
    path('aset/<int:pk>/edit/', views.aset_lv1_update, name='aset_lv1_update'),
    path('aset/<int:pk>/delete/', views.aset_lv1_delete, name='aset_lv1_delete'),
    # Aset Level 2
    path('aset/<int:lv1_pk>/lv2/create/', views.aset_lv2_create, name='aset_lv2_create'),
    path('aset/<int:lv1_pk>/lv2/<int:pk>/edit/', views.aset_lv2_update, name='aset_lv2_update'),
    path('aset/<int:lv1_pk>/lv2/<int:pk>/delete/', views.aset_lv2_delete, name='aset_lv2_delete'),
    # Kewajiban Level 1
    path('kewajiban/create/', views.kewajiban_lv1_create, name='kewajiban_lv1_create'),
    path('kewajiban/<int:pk>/edit/', views.kewajiban_lv1_update, name='kewajiban_lv1_update'),
    path('kewajiban/<int:pk>/delete/', views.kewajiban_lv1_delete, name='kewajiban_lv1_delete'),
    # Kewajiban Level 2
    path('kewajiban/<int:lv1_pk>/lv2/create/', views.kewajiban_lv2_create, name='kewajiban_lv2_create'),
    path('kewajiban/<int:lv1_pk>/lv2/<int:pk>/edit/', views.kewajiban_lv2_update, name='kewajiban_lv2_update'),
    path('kewajiban/<int:lv1_pk>/lv2/<int:pk>/delete/', views.kewajiban_lv2_delete, name='kewajiban_lv2_delete'),
    # Ekuitas Level 1
    path('ekuitas/create/', views.ekuitas_lv1_create, name='ekuitas_lv1_create'),
    path('ekuitas/<int:pk>/edit/', views.ekuitas_lv1_update, name='ekuitas_lv1_update'),
    path('ekuitas/<int:pk>/delete/', views.ekuitas_lv1_delete, name='ekuitas_lv1_delete'),
    # Ekuitas Level 2
    path('ekuitas/<int:lv1_pk>/lv2/create/', views.ekuitas_lv2_create, name='ekuitas_lv2_create'),
    path('ekuitas/<int:lv1_pk>/lv2/<int:pk>/edit/', views.ekuitas_lv2_update, name='ekuitas_lv2_update'),
    path('ekuitas/<int:lv1_pk>/lv2/<int:pk>/delete/', views.ekuitas_lv2_delete, name='ekuitas_lv2_delete'),
    # Pendapatan Level 1
    path('pendapatan/create/', views.pendapatan_lv1_create, name='pendapatan_lv1_create'),
    path('pendapatan/<int:pk>/edit/', views.pendapatan_lv1_update, name='pendapatan_lv1_update'),
    path('pendapatan/<int:pk>/delete/', views.pendapatan_lv1_delete, name='pendapatan_lv1_delete'),
    # Pendapatan Level 2
    path('pendapatan/<int:lv1_pk>/lv2/create/', views.pendapatan_lv2_create, name='pendapatan_lv2_create'),
    path('pendapatan/<int:lv1_pk>/lv2/<int:pk>/edit/', views.pendapatan_lv2_update, name='pendapatan_lv2_update'),
    path('pendapatan/<int:lv1_pk>/lv2/<int:pk>/delete/', views.pendapatan_lv2_delete, name='pendapatan_lv2_delete'),
    # Beban Level 1
    path('beban/create/', views.beban_lv1_create, name='beban_lv1_create'),
    path('beban/<int:pk>/edit/', views.beban_lv1_update, name='beban_lv1_update'),
    path('beban/<int:pk>/delete/', views.beban_lv1_delete, name='beban_lv1_delete'),
    # Beban Level 2
    path('beban/<int:lv1_pk>/lv2/create/', views.beban_lv2_create, name='beban_lv2_create'),
    path('beban/<int:lv1_pk>/lv2/<int:pk>/edit/', views.beban_lv2_update, name='beban_lv2_update'),
    path('beban/<int:lv1_pk>/lv2/<int:pk>/delete/', views.beban_lv2_delete, name='beban_lv2_delete'),
    # Chart of Accounts
    path('chart-of-accounts/', views.chart_of_accounts, name='chart_of_accounts'),
    path('chart-of-accounts/export/', views.coa_export, name='coa_export'),
    path('chart-of-accounts/import/', views.coa_import, name='coa_import'),
    path('chart-of-accounts/preview/', views.coa_preview, name='coa_preview'),
    path('chart-of-accounts/import-json/', views.coa_import_json, name='coa_import_json'),
    # Tipe Transaksi (read-only)
    path('tipe-transaksi/', views.tipe_transaksi_list, name='tipe_transaksi_list'),
    # Prefiks Transaksi (read-only, data lives in jurnal.TransactionPrefix)
    path('prefiks-transaksi/', views.prefix_list, name='prefix_list'),
    # Bukti
    path('bukti/<int:pk>/', views.bukti_detail, name='bukti_detail'),
]
