from django.urls import path

from . import views

app_name = 'pajak'

urlpatterns = [
    path('transaksi/', views.transaksi_list, name='transaksi_list'),
    path('transaksi/<int:pk>/edit/', views.transaksi_edit, name='transaksi_edit'),
    path('masa/', views.masa_list, name='masa_list'),
    path('masa/<int:pk>/', views.masa_detail, name='masa_detail'),
    path('tarif/', views.tarif_list, name='tarif_list'),
    path('tarif/tambah/', views.tarif_form, name='tarif_tambah'),
    path('tarif/<int:pk>/edit/', views.tarif_form, name='tarif_edit'),
]
