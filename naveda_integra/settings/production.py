"""Production settings — Hetzner VPS deployment."""
import os

import dj_database_url

from .base import *  # noqa: F401, F403

# ── Core ─────────────────────────────────────────────────────────────────────
DEBUG = False
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# Custom domain
ALLOWED_HOSTS += ['navedafinance.com', 'www.navedafinance.com']

# ── Database (Neon.tech via DATABASE_URL) ────────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', ''),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ── Security hardening ───────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1')
# deploy.sh probes /healthz over plain HTTP from inside the container, where there
# is no TLS. Without this exemption Django answers 301 -> https, which `curl -f`
# reports as success — a healthcheck that passes even when the app is broken.
SECURE_REDIRECT_EXEMPT = [r'^healthz$']
SECURE_HSTS_SECONDS = 31_536_000       # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
] + ['https://navedafinance.com', 'https://www.navedafinance.com']

# ── Static + media files ─────────────────────────────────────────────────────
# Hetzner filesystem is persistent — media uploads survive across deploys.
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', '/home/deploy/apps/media')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# ── Logging (stdout for Render log streams) ──────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'production': {
            'format': '{asctime} {levelname} {name} {module}:{lineno} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'production',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'WARNING'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('LOG_LEVEL', 'WARNING'),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ── Remove debug toolbar in production ───────────────────────────────────────
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]  # noqa: F405
