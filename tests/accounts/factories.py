"""Test factories for the accounts app."""
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(email='user@example.com', name='Test User', password='OldPass123!', **kwargs):
    user = User.objects.create_user(email=email, name=name, password=password, **kwargs)
    return user


def make_admin(email='admin@example.com', name='Admin', password='AdminPass123!'):
    return User.objects.create_superuser(email=email, name=name, password=password)
