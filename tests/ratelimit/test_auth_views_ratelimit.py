import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.conf import settings as django_settings


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**django_settings.RATELIMIT_RATES, 'register': '1/h'})
def test_register_blocked_after_limit():
    c = Client()
    url = reverse('accounts:register')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.70')
    c.post(url, {}, **headers)            # 1st POST counts
    resp = c.post(url, {}, **headers)     # 2nd POST blocked
    assert resp.status_code == 429


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**django_settings.RATELIMIT_RATES, 'login': '1/5m'})
def test_login_coarse_ip_limit():
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.71')
    c.post(url, {'username': 'nonexistent@example.com', 'password': 'y'}, **headers)
    resp = c.post(url, {'username': 'nonexistent@example.com', 'password': 'y'}, **headers)
    assert resp.status_code == 429
