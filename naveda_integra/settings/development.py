"""Development settings — defaults to SQLite for zero-setup local dev."""
from .base import *  # noqa: F401, F403
import os
from pathlib import Path

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use SQLite locally unless explicit DB_ENGINE env var is set.
if not os.environ.get('DB_ENGINE'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': Path(__file__).resolve().parent.parent.parent / 'db.sqlite3',
        }
    }
