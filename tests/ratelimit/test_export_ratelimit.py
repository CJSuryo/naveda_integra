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
        email='bob@example.com',
        name='Bob',
        password='Strong-pass-12',
    )
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**django_settings.RATELIMIT_RATES, 'export': '1/m'})
def test_export_blocked_after_limit(logged_in_client):
    url = reverse('aset_tetap:export')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.90')
    first = logged_in_client.get(url, **headers)
    assert first.status_code in (200, 302)
    second = logged_in_client.get(url, **headers)
    assert second.status_code == 429
