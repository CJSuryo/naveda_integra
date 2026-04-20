"""Ekuitas URL configuration."""
from django.urls import path
from . import views

app_name = 'ekuitas'

urlpatterns = [
    path('', views.ekuitas_list, name='list'),
    path('export/', views.ekuitas_export, name='export'),
    path('export/pdf/', views.ekuitas_export_pdf, name='export_pdf'),
    path('create/', views.ekuitas_create, name='create'),
    path('<int:pk>/', views.ekuitas_detail, name='detail'),
    path('<int:pk>/delete/', views.ekuitas_delete, name='delete'),
    path('history/', views.ekuitas_history, name='history'),
    path('api/pemilik-search/', views.api_pemilik_search, name='api_pemilik_search'),
    path('api/pemilik-create/', views.api_pemilik_create, name='api_pemilik_create'),
]
