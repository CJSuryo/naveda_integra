"""Manufacturing URLs."""
from django.urls import path
from . import views

app_name = 'manufacturing'

urlpatterns = [
    # BOM
    path('bom/', views.bom_list, name='bom_list'),
    path('bom/create/', views.bom_create, name='bom_create'),
    path('bom/<int:pk>/', views.bom_detail, name='bom_detail'),
    path('bom/<int:pk>/edit/', views.bom_update, name='bom_update'),
    path('bom/<int:pk>/delete/', views.bom_delete, name='bom_delete'),

    # Production Orders
    path('', views.production_list, name='production_list'),
    path('create/', views.production_create, name='production_create'),
    path('<int:pk>/', views.production_detail, name='production_detail'),
    path('<int:pk>/delete/', views.production_delete, name='production_delete'),
    path('<int:pk>/reverse/', views.production_reverse, name='production_reverse'),

    # AJAX API
    path('api/bom-preview/', views.api_bom_preview, name='api_bom_preview'),
]
