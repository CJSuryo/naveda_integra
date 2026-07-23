"""Endpoint registry, keyed by (aggregator, country, environment).

The operator picks "Indonesia / Production" and the base URLs, auth URLs, scopes
and API version are filled in for them. Nobody types an endpoint by hand — a
typo'd or stale base URL is the single most common way these integrations break,
and it fails in ways that look like an authentication problem.

Every URL below is overridable through environment variables so a sandbox host
or a mid-flight vendor change never requires a code deploy.
"""
import os
from dataclasses import dataclass, field

from .constants import AggregatorType, Environment


@dataclass(frozen=True, slots=True)
class ConfigTemplate:
    aggregator: str
    country: str
    environment: str
    api_base_url: str
    auth_url: str
    authorize_url: str = ''
    scopes: tuple[str, ...] = ()
    api_version: str = 'v1'
    #: Whether the aggregator can hand us outlet ids after merchant consent.
    supports_outlet_discovery: bool = False
    #: Whether a merchant-consent redirect exists at all.
    supports_merchant_consent: bool = False
    #: Webhook events we must register with the aggregator, if it uses
    #: explicit subscriptions rather than a fixed callback URL.
    webhook_events: tuple[str, ...] = ()
    notes: str = ''


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# ── GoFood (GoBiz) ───────────────────────────────────────────────────────────
# Facilitator model: merchant authorises via phone → OTP → consent, we receive
# an authorization code, and outlets are then discoverable via token-info.
_GOFOOD_EVENTS = (
    'order.created',
    'order.merchant_accepted',
    'order.otw_pickup',
    'order.driver_arrived',
    'order.cancelled',
    'order.completed',
    'catalog.mapping_updated',
)

GOFOOD_ID_PRODUCTION = ConfigTemplate(
    aggregator=AggregatorType.GOFOOD,
    country='ID',
    environment=Environment.PRODUCTION,
    api_base_url=_env('GOFOOD_API_BASE_URL', 'https://api.gobiz.co.id'),
    auth_url=_env('GOFOOD_AUTH_URL', 'https://accounts.go-jek.com/oauth2/token'),
    authorize_url=_env('GOFOOD_AUTHORIZE_URL', 'https://accounts.go-jek.com/oauth2/auth'),
    scopes=(
        'gofood:order:read',
        'gofood:catalog:write',
        'partner:outlet:read',
        'partner:outlet:write',
    ),
    supports_outlet_discovery=True,
    supports_merchant_consent=True,
    webhook_events=_GOFOOD_EVENTS,
    notes='Facilitator model. Requires GoBiz Partner registration (company-level, one time).',
)

GOFOOD_ID_SANDBOX = ConfigTemplate(
    aggregator=AggregatorType.GOFOOD,
    country='ID',
    environment=Environment.SANDBOX,
    api_base_url=_env('GOFOOD_SANDBOX_API_BASE_URL', 'https://api.sandbox.gobiz.co.id'),
    auth_url=_env('GOFOOD_SANDBOX_AUTH_URL', 'https://accounts-sandbox.go-jek.com/oauth2/token'),
    authorize_url=_env('GOFOOD_SANDBOX_AUTHORIZE_URL', 'https://accounts-sandbox.go-jek.com/oauth2/auth'),
    scopes=GOFOOD_ID_PRODUCTION.scopes,
    supports_outlet_discovery=True,
    supports_merchant_consent=True,
    webhook_events=_GOFOOD_EVENTS,
)


# ── GrabFood ─────────────────────────────────────────────────────────────────
# Self-activation: we generate an activation URL, the merchant approves on
# Grab, and Grab pushes the resulting store id back to our callback.
GRABFOOD_ID_PRODUCTION = ConfigTemplate(
    aggregator=AggregatorType.GRABFOOD,
    country='ID',
    environment=Environment.PRODUCTION,
    api_base_url=_env('GRABFOOD_API_BASE_URL', 'https://partner-api.grab.com'),
    auth_url=_env('GRABFOOD_AUTH_URL', 'https://api.grab.com/grabid/v1/oauth2/token'),
    authorize_url=_env('GRABFOOD_AUTHORIZE_URL', 'https://api.grab.com/grabid/v1/oauth2/authorize'),
    scopes=('food.partner_api',),
    supports_outlet_discovery=False,
    supports_merchant_consent=True,
    notes='Store id arrives via the self-activation callback; never typed by an operator.',
)

GRABFOOD_ID_SANDBOX = ConfigTemplate(
    aggregator=AggregatorType.GRABFOOD,
    country='ID',
    environment=Environment.SANDBOX,
    api_base_url=_env('GRABFOOD_SANDBOX_API_BASE_URL', 'https://partner-api.stg-myteksi.com'),
    auth_url=_env('GRABFOOD_SANDBOX_AUTH_URL', 'https://api.stg-myteksi.com/grabid/v1/oauth2/token'),
    authorize_url=_env('GRABFOOD_SANDBOX_AUTHORIZE_URL', 'https://api.stg-myteksi.com/grabid/v1/oauth2/authorize'),
    scopes=GRABFOOD_ID_PRODUCTION.scopes,
    supports_outlet_discovery=False,
    supports_merchant_consent=True,
)


# ── ShopeeFood ───────────────────────────────────────────────────────────────
# No public merchant-consent flow. Credentials are provisioned out of band and
# the store id is entered once, with format validation, by the operator.
SHOPEEFOOD_ID_PRODUCTION = ConfigTemplate(
    aggregator=AggregatorType.SHOPEEFOOD,
    country='ID',
    environment=Environment.PRODUCTION,
    api_base_url=_env('SHOPEEFOOD_API_BASE_URL', 'https://partner.shopeemobile.com'),
    auth_url=_env('SHOPEEFOOD_AUTH_URL', 'https://partner.shopeemobile.com/api/v2/auth/token/get'),
    scopes=(),
    supports_outlet_discovery=False,
    supports_merchant_consent=False,
    notes=(
        'Partner API access is granted case-by-case by Shopee. Credentials are '
        'entered once by an administrator; the operator supplies only the store id.'
    ),
)

SHOPEEFOOD_ID_SANDBOX = ConfigTemplate(
    aggregator=AggregatorType.SHOPEEFOOD,
    country='ID',
    environment=Environment.SANDBOX,
    api_base_url=_env('SHOPEEFOOD_SANDBOX_API_BASE_URL', 'https://partner.test-stable.shopeemobile.com'),
    auth_url=_env(
        'SHOPEEFOOD_SANDBOX_AUTH_URL',
        'https://partner.test-stable.shopeemobile.com/api/v2/auth/token/get',
    ),
    supports_outlet_discovery=False,
    supports_merchant_consent=False,
)


_REGISTRY: dict[tuple[str, str, str], ConfigTemplate] = {
    (t.aggregator, t.country, t.environment): t
    for t in (
        GOFOOD_ID_PRODUCTION, GOFOOD_ID_SANDBOX,
        GRABFOOD_ID_PRODUCTION, GRABFOOD_ID_SANDBOX,
        SHOPEEFOOD_ID_PRODUCTION, SHOPEEFOOD_ID_SANDBOX,
    )
}


class UnknownConfigTemplate(KeyError):
    pass


def get_template(aggregator: str, country: str, environment: str) -> ConfigTemplate:
    try:
        return _REGISTRY[(aggregator, country, environment)]
    except KeyError as exc:
        raise UnknownConfigTemplate(
            f'No endpoint template for {aggregator} / {country} / {environment}. '
            f'Available: {sorted(_REGISTRY)}'
        ) from exc


def available_countries(aggregator: str) -> list[str]:
    return sorted({c for (a, c, _) in _REGISTRY if a == aggregator})
