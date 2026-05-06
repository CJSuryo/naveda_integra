from django.urls import path
from . import views

app_name = 'pos_config'

urlpatterns = [
    path('config/<int:pk>/', views.merchant_config, name='merchant_config'),
    path('config/<int:merchant_pk>/stores/', views.store_list, name='store_list'),
    path('config/<int:merchant_pk>/stores/<int:lv2_pk>/', views.store_form, name='store_form'),
    path('config/store/<int:store_pk>/payments/', views.payment_method_list, name='payment_method_list'),
    path('config/store/<int:store_pk>/shifts/', views.shift_list, name='shift_list'),
]
