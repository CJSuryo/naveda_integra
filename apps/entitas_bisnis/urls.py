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
    # Entitas Bisnis (Level 1)
    path('', views.list_view, name='list'),
    path('<int:pk>/', views.detail_view, name='detail'),
    path('create/', views.create_view, name='create'),
    path('<int:pk>/edit/', views.update_view, name='update'),
    path('<int:pk>/delete/', views.delete_view, name='delete'),
    path('<int:pk>/setup/', views.setup_wizard, name='setup_wizard'),
    # Entitas Bisnis Level 2
    path('<int:eb_pk>/lv2/create/', views.lv2_create, name='lv2_create'),
    path('<int:eb_pk>/lv2/<int:pk>/', views.lv2_detail, name='lv2_detail'),
    path('<int:eb_pk>/lv2/<int:pk>/edit/', views.lv2_update, name='lv2_update'),
    path('<int:eb_pk>/lv2/<int:pk>/delete/', views.lv2_delete, name='lv2_delete'),
    # Entitas Bisnis Level 3
    path('<int:eb_pk>/lv2/<int:lv2_pk>/lv3/create/', views.lv3_create, name='lv3_create'),
    path('<int:eb_pk>/lv2/<int:lv2_pk>/lv3/<int:pk>/edit/', views.lv3_update, name='lv3_update'),
    path('<int:eb_pk>/lv2/<int:lv2_pk>/lv3/<int:pk>/delete/', views.lv3_delete, name='lv3_delete'),
]
