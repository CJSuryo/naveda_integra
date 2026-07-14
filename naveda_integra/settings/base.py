"""
Base Django settings for naveda_integra project.
"""

import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Allow apps in the `apps/` subdirectory to be imported by their short label
# (e.g. `pos_config` instead of `apps.pos_config`).
_APPS_DIR = str(BASE_DIR / 'apps')
if _APPS_DIR not in sys.path:
    sys.path.insert(0, _APPS_DIR)

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-%yrhd^ezay#5bkcv+6&yn3iq*1x42#dafmvep%he%h)q&k^j1@',
)

DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS: list[str] = os.environ.get('ALLOWED_HOSTS', '').split(',') if os.environ.get('ALLOWED_HOSTS') else []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Third-party
    'django_extensions',
    'debug_toolbar',
    # Local apps
    'apps.accounts',
    'apps.entitas_bisnis',
    'apps.master_data',
    'apps.jurnal',
    'apps.sales',
    'apps.piutang',
    'apps.pendapatan',
    'apps.inventory',
    'apps.purchase',
    'apps.utang',
    'apps.pajak',
    'apps.aset_tetap',
    'apps.aset_lainnya',
    'apps.ekuitas',
    'apps.manufacturing',
    'apps.dashboard',
    'apps.customers',
    'apps.posting',
    'pos_config',
    'pos_catalog',
    'pos_orders',
    'apps.pos_crm',
    'apps.pos_promotions',
    'apps.pos_reports',
    'axes',
]

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'naveda_integra.middleware.security_headers.SecurityHeadersMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'naveda_integra.middleware.throttle.GlobalThrottleMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
    'django_ratelimit.middleware.RatelimitMiddleware',
]

ROOT_URLCONF = 'naveda_integra.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.pos_config.context_processors.pos_nav_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'naveda_integra.wsgi.application'

# Database — prefers DATABASE_URL (for Neon/Render/Heroku), falls back to
# individual DB_* env vars, then to local PostgreSQL defaults.
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get(
            'DATABASE_URL',
            'postgres://{user}:{password}@{host}:{port}/{name}'.format(
                user=os.environ.get('DB_USER', 'postgres'),
                password=os.environ.get('DB_PASSWORD', ''),
                host=os.environ.get('DB_HOST', 'localhost'),
                port=os.environ.get('DB_PORT', '5432'),
                name=os.environ.get('DB_NAME', 'naveda_integra'),
            ),
        ),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=bool(os.environ.get('DATABASE_URL')),
    )
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'id'
TIME_ZONE = 'Asia/Jakarta'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/home/'
LOGOUT_REDIRECT_URL = '/login/'

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

# ── Security headers (apply in every environment via SecurityMiddleware) ─────
# X-Content-Type-Options: nosniff — stop browsers MIME-sniffing responses.
SECURE_CONTENT_TYPE_NOSNIFF = True

# Permissions-Policy — deny browser features the app never uses. The POS only
# needs service-worker push/notifications, which are not gated here. Emitted by
# naveda_integra.middleware.security_headers.SecurityHeadersMiddleware.
PERMISSIONS_POLICY = (
    'camera=(), microphone=(), geolocation=(), usb=(), bluetooth=(), '
    'payment=(), magnetometer=(), gyroscope=(), accelerometer=()'
)

INTERNAL_IPS = ['127.0.0.1']

SHELL_PLUS = 'ipython'
SHELL_PLUS_PRINT_SQL = True

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {module}:{lineno} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}

# POS Web Push (VAPID)
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'push@naveda.id')

# Django Channels — Redis channel layer
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [os.environ.get("REDIS_URL", "redis://localhost:6379")]},
    }
}

# ── Email + password-change link ─────────────────────────────────────────────
PASSWORD_RESET_TIMEOUT = 900  # 15 min — governs the password-change link

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Naveda Finance <noreply@navedafinance.com>')
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

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

# Global throttle is on in real deployments; tests opt in per-case.
GLOBAL_THROTTLE_ENABLE = os.environ.get('GLOBAL_THROTTLE_ENABLE', 'True').lower() in ('true', '1', 'yes')
