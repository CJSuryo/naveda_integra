"""Celery application for naveda_integra.

Background execution is required by the aggregator integration: menu pushes are
slow, aggregator webhooks must be acknowledged within seconds while the real
work happens afterwards, and OAuth access tokens must be refreshed on a
schedule or integrations silently die.

Durability note: the broker is *not* the source of truth. Every inbound webhook
is persisted as a ``WebhookEvent`` row before any task is queued, so a lost
broker message costs a retry, never an order.
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'naveda_integra.settings.development')

app = Celery('naveda_integra')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'aggregator-refresh-expiring-tokens': {
        'task': 'pos_aggregator.tasks.refresh_expiring_tokens',
        'schedule': crontab(minute='*/15'),
    },
    'aggregator-retry-dead-letter-webhooks': {
        'task': 'pos_aggregator.tasks.retry_failed_webhook_events',
        'schedule': crontab(minute='*/10'),
    },
    'aggregator-reconcile-menu-sync': {
        'task': 'pos_aggregator.tasks.reconcile_stale_menu_syncs',
        'schedule': crontab(minute='*/30'),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
