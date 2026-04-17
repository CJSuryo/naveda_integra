"""Aset Tetap URL configuration."""
from django.urls import path
from . import views

app_name = 'aset_tetap'

urlpatterns = [
    path('', views.aset_tetap_list, name='list'),
    path('create/', views.aset_tetap_create, name='create'),
    path('<int:pk>/', views.aset_tetap_detail, name='detail'),
    path('<int:pk>/edit/', views.aset_tetap_update, name='update'),
    path('<int:pk>/delete/', views.aset_tetap_delete, name='delete'),
    path('<int:pk>/proses-penyusutan/', views.aset_tetap_process_depreciation, name='process_depreciation'),
    path('bulk-penyusutan/', views.aset_tetap_bulk_depreciation, name='bulk_depreciation'),
]
