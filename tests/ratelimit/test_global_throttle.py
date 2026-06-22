import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from naveda_integra.middleware.throttle import GlobalThrottleMiddleware


def _ok_view(request):
    from django.http import HttpResponse
    return HttpResponse('ok')


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(GLOBAL_THROTTLE_ENABLE=True,
                   RATELIMIT_RATES={'global_ceiling_per_min': 3})
def test_blocks_after_ceiling():
    mw = GlobalThrottleMiddleware(_ok_view)
    rf = RequestFactory()
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.1')
    for _ in range(3):
        assert mw(rf.get('/x/', **headers)).status_code == 200
    assert mw(rf.get('/x/', **headers)).status_code == 429


@override_settings(GLOBAL_THROTTLE_ENABLE=True,
                   RATELIMIT_RATES={'global_ceiling_per_min': 1})
def test_separate_ips_have_separate_buckets():
    mw = GlobalThrottleMiddleware(_ok_view)
    rf = RequestFactory()
    assert mw(rf.get('/x/', HTTP_CF_CONNECTING_IP='203.0.113.1')).status_code == 200
    # different IP, fresh bucket
    assert mw(rf.get('/x/', HTTP_CF_CONNECTING_IP='203.0.113.2')).status_code == 200


@override_settings(GLOBAL_THROTTLE_ENABLE=True,
                   RATELIMIT_RATES={'global_ceiling_per_min': 1})
def test_static_path_is_exempt():
    mw = GlobalThrottleMiddleware(_ok_view)
    rf = RequestFactory()
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.1')
    assert mw(rf.get('/static/css/x.css', **headers)).status_code == 200
    assert mw(rf.get('/static/css/y.css', **headers)).status_code == 200


@override_settings(GLOBAL_THROTTLE_ENABLE=False,
                   RATELIMIT_RATES={'global_ceiling_per_min': 1})
def test_disabled_passes_through():
    mw = GlobalThrottleMiddleware(_ok_view)
    rf = RequestFactory()
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.1')
    assert mw(rf.get('/x/', **headers)).status_code == 200
    assert mw(rf.get('/x/', **headers)).status_code == 200
