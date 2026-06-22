from django.test import RequestFactory

from naveda_integra.ratelimit_utils import get_client_ip


def _req(**headers):
    rf = RequestFactory()
    return rf.get('/', **headers)


def test_prefers_cf_connecting_ip():
    req = _req(HTTP_CF_CONNECTING_IP='203.0.113.7',
               HTTP_X_FORWARDED_FOR='10.0.0.1, 198.51.100.9',
               REMOTE_ADDR='10.0.0.1')
    assert get_client_ip(req) == '203.0.113.7'


def test_falls_back_to_rightmost_xff_when_no_cf_header():
    req = _req(HTTP_X_FORWARDED_FOR='198.51.100.9, 203.0.113.7',
               REMOTE_ADDR='10.0.0.1')
    assert get_client_ip(req) == '203.0.113.7'


def test_falls_back_to_remote_addr():
    req = _req(REMOTE_ADDR='192.0.2.55')
    assert get_client_ip(req) == '192.0.2.55'


def test_unknown_when_nothing_present():
    req = _req()
    req.META.pop('REMOTE_ADDR', None)
    assert get_client_ip(req) == 'unknown'
