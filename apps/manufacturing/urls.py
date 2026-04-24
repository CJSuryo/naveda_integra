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
    path('<int:pk>/approve/', views.production_approve, name='production_approve'),

    # Overhead Category CRUD
    path('overhead/', views.overhead_category_list, name='overhead_category_list'),
    path('overhead/create/', views.overhead_category_create, name='overhead_category_create'),
    path('overhead/<int:pk>/edit/', views.overhead_category_update, name='overhead_category_update'),
    path('overhead/<int:pk>/delete/', views.overhead_category_delete, name='overhead_category_delete'),

    # Overhead Rates
    path('overhead/rates/', views.overhead_rate_setup, name='overhead_rate_setup'),

    # Overhead Monitoring + Period Closing
    path('overhead/monitoring/', views.overhead_monitoring, name='overhead_monitoring'),
    path('overhead/period-closing/', views.overhead_period_closing, name='overhead_period_closing'),

    # AJAX API
    path('api/bom-preview/', views.api_bom_preview, name='api_bom_preview'),
    path('api/boms-by-entity/', views.api_boms_by_entity, name='api_boms_by_entity'),
    path('api/overhead-rates/', views.api_overhead_rates, name='api_overhead_rates'),
]
