"""Shared rate-limiting helpers: client IP, ratelimit keys/rates, 429 rendering.

Topology: Cloudflare -> Render -> gunicorn. Cloudflare overwrites
`CF-Connecting-IP` on every request, so it is the trusted client IP *provided
the Render origin is only reachable through Cloudflare* (see deploy hardening
notes). If the header is absent we are likely being hit directly; fall back to
the rightmost X-Forwarded-For hop and log a warning.
"""
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger('naveda_integra.ratelimit')


def get_client_ip(request) -> str:
    """Return the best-effort real client IP. Never raises."""
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()

    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        logger.warning('CF-Connecting-IP missing; falling back to X-Forwarded-For '
                       '(possible direct-origin access)')
        # Rightmost hop is the one added by the closest trusted proxy.
        return xff.split(',')[-1].strip()

    return request.META.get('REMOTE_ADDR') or 'unknown'


def client_ip_key(group, request) -> str:
    """django-ratelimit `key` callable that buckets by real client IP."""
    return get_client_ip(request)


def rate_from(name: str):
    """Return a django-ratelimit `rate` callable reading settings.RATELIMIT_RATES.

    Using a callable (not a literal string) lets tests override_settings the
    rates without touching decorators.
    """
    def _rate(group, request):
        return settings.RATELIMIT_RATES[name]
    return _rate


def _wants_json(request) -> bool:
    if '/api/' in request.path:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept


def render_ratelimited(request, retry_after: int | None = None):
    """Smart 429: JSON for AJAX/api, styled HTML page for browsers."""
    if _wants_json(request):
        payload = {'error': 'rate_limited'}
        if retry_after is not None:
            payload['retry_after'] = retry_after
        resp = JsonResponse(payload, status=429)
    else:
        resp = render(request, '429.html', status=429)
    if retry_after is not None:
        resp['Retry-After'] = str(retry_after)
    return resp


def ratelimit_view(request, exception=None):
    """Target of settings.RATELIMIT_VIEW — called when a decorator blocks."""
    return render_ratelimited(request)


def axes_lockout_response(request, credentials=None):
    """Target of settings.AXES_LOCKOUT_CALLABLE — login lockout response."""
    return render_ratelimited(request)
