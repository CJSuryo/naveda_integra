from django.urls import path
from . import views

app_name = 'pos_catalog'

urlpatterns = [
    path('<int:merchant_pk>/products/', views.product_list, name='product_list'),
    path('<int:merchant_pk>/products/create/', views.product_create, name='product_create'),
    path('<int:merchant_pk>/products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('<int:merchant_pk>/modifiers/', views.modifier_group_list, name='modifier_group_list'),
    path('<int:merchant_pk>/modifiers/create/', views.modifier_group_form, name='modifier_group_create'),
    path('<int:merchant_pk>/modifiers/<int:pk>/edit/', views.modifier_group_form, name='modifier_group_edit'),
    path('<int:merchant_pk>/modifiers/<int:group_pk>/options/', views.modifier_option_create, name='modifier_option_create'),
]
