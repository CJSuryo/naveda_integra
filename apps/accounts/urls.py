"""Account URLs."""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    # User CRUD
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/edit/', views.user_update, name='user_update'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/permissions/', views.user_permissions, name='user_permissions'),
    path('users/<int:pk>/eb-access/', views.user_eb_access, name='user_eb_access'),
    # Email-verified password change (own account only)
    path('password-change/request/', views.password_change_request, name='password_change_request'),
    path('password-change/<uidb64>/<token>/', views.password_change_confirm, name='password_change_confirm'),
]
