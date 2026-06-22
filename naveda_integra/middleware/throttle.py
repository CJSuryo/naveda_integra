"""Global per-IP request ceiling. Catch-all defense against crawlers/bots.

Counter is a Redis INCR with a 60s TTL per IP per minute-window. Fails open if
the cache backend errors (availability over strict limiting). Exempts staff,
static assets, and health checks.
"""
import logging
import time

from django.conf import settings
from django.core.cache import cache

from naveda_integra.ratelimit_utils import get_client_ip, render_ratelimited

logger = logging.getLogger('naveda_integra.ratelimit')

_EXEMPT_PREFIXES = ('/static/', '/media/', '/healthz', '/health')


class GlobalThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_throttle(request) and self._over_limit(request):
            return render_ratelimited(request, retry_after=60)
        return self.get_response(request)

    def _should_throttle(self, request) -> bool:
        if not getattr(settings, 'GLOBAL_THROTTLE_ENABLE', True):
            return False
        path = request.path
        if path.startswith(_EXEMPT_PREFIXES):
            return False
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_staff:
            return False
        return True

    def _over_limit(self, request) -> bool:
        limit = settings.RATELIMIT_RATES['global_ceiling_per_min']
        ip = get_client_ip(request)
        window = int(time.time() // 60)
        key = f'globthrottle:{ip}:{window}'
        try:
            count = cache.get_or_set(key, 0, timeout=60)
            # get_or_set returns the existing/just-set value; increment after.
            count = cache.incr(key)
        except ValueError:
            # incr on a missing key (race / eviction) — reset.
            cache.set(key, 1, timeout=60)
            count = 1
        except Exception:  # noqa: BLE001 — cache backend down => fail open
            logger.warning('Global throttle cache error; failing open', exc_info=True)
            return False
        return count > limit
