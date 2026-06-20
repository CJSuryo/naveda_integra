from django.urls import path

from . import views

app_name = 'pajak'

urlpatterns = [
    path('hitung/', views.hitung_pajak, name='hitung_pajak'),
    path('transaksi/', views.transaksi_list, name='transaksi_list'),
    path('transaksi/<int:pk>/', views.transaksi_detail, name='transaksi_detail'),
    path('transaksi/<int:pk>/edit/', views.transaksi_edit, name='transaksi_edit'),
    path('transaksi/<int:pk>/hapus/', views.transaksi_hapus, name='transaksi_hapus'),
    path('transaksi/<int:pk>/batalkan/', views.transaksi_batalkan, name='transaksi_batalkan'),
    path('masa/', views.masa_list, name='masa_list'),
    path('masa/<int:pk>/', views.masa_detail, name='masa_detail'),
    path('tarif/', views.tarif_list, name='tarif_list'),
    path('tarif/tambah/', views.tarif_form, name='tarif_tambah'),
    path('tarif/<int:pk>/edit/', views.tarif_form, name='tarif_edit'),
]
