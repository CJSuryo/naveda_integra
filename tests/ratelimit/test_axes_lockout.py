import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(email='alice@example.com', password='Correct-horse-9', name='Alice')


@pytest.mark.django_db
@override_settings(AXES_FAILURE_LIMIT=2)
def test_locks_out_after_failed_attempts(user):
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.50')
    # Two wrong attempts reach the limit.
    c.post(url, {'username': 'alice@example.com', 'password': 'wrong'}, **headers)
    c.post(url, {'username': 'alice@example.com', 'password': 'wrong'}, **headers)
    # Third attempt (even with correct password) is locked out -> 429.
    resp = c.post(url, {'username': 'alice@example.com', 'password': 'Correct-horse-9'}, **headers)
    assert resp.status_code == 429


@pytest.mark.django_db
@override_settings(AXES_FAILURE_LIMIT=2)
def test_successful_login_before_limit_works(user):
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.51')
    c.post(url, {'username': 'alice@example.com', 'password': 'wrong'}, **headers)
    resp = c.post(url, {'username': 'alice@example.com', 'password': 'Correct-horse-9'}, **headers)
    assert resp.status_code in (302, 200)  # redirect to home on success
