"""Development settings — defaults to SQLite for zero-setup local dev."""
from .base import *  # noqa: F401, F403
import os
from pathlib import Path

import dj_database_url

DEBUG = True
ALLOWED_HOSTS = ['*']

# Serve static files directly from source (static/) instead of the collected
# staticfiles/ snapshot, so edits show up immediately without collectstatic.
WHITENOISE_USE_FINDERS = True

# Set DATABASE_URL in your .env file (e.g. a Neon connection string).
if os.environ.get('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(
            env='DATABASE_URL',
            conn_max_age=600,
        )
    }
