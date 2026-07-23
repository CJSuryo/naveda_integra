"""Test settings — uses SQLite for fast, zero-config local testing."""
from .base import *  # noqa: F401, F403

ALLOWED_HOSTS = ['*', 'testserver', 'localhost']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

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

# ── Celery ───────────────────────────────────────────────────────────────────
# Run tasks inline. Without this, every `.delay()` blocks trying to reach a
# Redis broker that is not running under test.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# ── Aggregator ───────────────────────────────────────────────────────────────
# A fixed key keeps ciphertexts stable across tests and independent of SECRET_KEY.
AGGREGATOR_ENCRYPTION_KEY = 'IEDpFCFbZ8oGa2ZM_hGGX1AyDBqRZbi5PZLmHtd3S3s='
AGGREGATOR_PUBLIC_BASE_URL = 'https://testserver.example.com'
