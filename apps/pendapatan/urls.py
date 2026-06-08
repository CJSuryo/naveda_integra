from django.urls import path
from . import views

app_name = 'pendapatan'

urlpatterns = [
    path('', views.pendapatan_dashboard, name='dashboard'),
    path('list/', views.pendapatan_list, name='list'),
    path('create/', views.pendapatan_create, name='create'),
    path('<int:pk>/', views.pendapatan_detail, name='detail'),
    path('<int:pk>/confirm/', views.pendapatan_confirm, name='confirm'),
    path('<int:pk>/void/', views.pendapatan_void, name='void'),
    path('api/stt-defaults/', views.stt_defaults, name='stt_defaults'),
]
