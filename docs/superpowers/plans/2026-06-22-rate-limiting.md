# Rate Limiting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add layered rate limiting (login lockout, per-view throttles, global per-IP ceiling) to the Naveda Integra Django app, backed by Redis, with smart HTML/JSON 429 responses.

**Architecture:** Five isolated pieces — Redis cache backend, a single `get_client_ip` source-of-truth, `django-axes` for login brute-force lockout, `django-ratelimit` decorators on sensitive views, and a custom global per-IP throttle middleware. A shared smart-429 renderer serves HTML to browsers and JSON to AJAX/api callers.

**Tech Stack:** Django 6, `django-ratelimit`, `django-axes`, `django-redis`, Redis (`REDIS_URL`), pytest.

**Design spec:** `docs/superpowers/specs/2026-06-22-rate-limiting-design.md`

---

## Key conventions (read before starting)

- Tests run with `pytest` (config in `setup.cfg`, `DJANGO_SETTINGS_MODULE = naveda_integra.settings.test`).
- Run a single test: `python -m pytest tests/path::test_name -v`
- Settings are split: edit `naveda_integra/settings/base.py` for shared config, `test.py` for test overrides.
- Rate numbers live in `settings.RATELIMIT_RATES` (a dict). Decorators read them through a `rate_from(name)` callable so tests can `override_settings`.
- New shared code lives in package `naveda_integra/` (same level as `settings/`, `urls.py`).
- All client-IP reads go through `get_client_ip` — never read headers ad hoc.
- 429 templates use **external CSS only** (project rule — no inline styles).

## File structure

- Create `naveda_integra/ratelimit_utils.py` — `get_client_ip`, `client_ip_key`, `rate_from`, `render_ratelimited`, `ratelimit_view`, `axes_lockout_response`.
- Create `naveda_integra/middleware/__init__.py` and `naveda_integra/middleware/throttle.py` — `GlobalThrottleMiddleware`.
- Create `templates/429.html` and `static/css/error_429.css`.
- Modify `naveda_integra/settings/base.py` — CACHES, INSTALLED_APPS, MIDDLEWARE, AUTHENTICATION_BACKENDS, axes + ratelimit settings, `RATELIMIT_RATES`.
- Modify `naveda_integra/settings/test.py` — deterministic low limits, disable global middleware, LocMem cache.
- Modify `requirements.txt` — three deps.
- Modify `apps/accounts/views.py` — decorators on `login_view`, `register_view`, `password_change_request`.
- Modify the 9 `*_export*` views (apply shared decorator) and POS api/push views.
- Modify `render.yaml` — add `REDIS_URL` env var.
- Create tests under `tests/ratelimit/`.

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the three packages**

Add these lines to `requirements.txt` (after the existing `cryptography` line, keeping alphabetical-ish grouping is not required):

```
django-ratelimit>=4.1,<5.0
django-axes>=7.0,<8.0
django-redis>=5.4,<6.0
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: installs `django-ratelimit`, `django-axes`, `django-redis` with no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "build: add rate limiting deps (django-ratelimit, django-axes, django-redis)"
```

---

## Task 2: Redis cache backend + settings scaffolding

**Files:**
- Modify: `naveda_integra/settings/base.py`
- Modify: `naveda_integra/settings/test.py`

- [ ] **Step 1: Add CACHES + RATELIMIT_RATES to base.py**

Append to `naveda_integra/settings/base.py` (end of file):

```python
# ── Caching / rate-limit backend ─────────────────────────────────────────────
# Redis shared across all gunicorn workers. Falls back to LocMem when REDIS_URL
# is unset (dev without Redis) so the app still boots.
_REDIS_URL = os.environ.get('REDIS_URL', '')
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': _REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,  # fail open if Redis is down
            },
        }
    }
    DJANGO_REDIS_IGNORE_EXCEPTIONS = True
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# ── Rate limiting ────────────────────────────────────────────────────────────
# Central, tunable limits. Values are django-ratelimit "rate" strings
# ("count/period"); the global ceiling is an int (requests per minute).
RATELIMIT_RATES = {
    'login': '20/5m',                 # coarse IP limit layered over axes lockout
    'register': '5/h',                # per IP
    'password_change_request': '3/h', # per authenticated user
    'export': '10/m',                 # per authenticated user
    'pos_api': '120/m',               # per authenticated user
    'push_subscribe': '10/m',         # per authenticated user
    'global_ceiling_per_min': 300,    # per IP, enforced by middleware
}

# django-ratelimit: route blocked requests to our smart-429 view.
RATELIMIT_VIEW = 'naveda_integra.ratelimit_utils.ratelimit_view'
RATELIMIT_ENABLE = True
```

- [ ] **Step 2: Add test overrides to test.py**

Append to `naveda_integra/settings/test.py`:

```python
# Deterministic, low limits for tests. LocMem cache (no Redis needed).
CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

RATELIMIT_RATES = {
    'login': '2/5m',
    'register': '2/h',
    'password_change_request': '2/h',
    'export': '2/m',
    'pos_api': '3/m',
    'push_subscribe': '2/m',
    'global_ceiling_per_min': 5,
}

# Global throttle middleware is disabled by default in tests; individual tests
# enable it with override_settings(GLOBAL_THROTTLE_ENABLE=True).
GLOBAL_THROTTLE_ENABLE = False

# django-axes deterministic config for tests.
AXES_FAILURE_LIMIT = 2
AXES_ENABLED = True
```

- [ ] **Step 3: Verify settings import cleanly**

Run: `python -c "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','naveda_integra.settings.test'); django.setup(); from django.conf import settings; print(settings.RATELIMIT_RATES['login'])"`
Expected: prints `2/5m` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add naveda_integra/settings/base.py naveda_integra/settings/test.py
git commit -m "feat(ratelimit): add Redis cache backend and central rate config"
```

---

## Task 3: Client-IP extraction + key/rate helpers

**Files:**
- Create: `naveda_integra/ratelimit_utils.py`
- Create: `tests/ratelimit/__init__.py`
- Test: `tests/ratelimit/test_client_ip.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ratelimit/__init__.py` (empty file).

Create `tests/ratelimit/test_client_ip.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_client_ip.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'naveda_integra.ratelimit_utils'`.

- [ ] **Step 3: Create the module with get_client_ip (and the other helpers stubbed for later tasks)**

Create `naveda_integra/ratelimit_utils.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_client_ip.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add naveda_integra/ratelimit_utils.py tests/ratelimit/__init__.py tests/ratelimit/test_client_ip.py
git commit -m "feat(ratelimit): add get_client_ip and 429 helpers with tests"
```

---

## Task 4: Smart 429 renderer test + template

**Files:**
- Create: `templates/429.html`
- Create: `static/css/error_429.css`
- Test: `tests/ratelimit/test_render_429.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ratelimit/test_render_429.py`:

```python
import json

from django.test import RequestFactory

from naveda_integra.ratelimit_utils import render_ratelimited


def test_json_for_api_path():
    req = RequestFactory().post('/pos/api/orders/create/')
    resp = render_ratelimited(req, retry_after=42)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')
    body = json.loads(resp.content)
    assert body['error'] == 'rate_limited'
    assert body['retry_after'] == 42
    assert resp['Retry-After'] == '42'


def test_json_for_xhr_header():
    req = RequestFactory().get('/anything/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    resp = render_ratelimited(req)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')


def test_html_for_browser():
    req = RequestFactory().get('/login/', HTTP_ACCEPT='text/html')
    resp = render_ratelimited(req)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('text/html')
    assert b'429' in resp.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_render_429.py -v`
Expected: `test_html_for_browser` FAILS with `TemplateDoesNotExist: 429.html` (JSON tests should already pass from Task 3).

- [ ] **Step 3: Create the template and CSS**

Create `static/css/error_429.css`:

```css
.error429 {
    max-width: 32rem;
    margin: 6rem auto;
    padding: 2rem;
    text-align: center;
    font-family: system-ui, sans-serif;
}
.error429__code {
    font-size: 3rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}
.error429__msg {
    color: #555;
    line-height: 1.5;
}
```

Create `templates/429.html`:

```html
{% load static %}
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>429 — Terlalu Banyak Permintaan</title>
    <link rel="stylesheet" href="{% static 'css/error_429.css' %}">
</head>
<body>
    <div class="error429">
        <div class="error429__code">429</div>
        <p class="error429__msg">
            Terlalu banyak permintaan dari perangkat Anda.
            Mohon tunggu sebentar lalu coba lagi.
        </p>
    </div>
</body>
</html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_render_429.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add templates/429.html static/css/error_429.css tests/ratelimit/test_render_429.py
git commit -m "feat(ratelimit): add styled 429 page and smart-render tests"
```

---

## Task 5: Global per-IP throttle middleware

**Files:**
- Create: `naveda_integra/middleware/__init__.py`
- Create: `naveda_integra/middleware/throttle.py`
- Test: `tests/ratelimit/test_global_throttle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ratelimit/test_global_throttle.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_global_throttle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'naveda_integra.middleware'`.

- [ ] **Step 3: Implement the middleware**

Create `naveda_integra/middleware/__init__.py` (empty file).

Create `naveda_integra/middleware/throttle.py`:

```python
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
```

Note: `_EXEMPT_PREFIXES` is a tuple; `str.startswith(tuple)` matches any prefix. `request.user` may be absent because this middleware runs before `AuthenticationMiddleware` (see Task 7 ordering) — `getattr(..., None)` handles that, so staff exemption only applies once auth middleware has run; that is acceptable because the ceiling is high and staff rarely approach it on unauthenticated paths.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_global_throttle.py -v`
Expected: 4 passed.

- [ ] **Step 5: Wire middleware into base.py (disabled-by-default-safe)**

In `naveda_integra/settings/base.py`, change the `MIDDLEWARE` list (currently lines 65-75) to insert the throttle right after WhiteNoise:

```python
MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'naveda_integra.middleware.throttle.GlobalThrottleMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

Also add to `naveda_integra/settings/base.py` (near RATELIMIT settings):

```python
# Global throttle is on in real deployments; tests opt in per-case.
GLOBAL_THROTTLE_ENABLE = os.environ.get('GLOBAL_THROTTLE_ENABLE', 'True').lower() in ('true', '1', 'yes')
```

- [ ] **Step 6: Verify full suite still green**

Run: `python -m pytest tests/ratelimit/ -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add naveda_integra/middleware/ naveda_integra/settings/base.py tests/ratelimit/test_global_throttle.py
git commit -m "feat(ratelimit): add global per-IP throttle middleware"
```

---

## Task 6: django-axes login lockout

**Files:**
- Modify: `naveda_integra/settings/base.py`
- Test: `tests/ratelimit/test_axes_lockout.py`

- [ ] **Step 1: Wire axes into settings**

In `naveda_integra/settings/base.py`:

(a) Add `'axes'` to `INSTALLED_APPS` — append after `'apps.pos_reports',` (current line 62, before the closing `]` on line 63):

```python
    'apps.pos_reports',
    'axes',
]
```

(b) Add the axes middleware as the **last** entry of `MIDDLEWARE` (after `XFrameOptionsMiddleware`):

```python
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]
```

(c) Add `AUTHENTICATION_BACKENDS` (none exists today) and axes config. Place near the auth settings (after `LOGIN_REDIRECT_URL`, line 142):

```python
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',   # must be first
    'django.contrib.auth.backends.ModelBackend',
]

# ── django-axes (login brute-force lockout) ──────────────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # hours = 15 minutes
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']  # lock the pair, not all
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_CALLABLE = 'naveda_integra.ratelimit_utils.axes_lockout_response'
AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_CF_CONNECTING_IP', 'REMOTE_ADDR']
AXES_ENABLED = True
```

- [ ] **Step 2: Write the failing test**

Create `tests/ratelimit/test_axes_lockout.py`:

```python
import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='alice', password='Correct-horse-9')


@pytest.mark.django_db
@override_settings(AXES_FAILURE_LIMIT=2)
def test_locks_out_after_failed_attempts(user):
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.50')
    # Two wrong attempts reach the limit.
    c.post(url, {'username': 'alice', 'password': 'wrong'}, **headers)
    c.post(url, {'username': 'alice', 'password': 'wrong'}, **headers)
    # Third attempt (even with correct password) is locked out -> 429.
    resp = c.post(url, {'username': 'alice', 'password': 'Correct-horse-9'}, **headers)
    assert resp.status_code == 429


@pytest.mark.django_db
@override_settings(AXES_FAILURE_LIMIT=2)
def test_successful_login_before_limit_works(user):
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.51')
    c.post(url, {'username': 'alice', 'password': 'wrong'}, **headers)
    resp = c.post(url, {'username': 'alice', 'password': 'Correct-horse-9'}, **headers)
    assert resp.status_code in (302, 200)  # redirect to home on success
```

Note: confirm the login form field names are `username` / `password`. If `LoginForm` (Django `AuthenticationForm` subclass) uses different field names, adjust the POST dict accordingly. Verify with: `python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','naveda_integra.settings.test');django.setup();from apps.accounts.forms import LoginForm;print(list(LoginForm(None).fields))"`

- [ ] **Step 3: Run migrations for axes, then run test to verify behavior**

axes ships DB models. Run: `python -m pytest tests/ratelimit/test_axes_lockout.py -v`
Expected: both pass (pytest-django applies axes migrations to the test DB automatically). If a migration error appears, run `python manage.py migrate axes` against a scratch DB to confirm axes is installed correctly.

- [ ] **Step 4: Commit**

```bash
git add naveda_integra/settings/base.py tests/ratelimit/test_axes_lockout.py
git commit -m "feat(ratelimit): add django-axes login lockout with smart 429"
```

---

## Task 7: Ratelimit decorators on auth views

**Files:**
- Modify: `apps/accounts/views.py`
- Test: `tests/ratelimit/test_auth_views_ratelimit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ratelimit/test_auth_views_ratelimit.py`:

```python
import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**__import__('django').conf.settings.RATELIMIT_RATES,
                                    'register': '1/h'})
def test_register_blocked_after_limit():
    c = Client()
    url = reverse('accounts:register')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.70')
    c.post(url, {}, **headers)            # 1st POST counts
    resp = c.post(url, {}, **headers)     # 2nd POST blocked
    assert resp.status_code == 429


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**__import__('django').conf.settings.RATELIMIT_RATES,
                                    'login': '1/5m'})
def test_login_coarse_ip_limit():
    c = Client()
    url = reverse('accounts:login')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.71')
    c.post(url, {'username': 'x', 'password': 'y'}, **headers)
    resp = c.post(url, {'username': 'x', 'password': 'y'}, **headers)
    assert resp.status_code == 429
```

(If the `__import__` inline is awkward, replace with `from django.conf import settings` at top and build the dict in a local variable before the decorator — but `override_settings` needs the dict at decoration time, so the inline merge keeps existing keys present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_auth_views_ratelimit.py -v`
Expected: FAIL — both return 200/302 (no limiting yet), assertion error on 429.

- [ ] **Step 3: Add decorators to the views**

In `apps/accounts/views.py`, add imports near the top (after line 10):

```python
from django_ratelimit.decorators import ratelimit

from naveda_integra.ratelimit_utils import client_ip_key, rate_from
```

Decorate `login_view` (currently line 58):

```python
@ratelimit(key=client_ip_key, rate=rate_from('login'), method='POST', block=True)
def login_view(request: HttpRequest) -> HttpResponse:
```

Decorate `register_view` (currently line 78):

```python
@ratelimit(key=client_ip_key, rate=rate_from('register'), method='POST', block=True)
def register_view(request: HttpRequest) -> HttpResponse:
```

Decorate `password_change_request` (currently line 89) — keep `@login_required` outermost, key on the authenticated user:

```python
@login_required
@ratelimit(key='user', rate=rate_from('password_change_request'), method='POST', block=True)
def password_change_request(request: HttpRequest) -> HttpResponse:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_auth_views_ratelimit.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/views.py tests/ratelimit/test_auth_views_ratelimit.py
git commit -m "feat(ratelimit): throttle login, register, password-change-request"
```

---

## Task 8: Ratelimit decorators on export views

**Files:**
- Modify: the 9 export views across apps (each `*_export` / `*_export_pdf`)
- Test: `tests/ratelimit/test_export_ratelimit.py`

The export views live in: `apps/aset_lainnya/views.py`, `apps/aset_tetap/views.py`, `apps/ekuitas/views.py`, `apps/entitas_bisnis/views.py`, and any others surfaced by the search command below. Find them all first.

- [ ] **Step 1: Enumerate every export view**

Run: `python -m pytest --collect-only -q >/dev/null 2>&1; grep -rln "def .*_export" apps/*/views.py`
Expected: a list of files. Open each and confirm the exact function names (`grep -n "def .*_export" <file>`).

- [ ] **Step 2: Write the failing test (use aset_tetap export as representative)**

Create `tests/ratelimit/test_export_ratelimit.py`:

```python
import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def logged_in_client(db):
    user = User.objects.create_user(username='bob', password='Strong-pass-12')
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**__import__('django').conf.settings.RATELIMIT_RATES,
                                    'export': '1/m'})
def test_export_blocked_after_limit(logged_in_client):
    # Use the aset_tetap export URL; adjust name if the URL namespace differs.
    url = reverse('aset_tetap:export')
    headers = dict(HTTP_CF_CONNECTING_IP='203.0.113.90')
    first = logged_in_client.get(url, **headers)
    assert first.status_code in (200, 302)
    second = logged_in_client.get(url, **headers)
    assert second.status_code == 429
```

Verify the URL name with: `grep -n "name='export'" apps/aset_tetap/urls.py` and the namespace via `app_name` in that file. Adjust `reverse('aset_tetap:export')` if needed.

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_export_ratelimit.py -v`
Expected: FAIL — second request returns 200 (no limit yet).

- [ ] **Step 4: Decorate every export view**

For EACH export view function found in Step 1, add the decorator (key on user since exports require login). Example for `apps/aset_tetap/views.py`:

Add imports at the top of each modified views file (if not already present):

```python
from django_ratelimit.decorators import ratelimit

from naveda_integra.ratelimit_utils import rate_from
```

Decorate each export function:

```python
@ratelimit(key='user', rate=rate_from('export'), method='GET', block=True)
def aset_tetap_export(request: HttpRequest) -> HttpResponse:
    ...

@ratelimit(key='user', rate=rate_from('export'), method='GET', block=True)
def aset_tetap_export_pdf(request: HttpRequest) -> HttpResponse:
    ...
```

Apply the same two-line decorator to every `*_export` and `*_export_pdf` function in every file from Step 1. If an export function is already wrapped by `@login_required` or a permission decorator, place `@ratelimit` **below** those (so auth runs first).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_export_ratelimit.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/*/views.py tests/ratelimit/test_export_ratelimit.py
git commit -m "feat(ratelimit): throttle Excel/PDF export endpoints per user"
```

---

## Task 9: Ratelimit POS api + push subscribe

**Files:**
- Modify: `apps/pos_orders/views.py`
- Test: `tests/ratelimit/test_pos_ratelimit.py`

- [ ] **Step 1: Identify the POS api + push functions**

Run: `grep -n "def api_\|def push_subscribe" apps/pos_orders/views.py`
Expected: `api_create_order`, `api_add_item`, `api_remove_item`, `api_update_qty`, `api_submit_order`, `api_process_payment`, `api_confirm_payment`, `api_complete_order`, `api_cancel_order`, `push_subscribe`.

- [ ] **Step 2: Write the failing test**

Create `tests/ratelimit/test_pos_ratelimit.py`:

```python
import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def logged_in_client(db):
    user = User.objects.create_user(username='cara', password='Strong-pass-12')
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
@override_settings(RATELIMIT_RATES={**__import__('django').conf.settings.RATELIMIT_RATES,
                                    'pos_api': '1/m'})
def test_pos_api_create_blocked_after_limit(logged_in_client):
    url = reverse('pos_orders:api_create_order')
    headers = dict(HTTP_X_REQUESTED_WITH='XMLHttpRequest', HTTP_CF_CONNECTING_IP='203.0.113.95')
    logged_in_client.post(url, {}, content_type='application/json', **headers)
    resp = logged_in_client.post(url, {}, content_type='application/json', **headers)
    assert resp.status_code == 429
    assert resp['Content-Type'].startswith('application/json')
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/ratelimit/test_pos_ratelimit.py -v`
Expected: FAIL — second request not 429.

- [ ] **Step 4: Decorate the POS api + push views**

In `apps/pos_orders/views.py`, add imports:

```python
from django_ratelimit.decorators import ratelimit

from naveda_integra.ratelimit_utils import rate_from
```

For EACH of the nine `api_*` functions, add below the existing decorators (these views already have `@login_required` / `@require_POST` — keep `@ratelimit` innermost, directly above `def`):

```python
@ratelimit(key='user', rate=rate_from('pos_api'), method='POST', block=True)
def api_create_order(request, ...):
    ...
```

For `push_subscribe` (already `@login_required @require_POST`):

```python
@ratelimit(key='user', rate=rate_from('push_subscribe'), method='POST', block=True)
def push_subscribe(request, store_id):
    ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/ratelimit/test_pos_ratelimit.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/pos_orders/views.py tests/ratelimit/test_pos_ratelimit.py
git commit -m "feat(ratelimit): throttle POS api endpoints and push subscribe"
```

---

## Task 10: Deploy config + hardening docs

**Files:**
- Modify: `render.yaml`
- Create: `docs/rate-limiting-ops.md`

- [ ] **Step 1: Add REDIS_URL to render.yaml web service env**

In `render.yaml`, under the web service `envVars:` list, add:

```yaml
      - key: REDIS_URL
        sync: false          # Redis connection string (e.g. Render Key Value / Upstash)
      - key: GLOBAL_THROTTLE_ENABLE
        value: "True"
```

Note: the app falls back to LocMem cache if `REDIS_URL` is unset, but per-worker counters then diverge across the 4 gunicorn workers — set a real Redis URL in production.

- [ ] **Step 2: Write the ops/hardening doc**

Create `docs/rate-limiting-ops.md`:

```markdown
# Rate Limiting — Operations & Hardening

## Tuning limits
All limits live in `RATELIMIT_RATES` in `naveda_integra/settings/base.py`.
Change values there; no code changes needed. Format is django-ratelimit
"count/period" (e.g. `5/h`, `120/m`); the global ceiling is an int (req/min).

## Components
- **django-axes** — login lockout (5 fails / 15 min per username+IP). Unlock a
  user manually: `python manage.py axes_reset` (all) or
  `python manage.py axes_reset_username <name>`.
- **django-ratelimit** — per-view decorators (login coarse, register,
  password-change-request, exports, POS api, push).
- **GlobalThrottleMiddleware** — 300 req/min/IP catch-all. Toggle with env
  `GLOBAL_THROTTLE_ENABLE`.

## Client IP trust (IMPORTANT)
Real client IP is read from `CF-Connecting-IP` (Cloudflare). This is only
trustworthy if the Render origin is reachable **exclusively** through
Cloudflare. Hardening: restrict the Render service to Cloudflare's published
IP ranges (https://www.cloudflare.com/ips/). Without this, an attacker hitting
the origin directly and spoofing `CF-Connecting-IP` could evade IP-based limits.

## Redis failure behavior
If Redis is unavailable, ratelimit + global throttle **fail open** (requests
allowed, warnings logged). Axes uses the database, so login lockout still
enforces during a Redis outage.

## Future infra layer
Enable Cloudflare WAF / rate-limiting rules at the edge for a third defense
layer in front of the application.
```

- [ ] **Step 3: Commit**

```bash
git add render.yaml docs/rate-limiting-ops.md
git commit -m "docs(ratelimit): add ops/hardening guide and REDIS_URL deploy config"
```

---

## Task 11: Full suite + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -q`
Expected: all tests pass (ratelimit suite + existing suites). Investigate any failure before proceeding.

- [ ] **Step 2: Manual smoke (optional, requires Redis running locally)**

```bash
# with REDIS_URL set and DEBUG settings
python manage.py runserver
```
Then: hit `/login/` with wrong credentials 6 times → expect a 429 HTML page;
hit a POS `/api/` endpoint rapidly while logged in → expect JSON `{"error":"rate_limited"}` with status 429.

- [ ] **Step 3: Final commit (if any cleanup)**

```bash
git add -A
git commit -m "chore(ratelimit): finalize rate limiting implementation"
```

---

## Self-review notes (addressed)

- **Spec coverage:** Redis backend (T2), get_client_ip/CF-IP (T3), smart 429 (T3/T4), axes login lockout (T6), ratelimit auth/export/POS/push (T7/T8/T9), global ceiling middleware (T5), fail-open (T5 code), hardening + Cloudflare IP restriction (T10). All spec sections mapped.
- **Refinement vs spec:** `password_change_request` is `@login_required`, so it is keyed on `user` (not IP+email as the spec table drafted) — lower enumeration risk, simpler. Documented in T7.
- **Type/name consistency:** `get_client_ip`, `client_ip_key`, `rate_from`, `render_ratelimited`, `ratelimit_view`, `axes_lockout_response` defined once in T3 and referenced consistently in settings (T2/T5/T6) and views (T7/T8/T9).
- **Middleware ordering:** GlobalThrottle after WhiteNoise (cheap, pre-session); AxesMiddleware last. `request.user` may be unset in throttle — handled with `getattr`.
```
