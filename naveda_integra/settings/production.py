"""Production settings — Render.com + Neon.tech cloud deployment."""
import os

import dj_database_url

from .base import *  # noqa: F401, F403

# ── Core ─────────────────────────────────────────────────────────────────────
DEBUG = False
SECRET_KEY = os.environ['SECRET_KEY']
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# Render sets RENDER_EXTERNAL_HOSTNAME automatically.
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Custom domain
ALLOWED_HOSTS += ['navedafinance.com', 'www.navedafinance.com']

# ── Database (Neon.tech via DATABASE_URL) ────────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', ''),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
}

# ── Security hardening ───────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1')
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
# Render filesystem is ephemeral — media uploads survive only until next deploy.
# For persistent uploads, replace the 'default' backend with S3/Cloudinary.
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
