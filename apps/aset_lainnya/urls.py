"""Aset Lainnya URL configuration."""
from django.urls import path
from . import views

app_name = 'aset_lainnya'

urlpatterns = [
    path('', views.aset_lainnya_list, name='list'),
    path('export/', views.aset_lainnya_export, name='export'),
    path('export/pdf/', views.aset_lainnya_export_pdf, name='export_pdf'),
    path('create/', views.aset_lainnya_create, name='create'),
    path('<int:pk>/', views.aset_lainnya_detail, name='detail'),
    path('<int:pk>/edit/', views.aset_lainnya_update, name='update'),
    path('<int:pk>/delete/', views.aset_lainnya_delete, name='delete'),
    path('<int:pk>/proses-amortisasi/', views.aset_lainnya_process_amortization, name='process_amortization'),
    path('<int:pk>/jurnal-amortisasi/<int:jurnal_pk>/hapus/', views.delete_amortization_journal, name='delete_amort_journal'),
    path('bulk-amortisasi/', views.aset_lainnya_bulk_amortization, name='bulk_amortization'),
]
