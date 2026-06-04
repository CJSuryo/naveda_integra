from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('api/penjualan/', views.api_penjualan, name='api_penjualan'),
    path('api/profit/', views.api_profit, name='api_profit'),
    path('api/pengeluaran/', views.api_pengeluaran, name='api_pengeluaran'),
    path('api/rata-pengeluaran/', views.api_rata_pengeluaran, name='api_rata_pengeluaran'),
    path('api/top-persediaan/', views.api_top_persediaan, name='api_top_persediaan'),
    path('api/saldo-persediaan/', views.api_saldo_persediaan, name='api_saldo_persediaan'),
    path('api/utang/', views.api_utang, name='api_utang'),
    path('api/tag-item/', views.api_tag_item, name='api_tag_item'),
    path('api/set-eb/', views.api_set_eb, name='api_set_eb'),
    path('api/eb-options/', views.api_eb_options, name='api_eb_options'),
]
