import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings as django_settings

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def logged_in_client(db):
    user = User.objects.create_user(
        email='cara@example.com',
        name='Cara',
        password='Strong-pass-12',
    )
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**django_settings.RATELIMIT_RATES, 'pos_api': '1/m'})
def test_pos_api_create_blocked_after_limit(logged_in_client):
    url = reverse('pos_orders:api_create_order')
    headers = dict(HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_CF_CONNECTING_IP='203.0.113.95')
    logged_in_client.post(url, {}, content_type='application/json', **headers)
    resp = logged_in_client.post(url, {}, content_type='application/json', **headers)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')
