"""Sales URLs."""
from django.urls import path
from . import views, kasir_views

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

    # POS cashier
    path('pos/', views.pos_cashier, name='pos_cashier'),

    # API endpoints
    path('api/stock-check/', views.api_stock_check, name='api_stock_check'),
    path('api/stt-offset/', views.api_stt_offset, name='api_stt_offset'),
    path('api/stt-defaults/', views.api_stt_defaults, name='api_stt_defaults'),
    path('api/pos-items/', views.api_pos_items, name='api_pos_items'),

    # Kasir POS
    path('kasir/', kasir_views.kasir_pos, name='kasir_pos'),
    path('kasir/api/catalog/', kasir_views.api_kasir_catalog, name='api_kasir_catalog'),
    path('kasir/api/config/<int:lv3_pk>/', kasir_views.api_kasir_config, name='api_kasir_config'),
    path('kasir/api/submit/', kasir_views.api_kasir_submit, name='api_kasir_submit'),
]
