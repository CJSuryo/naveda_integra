"""Aset Tetap URL configuration."""
from django.urls import path
from . import views

app_name = 'aset_tetap'

urlpatterns = [
    path('', views.aset_tetap_list, name='list'),
    path('export/', views.aset_tetap_export, name='export'),
    path('export/pdf/', views.aset_tetap_export_pdf, name='export_pdf'),
    path('create/', views.aset_tetap_create, name='create'),
    path('<int:pk>/', views.aset_tetap_detail, name='detail'),
    path('<int:pk>/edit/', views.aset_tetap_update, name='update'),
    path('<int:pk>/delete/', views.aset_tetap_delete, name='delete'),
    path('<int:pk>/proses-penyusutan/', views.aset_tetap_process_depreciation, name='process_depreciation'),
    path('<int:pk>/jurnal-penyusutan/<int:jurnal_pk>/hapus/', views.delete_depreciation_journal, name='delete_dep_journal'),
    path('bulk-penyusutan/', views.aset_tetap_bulk_depreciation, name='bulk_depreciation'),
    path('bulk-penyusutan/preview/', views.aset_tetap_bulk_preview, name='bulk_preview'),
    path('<int:pk>/lepas/', views.aset_tetap_dispose, name='dispose'),
    path('<int:pk>/pelepasan/<int:disposal_pk>/batal/', views.aset_tetap_disposal_delete, name='disposal_delete'),
]
