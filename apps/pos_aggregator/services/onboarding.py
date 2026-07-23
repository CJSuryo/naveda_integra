"""The onboarding state machine.

The wizard holds no state. It asks the backend to advance, and the backend
decides what "advance" means for that aggregator. Every function here is
idempotent: closing the tab, double-clicking, or replaying a callback must never
corrupt the sequence.

Going live is gated on pre-flight passing. That is the whole safety model — the
system, not the operator, decides readiness.
"""
from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from ..constants import LinkStatus, OnboardingState, SyncStatus
from ..models import (
    AggregatorCredential, AggregatorStoreLink, OnboardingSession,
)
from .preflight import as_dicts, run_preflight

logger = logging.getLogger(__name__)

#: An OAuth state nonce older than this is refused, limiting replay of a
#: captured redirect.
OAUTH_STATE_TTL_SECONDS = 900


class OnboardingError(Exception):
    pass


def get_or_create_session(credential: AggregatorCredential, user=None) -> OnboardingSession:
    session, created = OnboardingSession.objects.get_or_create(
        credential=credential, defaults={'started_by': user},
    )
    if created and user is None:
        pass
    return session


def public_base_url() -> str:
    base = getattr(settings, 'AGGREGATOR_PUBLIC_BASE_URL', '')
    if not base:
        raise OnboardingError(
            'AGGREGATOR_PUBLIC_BASE_URL belum diisi. Aggregator tidak bisa '
            'mengirim pesanan tanpa alamat publik HTTPS.'
        )
    return base.rstrip('/')


def oauth_redirect_uri() -> str:
    return public_base_url() + reverse('pos_aggregator:oauth_callback')


def webhook_base_url() -> str:
    return public_base_url() + '/pos/aggregator/webhook'


# ── Transitions ─────────────────────────────────────────────────────────────

def confirm_prerequisites(session: OnboardingSession) -> OnboardingSession:
    """Operator has confirmed the merchant account and API access exist."""
    return _advance(session, OnboardingState.PREREQ_CONFIRMED)


def begin_connect(session: OnboardingSession):
    """Return the next connect action (redirect or form)."""
    from ..adapters import get_adapter

    session.oauth_state = secrets.token_urlsafe(32)
    session.oauth_state_created_at = timezone.now()
    session.save(update_fields=['oauth_state', 'oauth_state_created_at', 'updated_at'])

    adapter = get_adapter(session.credential)
    return adapter.begin_connect(session, oauth_redirect_uri())


def complete_connect(session: OnboardingSession, params: dict) -> OnboardingSession:
    """Finish account connection from an OAuth callback or a submitted form."""
    from ..adapters import get_adapter

    adapter = get_adapter(session.credential)
    params = dict(params)
    params.setdefault('redirect_uri', oauth_redirect_uri())
    adapter.complete_connect(session, params)

    credential = session.credential
    credential.is_active = True
    credential.save(update_fields=['is_active', 'updated_at'])

    session.oauth_state = ''
    session.last_error = ''
    session.save(update_fields=['oauth_state', 'last_error', 'updated_at'])
    return _advance(session, OnboardingState.ACCOUNT_CONNECTED)


def verify_oauth_state(session: OnboardingSession, provided: str) -> None:
    """Reject a callback whose nonce does not match a recent request."""
    if not session.oauth_state or not provided:
        raise OnboardingError('State OAuth tidak ada — mulai ulang proses menghubungkan akun.')
    if not secrets.compare_digest(session.oauth_state, provided):
        raise OnboardingError('State OAuth tidak cocok — permintaan ditolak.')
    created = session.oauth_state_created_at
    if not created or (timezone.now() - created).total_seconds() > OAUTH_STATE_TTL_SECONDS:
        raise OnboardingError('Permintaan sudah kedaluwarsa — ulangi "Hubungkan Akun".')


def register_webhooks(session: OnboardingSession) -> list:
    """Create or reconcile webhook subscriptions. Safe to press twice."""
    from ..adapters import get_adapter

    subscriptions = get_adapter(session.credential).register_webhooks(webhook_base_url())
    failed = [s for s in subscriptions if s.status == SyncStatus.FAILED]
    if failed and len(failed) == len(subscriptions):
        session.last_error = 'Semua langganan webhook gagal didaftarkan.'
        session.save(update_fields=['last_error', 'updated_at'])
        return subscriptions
    _advance(session, OnboardingState.WEBHOOKS_REGISTERED)
    return subscriptions


def discover_outlets(session: OnboardingSession):
    from ..adapters import get_adapter
    return get_adapter(session.credential).discover_outlets()


@transaction.atomic
def link_store(session: OnboardingSession, store_config, external_store_id: str,
               *, name='', address='') -> AggregatorStoreLink:
    """Attach one branch to one outlet.

    The uniqueness constraint on ``(aggregator, external_store_id)`` is what
    stops two branches claiming the same outlet — a mistake that routes orders
    to the wrong kitchen and books revenue against the wrong entity.
    """
    from ..adapters import get_adapter

    credential = session.credential
    adapter = get_adapter(credential)

    external_store_id = (external_store_id or '').strip()
    valid, message = adapter.validate_store_id(external_store_id)
    if not valid:
        raise OnboardingError(message)

    clash = (
        AggregatorStoreLink.objects
        .filter(aggregator=credential.aggregator, external_store_id=external_store_id)
        .exclude(store_config=store_config)
        .select_related('store_config__entitas_bisnis_lv3')
        .first()
    )
    if clash:
        raise OnboardingError(
            f'Outlet {external_store_id} sudah terhubung ke cabang '
            f'"{clash.store_config.entitas_bisnis_lv3.nama}". Satu outlet hanya '
            'boleh dipakai satu cabang.'
        )

    link, _ = AggregatorStoreLink.objects.update_or_create(
        store_config=store_config, aggregator=credential.aggregator,
        defaults={
            'credential': credential,
            'external_store_id': external_store_id,
            'external_store_name': name,
            'external_store_address': address,
            'status': LinkStatus.LINKED,
            'linked_at': timezone.now(),
            'status_detail': '',
        },
    )

    try:
        adapter.link_store(link)
    except Exception as exc:
        from ..adapters import NotSupported
        if not isinstance(exc, NotSupported):
            link.status = LinkStatus.FAILED
            link.status_detail = str(exc)[:2000]
            link.save(update_fields=['status', 'status_detail', 'updated_at'])
            raise OnboardingError(f'Gagal menghubungkan outlet: {exc}') from exc

    _advance(session, OnboardingState.STORES_LINKED)
    return link


def unlink_store(link: AggregatorStoreLink) -> None:
    from ..adapters import get_adapter, NotSupported
    try:
        get_adapter(link.credential).unlink_store(link)
    except NotSupported:
        pass
    except Exception:
        logger.warning('Remote unlink failed; unlinking locally', exc_info=True)
    link.delete()


def sync_menus(session: OnboardingSession) -> dict:
    """Publish the menu for every linked branch."""
    from .menu import MenuError, publish_menu

    results = {}
    links = AggregatorStoreLink.objects.filter(
        credential=session.credential
    ).exclude(external_store_id='')
    for link in links:
        try:
            publish_menu(link)
            results[link.pk] = {'ok': True}
        except MenuError as exc:
            results[link.pk] = {'ok': False, 'error': str(exc)}
        except Exception as exc:
            results[link.pk] = {'ok': False, 'error': str(exc)}

    if results and all(r['ok'] for r in results.values()):
        _advance(session, OnboardingState.MENU_SYNCED)
    return results


def run_checks(session: OnboardingSession) -> list:
    results = run_preflight(session.credential)
    session.preflight_results = as_dicts(results)
    session.save(update_fields=['preflight_results', 'updated_at'])
    if session.preflight_passed:
        _advance(session, OnboardingState.PREFLIGHT_PASSED)
    return results


def go_live(session: OnboardingSession) -> OnboardingSession:
    """Open the channel for real orders. Refuses unless pre-flight is green."""
    if not session.preflight_passed:
        raise OnboardingError(
            'Pemeriksaan belum lolos semua. Jalankan "Jalankan Pemeriksaan" dan '
            'perbaiki item yang merah sebelum go live.'
        )

    from ..adapters import get_adapter, NotSupported
    adapter = get_adapter(session.credential)
    links = AggregatorStoreLink.objects.filter(
        credential=session.credential
    ).exclude(external_store_id='')

    for link in links:
        try:
            adapter.push_store_status(link, True)
        except NotSupported:
            pass
        except Exception:
            logger.warning('Could not open store %s upstream', link.pk, exc_info=True)
        link.is_live = True
        link.is_accepting_orders = True
        link.save(update_fields=['is_live', 'is_accepting_orders', 'updated_at'])

    return _advance(session, OnboardingState.LIVE)


def disconnect(session: OnboardingSession) -> OnboardingSession:
    """Reverse everything: revoke tokens, drop subscriptions, unlink branches."""
    from ..adapters import get_adapter

    try:
        get_adapter(session.credential).disconnect()
    except Exception:
        logger.warning('Remote disconnect failed; disconnecting locally', exc_info=True)

    AggregatorStoreLink.objects.filter(credential=session.credential).update(
        is_live=False, is_accepting_orders=False, status=LinkStatus.NOT_LINKED,
    )
    session.preflight_results = []
    session.save(update_fields=['preflight_results', 'updated_at'])
    return _advance(session, OnboardingState.DISCONNECTED, force=True)


def _advance(session: OnboardingSession, state: str, *, force=False) -> OnboardingSession:
    """Move forward only, unless forced (disconnect).

    Re-running an earlier step must not demote a session that has progressed
    past it, or a stray click would knock a live channel back to setup.
    """
    from ..constants import ONBOARDING_SEQUENCE

    if not force and session.state in (OnboardingState.LIVE,) and state != OnboardingState.LIVE:
        return session
    if not force:
        order = list(ONBOARDING_SEQUENCE)
        try:
            if order.index(state) <= order.index(session.state):
                return session
        except ValueError:
            pass
    session.state = state
    session.save(update_fields=['state', 'updated_at'])
    return session
