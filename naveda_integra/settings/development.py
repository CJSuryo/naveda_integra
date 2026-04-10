"""Development settings — defaults to SQLite for zero-setup local dev."""
from .base import *  # noqa: F401, F403
import os
from pathlib import Path

import dj_database_url

DEBUG = True
ALLOWED_HOSTS = ['*']

# Use SQLite locally unless DATABASE_URL or DB_ENGINE env var is set.
if not os.environ.get('DATABASE_URL') and not os.environ.get('DB_ENGINE'):
    DATABASES = {
        'default': dj_database_url.config(
            default='sqlite:///' + str(Path(__file__).resolve().parent.parent.parent / 'db.sqlite3'),
        )
    }
