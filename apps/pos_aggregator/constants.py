"""Vocabulary shared by every aggregator adapter.

The canonical lifecycle is deliberately small. Each aggregator speaks its own
status language; adapters map that language onto ``OrderStatus`` and keep the
native value in ``AggregatorOrder.external_status`` for audit.

``OrderStatus`` values are ordered integers. That ordering is the cheap guard
against out-of-order webhook delivery: aggregators retry aggressively and fire
near-simultaneous events, so a transition is only applied when it moves the
order *forward*.
"""
from django.db import models


class AggregatorType(models.TextChoices):
    GOFOOD = 'GOFOOD', 'GoFood'
    GRABFOOD = 'GRABFOOD', 'GrabFood'
    SHOPEEFOOD = 'SHOPEEFOOD', 'ShopeeFood'


class OrderStatus(models.IntegerChoices):
    """Canonical delivery lifecycle.

    Terminal states are CANCELLED and COMPLETED. Everything else may advance.
    """
    CREATED = 10, 'Pesanan Masuk'
    ACCEPTED = 20, 'Diterima'
    PREPARING = 30, 'Diproses'
    READY = 40, 'Siap Diambil'
    DRIVER_ARRIVED = 50, 'Driver Tiba'
    PICKED_UP = 60, 'Diambil Driver'
    COMPLETED = 70, 'Selesai'
    CANCELLED = 90, 'Dibatalkan'


#: Statuses after which no further forward transition is meaningful.
TERMINAL_STATUSES = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})


class OrderType(models.TextChoices):
    DELIVERY = 'DELIVERY', 'Pesan Antar'
    TAKEAWAY = 'TAKEAWAY', 'Bawa Pulang'
    DINE_IN = 'DINE_IN', 'Makan di Tempat'


class POSTrigger(models.TextChoices):
    """Which lifecycle event releases the order to the kitchen.

    Merchants differ: some start cooking the moment an order lands, others wait
    until a driver is allocated so a cancellation does not waste food.
    """
    ON_CREATED = 'ON_CREATED', 'Saat pesanan masuk'
    ON_ACCEPTED = 'ON_ACCEPTED', 'Saat pesanan diterima'
    ON_DRIVER_ARRIVED = 'ON_DRIVER_ARRIVED', 'Saat driver tiba'


class Environment(models.TextChoices):
    SANDBOX = 'SANDBOX', 'Sandbox'
    PRODUCTION = 'PRODUCTION', 'Production'


class LinkStatus(models.TextChoices):
    NOT_LINKED = 'NOT_LINKED', 'Belum Terhubung'
    PENDING = 'PENDING', 'Menunggu Aggregator'
    LINKED = 'LINKED', 'Terhubung'
    FAILED = 'FAILED', 'Gagal'


class OnboardingState(models.TextChoices):
    """Resumable server-side onboarding pipeline.

    The wizard never holds state itself; it asks the backend to advance. Every
    transition is idempotent so a double-click or a reloaded tab cannot corrupt
    the sequence.
    """
    NOT_STARTED = 'NOT_STARTED', 'Belum Dimulai'
    PREREQ_CONFIRMED = 'PREREQ_CONFIRMED', 'Prasyarat Dikonfirmasi'
    ACCOUNT_CONNECTED = 'ACCOUNT_CONNECTED', 'Akun Terhubung'
    WEBHOOKS_REGISTERED = 'WEBHOOKS_REGISTERED', 'Webhook Terdaftar'
    STORES_LINKED = 'STORES_LINKED', 'Cabang Terhubung'
    MENU_SYNCED = 'MENU_SYNCED', 'Menu Tersinkron'
    PREFLIGHT_PASSED = 'PREFLIGHT_PASSED', 'Pemeriksaan Lolos'
    LIVE = 'LIVE', 'Live'
    DISCONNECTED = 'DISCONNECTED', 'Terputus'


#: Linear order of onboarding states, used to decide "what is the next step".
ONBOARDING_SEQUENCE = (
    OnboardingState.NOT_STARTED,
    OnboardingState.PREREQ_CONFIRMED,
    OnboardingState.ACCOUNT_CONNECTED,
    OnboardingState.WEBHOOKS_REGISTERED,
    OnboardingState.STORES_LINKED,
    OnboardingState.MENU_SYNCED,
    OnboardingState.PREFLIGHT_PASSED,
    OnboardingState.LIVE,
)


class SyncStatus(models.TextChoices):
    PENDING = 'PENDING', 'Menunggu'
    IN_PROGRESS = 'IN_PROGRESS', 'Berjalan'
    SUCCESS = 'SUCCESS', 'Berhasil'
    FAILED = 'FAILED', 'Gagal'


class WebhookStatus(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Diterima'
    PROCESSED = 'PROCESSED', 'Diproses'
    DUPLICATE = 'DUPLICATE', 'Duplikat'
    FAILED = 'FAILED', 'Gagal'
