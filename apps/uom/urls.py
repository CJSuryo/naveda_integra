from django.urls import path

from . import views

app_name = 'uom'

urlpatterns = [
    path('', views.unit_list, name='list'),
    path('create/', views.unit_create, name='create'),
    path('<int:pk>/edit/', views.unit_update, name='update'),
    path('konversi/', views.conversion_list, name='conversion_list'),
    path('konversi/create/', views.conversion_create, name='conversion_create'),
    path('konversi/<int:pk>/edit/', views.conversion_update, name='conversion_update'),
    path('konversi/<int:pk>/delete/', views.conversion_delete, name='conversion_delete'),
]
