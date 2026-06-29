"""Root URL configuration — landing page, app home, and top-level login."""
from django.urls import path
from apps.accounts.views import home_view, landing_view, login_view, terms_view

urlpatterns = [
    path('', landing_view, name='landing'),
    path('home/', home_view, name='home'),
    path('login/', login_view, name='login'),
    path('terms/', terms_view, name='terms'),
]
