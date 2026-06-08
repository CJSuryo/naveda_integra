from django.urls import path
from . import views

app_name = 'pendapatan'

urlpatterns = [
    path('api/stt-defaults/', views.stt_defaults, name='stt_defaults'),
]
