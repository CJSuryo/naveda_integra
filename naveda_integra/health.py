"""Liveness endpoint for the deploy healthcheck.

Unauthenticated and exempt from the global throttle (see middleware/throttle.py),
so deploy.sh can poll it from inside the container before declaring a deploy good.
Checks the database too: gunicorn answering while Postgres is unreachable is not
"healthy" for an accounting app, and is exactly the failure a deploy must catch.
"""
from django.db import connection
from django.http import HttpResponse


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:  # noqa: BLE001 — any DB failure is unhealthy, reason is in the logs
        return HttpResponse('db unavailable\n', status=503, content_type='text/plain')
    return HttpResponse('ok\n', content_type='text/plain')
