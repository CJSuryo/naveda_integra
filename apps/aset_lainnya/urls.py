"""Aset Lainnya URL configuration."""
from django.urls import path
from . import views

app_name = 'aset_lainnya'

urlpatterns = [
    path('', views.aset_lainnya_list, name='list'),
    path('create/', views.aset_lainnya_create, name='create'),
    path('<int:pk>/', views.aset_lainnya_detail, name='detail'),
    path('<int:pk>/edit/', views.aset_lainnya_update, name='update'),
    path('<int:pk>/delete/', views.aset_lainnya_delete, name='delete'),
    path('<int:pk>/proses-amortisasi/', views.aset_lainnya_process_amortization, name='process_amortization'),
]
