import json
from unittest.mock import Mock

from django.test import RequestFactory

from naveda_integra.ratelimit_utils import render_ratelimited


def test_json_for_api_path():
    req = RequestFactory().post('/pos/api/orders/create/')
    req.user = Mock()
    resp = render_ratelimited(req, retry_after=42)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')
    body = json.loads(resp.content)
    assert body['error'] == 'rate_limited'
    assert body['retry_after'] == 42
    assert resp['Retry-After'] == '42'


def test_json_for_xhr_header():
    req = RequestFactory().get('/anything/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    req.user = Mock()
    resp = render_ratelimited(req)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')


def test_html_for_browser():
    req = RequestFactory().get('/login/', HTTP_ACCEPT='text/html')
    req.user = Mock()
    resp = render_ratelimited(req)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('text/html')
    assert b'429' in resp.content
