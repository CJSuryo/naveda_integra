from django.urls import path
from . import views

app_name = 'pos_catalog'

urlpatterns = [
    path('<int:merchant_pk>/modifiers/', views.modifier_group_list, name='modifier_group_list'),
    path('<int:merchant_pk>/modifiers/create/', views.modifier_group_form, name='modifier_group_create'),
    path('<int:merchant_pk>/modifiers/<int:pk>/edit/', views.modifier_group_form, name='modifier_group_edit'),
    path('<int:merchant_pk>/modifiers/<int:group_pk>/options/', views.modifier_option_create, name='modifier_option_create'),

    # Catalog
    path('<int:eb_pk>/catalog/', views.catalog_list, name='catalog_list'),
    path('<int:eb_pk>/catalog/items/', views.catalog_items_ajax, name='catalog_items_ajax'),
    path('<int:eb_pk>/catalog/items/upsert/', views.catalog_upsert, name='catalog_upsert'),
    path('<int:eb_pk>/catalog/logs/', views.catalog_logs, name='catalog_logs'),
]
