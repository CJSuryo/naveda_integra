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
