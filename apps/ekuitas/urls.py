"""Ekuitas URL configuration."""
from django.urls import path
from . import views

app_name = 'ekuitas'

urlpatterns = [
    path('', views.ekuitas_list, name='list'),
    path('create/', views.ekuitas_create, name='create'),
    path('<int:pk>/', views.ekuitas_detail, name='detail'),
    path('<int:pk>/edit/', views.ekuitas_update, name='update'),
    path('<int:pk>/delete/', views.ekuitas_delete, name='delete'),
]
