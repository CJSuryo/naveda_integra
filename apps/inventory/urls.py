"""Inventory URL configuration."""
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='list'),
    path('create/', views.inventory_create, name='create'),
    path('<int:pk>/', views.inventory_detail, name='detail'),
    path('<int:pk>/convert-to-satuan/', views.convert_bulk_to_satuan, name='convert_to_satuan'),
    path('<int:pk>/edit/', views.inventory_update, name='update'),
    path('<int:pk>/delete/', views.inventory_delete, name='delete'),
]
