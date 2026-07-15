from django.urls import path

from . import views

app_name = 'uom'

urlpatterns = [
    path('', views.unit_list, name='list'),
    path('create/', views.unit_create, name='create'),
    path('<int:pk>/edit/', views.unit_update, name='update'),
]
