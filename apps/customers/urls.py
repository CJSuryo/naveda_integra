# apps/customers/urls.py
from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('', views.customer_list, name='list'),
    path('tambah/', views.customer_create, name='create'),
    path('<int:pk>/edit/', views.customer_update, name='update'),
    path('<int:pk>/hapus/', views.customer_delete, name='delete'),
    path('quick-create/', views.customer_quick_create, name='quick_create'),
]
