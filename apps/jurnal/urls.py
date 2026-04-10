"""Jurnal URLs."""
from django.urls import path
from . import views

app_name = 'jurnal'

urlpatterns = [
    # Index (combined header + detail view)
    path('', views.index, name='index'),

    # JurnalHeader CRUD
    path('header/', views.header_list, name='header_list'),
    path('header/create/', views.header_create, name='header_create'),
    path('header/<int:pk>/', views.header_detail, name='header_detail'),
    path('header/<int:pk>/edit/', views.header_update, name='header_update'),
    path('header/<int:pk>/delete/', views.header_delete, name='header_delete'),

    # JurnalDetail CRUD (nested under header)
    path('header/<int:header_pk>/detail/create/', views.detail_create, name='detail_create'),
    path('header/<int:header_pk>/detail/<int:pk>/edit/', views.detail_update, name='detail_update'),
    path('header/<int:header_pk>/detail/<int:pk>/delete/', views.detail_delete, name='detail_delete'),

    # Item CRUD
    path('item/', views.item_list, name='item_list'),
    path('item/create/', views.item_create, name='item_create'),
    path('item/<int:pk>/edit/', views.item_update, name='item_update'),
    path('item/<int:pk>/delete/', views.item_delete, name='item_delete'),

    # TransactionPrefix CRUD
    path('prefix/', views.prefix_list, name='prefix_list'),
    path('prefix/create/', views.prefix_create, name='prefix_create'),
    path('prefix/<int:pk>/edit/', views.prefix_update, name='prefix_update'),
    path('prefix/<int:pk>/delete/', views.prefix_delete, name='prefix_delete'),

    # Automasi CRUD
    path('automasi/', views.automasi_list, name='automasi_list'),
    path('automasi/create/', views.automasi_create, name='automasi_create'),
    path('automasi/<int:pk>/', views.automasi_detail, name='automasi_detail'),
    path('automasi/<int:pk>/edit/', views.automasi_update, name='automasi_update'),
    path('automasi/<int:pk>/delete/', views.automasi_delete, name='automasi_delete'),
    path('automasi/<int:pk>/add-akun/', views.automasi_add_akun, name='automasi_add_akun'),
    path('automasi/<int:pk>/remove-akun/<int:mapping_pk>/', views.automasi_remove_akun, name='automasi_remove_akun'),
    path('automasi/<int:pk>/entry/', views.automasi_entry, name='automasi_entry'),

    # API
    path('api/akun-autocomplete/', views.akun_autocomplete, name='akun_autocomplete'),
]
