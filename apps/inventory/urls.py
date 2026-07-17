"""Inventory URL configuration."""
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_list, name='list'),
    path('export/', views.inventory_export, name='export'),
    path('export/pdf/', views.inventory_export_pdf, name='export_pdf'),
    path('laporan/', views.laporan_persediaan, name='laporan_persediaan'),
    path('create/', views.inventory_create, name='create'),
    path('<int:pk>/', views.inventory_detail, name='detail'),
    path('<int:pk>/convert-to-satuan/', views.convert_bulk_to_satuan, name='convert_to_satuan'),
    path('<int:pk>/edit/', views.inventory_update, name='update'),
    path('<int:pk>/delete/', views.inventory_delete, name='delete'),
    path('warehouse/', views.warehouse_list, name='warehouse_list'),
    path('warehouse/create/', views.warehouse_create, name='warehouse_create'),
    path('warehouse/<int:pk>/edit/', views.warehouse_update, name='warehouse_update'),
    path('warehouse/<int:pk>/toggle/', views.warehouse_toggle, name='warehouse_toggle'),
    path('ledger/', views.stock_ledger, name='stock_ledger'),
    path('kartu-stok/', views.stock_card, name='stock_card'),
    path('adjustment/', views.adjustment_list, name='adjustment_list'),
    path('adjustment/create/', views.adjustment_create, name='adjustment_create'),
    path('adjustment/<int:pk>/delete/', views.adjustment_delete, name='adjustment_delete'),
    path('opname/', views.opname_list, name='opname_list'),
    path('opname/create/', views.opname_create, name='opname_create'),
    path('opname/<int:pk>/delete/', views.opname_delete, name='opname_delete'),
    path('transfer/', views.transfer_list, name='transfer_list'),
    path('transfer/create/', views.transfer_create, name='transfer_create'),
    path('transfer/<int:pk>/delete/', views.transfer_delete, name='transfer_delete'),
]
