"""Sales URLs."""
from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Sales transactions
    path('', views.sales_list, name='list'),
    path('create/', views.sales_create, name='create'),
    path('<int:pk>/', views.sales_detail, name='detail'),
    path('<int:pk>/edit/', views.sales_update, name='update'),
    path('<int:pk>/delete/', views.sales_delete, name='delete'),

    # API endpoints
    path('api/stock-check/', views.api_stock_check, name='api_stock_check'),
    path('api/stt-offset/', views.api_stt_offset, name='api_stt_offset'),
]
