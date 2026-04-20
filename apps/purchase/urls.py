"""Purchase URLs."""
from django.urls import path
from . import views

app_name = 'purchase'

urlpatterns = [
    # Purchase transactions
    path('', views.purchase_list, name='list'),
    path('export/', views.purchase_export, name='export'),
    path('create/', views.purchase_create, name='create'),
    path('<int:pk>/', views.purchase_detail, name='detail'),
    path('<int:pk>/edit/', views.purchase_update, name='update'),
    path('<int:pk>/delete/', views.purchase_delete, name='delete'),

    # Item Master — 3 separate pages
    path('persediaan/', views.persediaan_list, name='persediaan_list'),
    path('aset-tetap/', views.aset_tetap_list, name='aset_tetap_list'),
    path('aset-lainnya/', views.aset_lainnya_list, name='aset_lainnya_list'),
    # Backward compat redirect
    path('item-master/', views.item_master_list, name='item_master_list'),
    # Shared create/update/delete (page param determines context)
    path('item-master/create/', views.item_master_create, name='item_master_create'),
    path('item-master/<int:pk>/edit/', views.item_master_update, name='item_master_update'),
    path('item-master/<int:pk>/delete/', views.item_master_delete, name='item_master_delete'),

    # Kategori Item
    path('kategori/', views.kategori_list, name='kategori_list'),
    path('kategori/create/', views.kategori_create, name='kategori_create'),
    path('kategori/<int:pk>/edit/', views.kategori_update, name='kategori_update'),
    path('kategori/<int:pk>/delete/', views.kategori_delete, name='kategori_delete'),

    # Settings (Sub-Transaction Type)
    path('settings/', views.settings_list, name='settings_list'),
    path('settings/create/', views.settings_create, name='settings_create'),
    path('settings/<int:pk>/edit/', views.settings_update, name='settings_update'),
    path('settings/<int:pk>/delete/', views.settings_delete, name='settings_delete'),

    # Available Akun per Entitas Bisnis Settings
    path('settings/akun/', views.akun_settings, name='akun_settings'),
    path('api/akun-settings-save/', views.akun_settings_save, name='akun_settings_save'),

    # API endpoints
    path('api/item-autocomplete/', views.api_item_autocomplete, name='api_item_autocomplete'),
    path('api/item-create/', views.api_item_create, name='api_item_create'),
    path('api/stt-offset/', views.api_stt_offset, name='api_stt_offset'),
    path('api/journal-preview/', views.journal_preview, name='api_journal_preview'),
    path('api/kategori-filter/', views.api_kategori_filter, name='api_kategori_filter'),
    path('api/kategori-create/', views.api_kategori_create, name='api_kategori_create'),
]
