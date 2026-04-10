"""EntitasBisnis URLs."""
from django.urls import path
from . import views

app_name = 'entitas_bisnis'

urlpatterns = [
    path('', views.list_view, name='list'),
    path('<int:pk>/', views.detail_view, name='detail'),
    path('create/', views.create_view, name='create'),
    path('<int:pk>/edit/', views.update_view, name='update'),
    path('<int:pk>/delete/', views.delete_view, name='delete'),
]
