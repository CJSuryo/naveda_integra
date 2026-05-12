"""Sales URLs."""
from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Sales transactions
    path('', views.sales_list, name='list'),
    path('export/', views.sales_export, name='export'),
    path('export/pdf/', views.sales_export_pdf, name='export_pdf'),
    path('create/', views.sales_create, name='create'),
    path('<int:pk>/', views.sales_detail, name='detail'),
    path('<int:pk>/invoice/', views.sales_invoice, name='invoice'),
    path('<int:pk>/edit/', views.sales_update, name='update'),
    path('<int:pk>/delete/', views.sales_delete, name='delete'),

    # API endpoints
    path('api/stock-check/', views.api_stock_check, name='api_stock_check'),
    path('api/stt-offset/', views.api_stt_offset, name='api_stt_offset'),
    path('api/stt-defaults/', views.api_stt_defaults, name='api_stt_defaults'),
]
