from django.urls import path

from . import views

app_name = 'utang'

urlpatterns = [
    path('', views.utang_list, name='list'),
    path('create/', views.utang_create, name='create'),
    path('<int:pk>/', views.utang_detail, name='detail'),
    path('<int:pk>/edit/', views.utang_update, name='update'),
    path('<int:pk>/delete/', views.utang_delete, name='delete'),
    path('<int:pk>/bayar/', views.utang_pay, name='pay'),
]