"""The adapter contract every aggregator implements.

Services talk to this interface only. Adding a fourth aggregator should mean
writing one module here plus one entry in the registry — never edits scattered
across ingestion, menu publishing and onboarding.

Two rules that are easy to get wrong and expensive to discover in production:

* **Verify signatures against the raw request body.** Re-serialising parsed JSON
  changes key order and whitespace, which breaks HMAC comparison in ways that
  look like a credential problem.
* **Return the acknowledgement the aggregator expects.** Most treat any non-2xx
  as "retry forever"; some require a specific status code or envelope.
"""
from __future__ import annotations

import hmac
import logging
from abc import ABC, abstractmethod
from datetime import timedelta

import requests
from django.utils import timezone

from ..dto import (
    CanonicalMenu, CanonicalOrder, CanonicalStatusUpdate, ConnectAction, OutletInfo,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


class AdapterError(Exception):
    """Base class for adapter failures."""


class SignatureError(AdapterError):
    """The request did not carry a valid signature — treat as hostile."""


class AuthError(AdapterError):
    """Credentials were rejected or a token could not be obtained."""


class UpstreamError(AdapterError):
    """The aggregator's API returned an error."""

    def __init__(self, message, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class NotSupported(AdapterError):
    """This aggregator has no API for the requested capability.

    Raised rather than silently no-oping, so the wizard can tell the operator
    the truth instead of showing a step that quietly does nothing.
    """


def constant_time_compare(a: str, b: str) -> bool:
    """Compare signatures without leaking timing information."""
    return hmac.compare_digest(str(a or ''), str(b or ''))


class BaseAdapter(ABC):
    """Shared HTTP plumbing and token handling."""

    #: AggregatorType value this adapter serves.
    aggregator: str = ''
    #: HTTP status this aggregator expects for a successfully handled webhook.
    ack_status_code: int = 200

    def __init__(self, credential):
        self.credential = credential
        self.template = credential.template

    # ── HTTP ────────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f'{self.template.api_base_url.rstrip("/")}/{path.lstrip("/")}'

    def _auth_headers(self) -> dict:
        return {'Authorization': f'Bearer {self.get_access_token()}'}

    def request(self, method: str, path: str, *, headers=None, json=None,
                data=None, params=None, timeout=DEFAULT_TIMEOUT, authed=True):
        url = self._url(path)
        merged = {'Accept': 'application/json'}
        if authed:
            merged.update(self._auth_headers())
        if headers:
            merged.update(headers)
        try:
            response = requests.request(
                method, url, headers=merged, json=json, data=data,
                params=params, timeout=timeout,
            )
        except requests.RequestException as exc:
            raise UpstreamError(f'{self.aggregator}: {method} {url} failed: {exc}') from exc

        if response.status_code >= 400:
            raise UpstreamError(
                f'{self.aggregator}: {method} {url} returned {response.status_code}',
                status_code=response.status_code,
                body=response.text[:2000],
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {'raw': response.text}

    # ── Tokens ──────────────────────────────────────────────────────────────

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing when close to expiry.

        Refreshed a minute early: a token that expires mid-flight produces a
        confusing 401 on an otherwise correct request.
        """
        cred = self.credential
        expires = cred.access_token_expires_at
        if cred.access_token_encrypted and expires and expires > timezone.now() + timedelta(minutes=1):
            return cred.access_token
        return self.refresh_access_token()

    @abstractmethod
    def refresh_access_token(self) -> str:
        """Obtain a fresh access token and persist it. Returns the token."""

    def store_tokens(self, *, access_token='', expires_in=None, refresh_token='',
                     refresh_expires_in=None) -> None:
        cred = self.credential
        fields = []
        if access_token:
            cred.access_token = access_token
            fields.append('access_token_encrypted')
            if expires_in:
                cred.access_token_expires_at = timezone.now() + timedelta(seconds=int(expires_in))
                fields.append('access_token_expires_at')
        if refresh_token:
            cred.refresh_token = refresh_token
            fields.append('refresh_token_encrypted')
            if refresh_expires_in:
                cred.refresh_token_expires_at = timezone.now() + timedelta(
                    seconds=int(refresh_expires_in)
                )
                fields.append('refresh_token_expires_at')
        if fields:
            cred.save(update_fields=fields + ['updated_at'])

    # ── Inbound ─────────────────────────────────────────────────────────────

    @abstractmethod
    def verify_webhook(self, request) -> None:
        """Raise ``SignatureError`` unless the request is authentic.

        Must read ``request.body`` (raw bytes), never a re-serialised payload.
        """

    @abstractmethod
    def extract_event_meta(self, payload: dict, request) -> dict:
        """Return ``{event_type, external_event_id, external_order_id, external_store_id}``."""

    @abstractmethod
    def parse_order(self, payload: dict) -> CanonicalOrder | None:
        """Translate a full order payload. Return ``None`` if not an order event."""

    @abstractmethod
    def parse_status(self, payload: dict) -> CanonicalStatusUpdate | None:
        """Translate a lifecycle callback. Return ``None`` if not a status event."""

    # ── Outbound: menu ──────────────────────────────────────────────────────

    @abstractmethod
    def push_menu(self, store_link, menu: CanonicalMenu) -> dict:
        """Publish the full catalog for one outlet."""

    def pull_menu(self, store_link) -> CanonicalMenu:
        """Read the menu currently live on the aggregator for one outlet.

        For an already-established business connecting for the first time,
        this seeds Naveda's catalog from what already exists on the aggregator
        instead of forcing a from-scratch rebuild. Not every aggregator's data
        model supports this direction — raise ``NotSupported`` with a reason a
        non-technical operator can read, rather than a bare 404.
        """
        raise NotSupported(f'{self.aggregator} has no menu read-back API.')

    def push_item_availability(self, store_link, external_item_id: str,
                               available: bool) -> dict:
        raise NotSupported(
            f'{self.aggregator} has no single-item availability API; '
            'republish the whole menu instead.'
        )

    def push_store_status(self, store_link, accepting_orders: bool) -> dict:
        raise NotSupported(f'{self.aggregator} has no open/close API.')

    def push_order_status(self, order, status) -> dict:
        """Send kitchen state back to the aggregator, where supported."""
        raise NotSupported(f'{self.aggregator} accepts no outbound order status.')

    # ── Onboarding ──────────────────────────────────────────────────────────

    @abstractmethod
    def begin_connect(self, session, redirect_uri: str) -> ConnectAction:
        """Start account connection: a consent redirect, or a manual form."""

    @abstractmethod
    def complete_connect(self, session, params: dict) -> None:
        """Finish connection from an OAuth callback or a submitted form."""

    def register_webhooks(self, callback_base_url: str) -> list:
        """Register/reconcile webhook subscriptions. Default: nothing to do."""
        return []

    def discover_outlets(self) -> list[OutletInfo]:
        """List outlets on the merchant's account."""
        raise NotSupported(
            f'{self.aggregator} cannot list outlets; the store id must be supplied manually.'
        )

    def link_store(self, store_link) -> dict:
        """Attach one branch to one outlet."""
        raise NotSupported(f'{self.aggregator} has no outlet linking API.')

    def unlink_store(self, store_link) -> dict:
        raise NotSupported(f'{self.aggregator} has no outlet unlinking API.')

    def validate_store_id(self, value: str) -> tuple[bool, str]:
        """Sanity-check a manually entered outlet id.

        A wrong id routes one branch's orders into another branch's kitchen, so
        the format is checked before it is ever saved.
        """
        value = (value or '').strip()
        if not value:
            return False, 'Store ID tidak boleh kosong.'
        if len(value) < 3:
            return False, 'Store ID terlalu pendek — sepertinya bukan nilai yang benar.'
        return True, ''

    def ping(self) -> tuple[bool, str]:
        """Cheap credential check used by pre-flight."""
        try:
            self.get_access_token()
        except AdapterError as exc:
            return False, str(exc)
        return True, 'Autentikasi berhasil.'

    def disconnect(self) -> None:
        """Revoke tokens and remove remote registrations. Best-effort."""
        cred = self.credential
        cred.access_token = ''
        cred.refresh_token = ''
        cred.access_token_expires_at = None
        cred.refresh_token_expires_at = None
        cred.is_active = False
        cred.save(update_fields=[
            'access_token_encrypted', 'refresh_token_encrypted',
            'access_token_expires_at', 'refresh_token_expires_at',
            'is_active', 'updated_at',
        ])
