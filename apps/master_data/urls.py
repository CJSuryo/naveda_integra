"""Master data URLs."""
from django.urls import path
from . import views

app_name = 'master_data'

urlpatterns = [
    # Aset Level 1
    path('aset/', views.aset_lv1_list, name='aset_lv1_list'),
    path('aset/create/', views.aset_lv1_create, name='aset_lv1_create'),
    path('aset/<int:pk>/', views.aset_lv1_detail, name='aset_lv1_detail'),
    path('aset/<int:pk>/edit/', views.aset_lv1_update, name='aset_lv1_update'),
    path('aset/<int:pk>/delete/', views.aset_lv1_delete, name='aset_lv1_delete'),
    # Aset Level 2
    path('aset/<int:lv1_pk>/lv2/create/', views.aset_lv2_create, name='aset_lv2_create'),
    path('aset/<int:lv1_pk>/lv2/<int:pk>/edit/', views.aset_lv2_update, name='aset_lv2_update'),
    path('aset/<int:lv1_pk>/lv2/<int:pk>/delete/', views.aset_lv2_delete, name='aset_lv2_delete'),
    # Kewajiban Level 1
    path('kewajiban/', views.kewajiban_lv1_list, name='kewajiban_lv1_list'),
    path('kewajiban/create/', views.kewajiban_lv1_create, name='kewajiban_lv1_create'),
    path('kewajiban/<int:pk>/', views.kewajiban_lv1_detail, name='kewajiban_lv1_detail'),
    path('kewajiban/<int:pk>/edit/', views.kewajiban_lv1_update, name='kewajiban_lv1_update'),
    path('kewajiban/<int:pk>/delete/', views.kewajiban_lv1_delete, name='kewajiban_lv1_delete'),
    # Kewajiban Level 2
    path('kewajiban/<int:lv1_pk>/lv2/create/', views.kewajiban_lv2_create, name='kewajiban_lv2_create'),
    path('kewajiban/<int:lv1_pk>/lv2/<int:pk>/edit/', views.kewajiban_lv2_update, name='kewajiban_lv2_update'),
    path('kewajiban/<int:lv1_pk>/lv2/<int:pk>/delete/', views.kewajiban_lv2_delete, name='kewajiban_lv2_delete'),
    # Ekuitas Level 1
    path('ekuitas/', views.ekuitas_lv1_list, name='ekuitas_lv1_list'),
    path('ekuitas/create/', views.ekuitas_lv1_create, name='ekuitas_lv1_create'),
    path('ekuitas/<int:pk>/', views.ekuitas_lv1_detail, name='ekuitas_lv1_detail'),
    path('ekuitas/<int:pk>/edit/', views.ekuitas_lv1_update, name='ekuitas_lv1_update'),
    path('ekuitas/<int:pk>/delete/', views.ekuitas_lv1_delete, name='ekuitas_lv1_delete'),
    # Ekuitas Level 2
    path('ekuitas/<int:lv1_pk>/lv2/create/', views.ekuitas_lv2_create, name='ekuitas_lv2_create'),
    path('ekuitas/<int:lv1_pk>/lv2/<int:pk>/edit/', views.ekuitas_lv2_update, name='ekuitas_lv2_update'),
    path('ekuitas/<int:lv1_pk>/lv2/<int:pk>/delete/', views.ekuitas_lv2_delete, name='ekuitas_lv2_delete'),
    # Tipe Transaksi
    path('tipe-transaksi/', views.tipe_transaksi_list, name='tipe_transaksi_list'),
    path('tipe-transaksi/create/', views.tipe_transaksi_create, name='tipe_transaksi_create'),
    path('tipe-transaksi/<int:pk>/edit/', views.tipe_transaksi_update, name='tipe_transaksi_update'),
    path('tipe-transaksi/<int:pk>/delete/', views.tipe_transaksi_delete, name='tipe_transaksi_delete'),
]
