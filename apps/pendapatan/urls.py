from django.urls import path
from . import views

app_name = 'pendapatan'

urlpatterns = [
    path('', views.pendapatan_dashboard, name='dashboard'),
    path('list/', views.pendapatan_list, name='list'),
    path('create/', views.pendapatan_create, name='create'),
    path('<int:pk>/', views.pendapatan_detail, name='detail'),
    path('<int:pk>/edit/', views.pendapatan_edit, name='edit'),
    path('<int:pk>/confirm/', views.pendapatan_confirm, name='confirm'),
    path('<int:pk>/void/', views.pendapatan_void, name='void'),
    path('api/stt-defaults/', views.stt_defaults, name='stt_defaults'),
    # Recurring Templates
    path('recurring/', views.recurring_list, name='recurring_list'),
    path('recurring/create/', views.recurring_create, name='recurring_create'),
    path('recurring/<int:pk>/', views.recurring_detail, name='recurring_detail'),
    path('recurring/<int:pk>/edit/', views.recurring_edit, name='recurring_edit'),
    path('recurring/<int:pk>/delete/', views.recurring_delete, name='recurring_delete'),
    path('recurring/<int:pk>/generate/', views.recurring_generate, name='recurring_generate'),
    path('reports/recurring/', views.recurring_calendar, name='recurring_calendar'),
]
