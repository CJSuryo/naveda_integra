"""EntitasBisnis URLs."""
from django.urls import path
from . import views

app_name = 'entitas_bisnis'

urlpatterns = [
    # Tipe Entitas
    path('tipe-entitas/', views.tipe_entitas_list, name='tipe_entitas_list'),
    path('tipe-entitas/create/', views.tipe_entitas_create, name='tipe_entitas_create'),
    path('tipe-entitas/<int:pk>/edit/', views.tipe_entitas_update, name='tipe_entitas_update'),
    path('tipe-entitas/<int:pk>/delete/', views.tipe_entitas_delete, name='tipe_entitas_delete'),
    # Entitas Bisnis
    path('', views.list_view, name='list'),
    path('<int:pk>/', views.detail_view, name='detail'),
    path('create/', views.create_view, name='create'),
    path('<int:pk>/edit/', views.update_view, name='update'),
    path('<int:pk>/delete/', views.delete_view, name='delete'),
    # Cabang Entitas Bisnis
    path('<int:eb_pk>/cabang/create/', views.cabang_create, name='cabang_create'),
    path('<int:eb_pk>/cabang/<int:pk>/edit/', views.cabang_update, name='cabang_update'),
    path('<int:eb_pk>/cabang/<int:pk>/delete/', views.cabang_delete, name='cabang_delete'),
]
