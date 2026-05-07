import secrets
import string
import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.pos_promotions.models import Campaign, Voucher, OrderPromotion


def get_applicable_campaigns(order) -> list[Campaign]:
    """Return active campaigns applicable to this order."""
    today = timezone.localdate()
    from django.db.models import Q
    qs = Campaign.objects.filter(
        merchant_config=order.store.merchant_config,
        is_active=True,
        start_date__lte=today,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).filter(
        min_purchase_amount__lte=order.subtotal,
    )

    applicable = []
    for c in qs:
        if c.stores.exists() and not c.stores.filter(pk=order.store_id).exists():
            continue
        if c.requires_member and not order.member_id:
            continue
        if c.max_uses is not None and c.uses_count >= c.max_uses:
            continue
        applicable.append(c)
    return applicable


def calculate_discount(campaign: Campaign, order) -> Decimal:
    """Compute discount amount for a campaign against an order subtotal."""
    subtotal = order.subtotal

    if campaign.campaign_type == Campaign.TYPE_DISCOUNT_PCT:
        raw = subtotal * (campaign.discount_pct / Decimal('100'))
        if campaign.max_discount_cap:
            raw = min(raw, campaign.max_discount_cap)
        return raw.quantize(Decimal('1'))

    if campaign.campaign_type == Campaign.TYPE_DISCOUNT_FIXED:
        return min(campaign.discount_amount or Decimal('0'), subtotal)

    # BUY_X_GET_Y, FREE_ITEM, VOUCHER — return 0; caller handles separately
    return Decimal('0')


def validate_voucher(code: str, order) -> tuple[Voucher | None, str | None]:
    """Return (voucher, None) if valid, or (None, error_message) if not."""
    try:
        voucher = Voucher.objects.select_related('campaign').get(code=code)
    except Voucher.DoesNotExist:
        return None, f'Kode voucher "{code}" tidak ditemukan.'

    if voucher.is_used:
        return None, 'Voucher sudah digunakan.'

    if voucher.expires_at and voucher.expires_at < timezone.now():
        return None, 'Voucher sudah kedaluwarsa.'

    campaign = voucher.campaign
    if not campaign.is_active:
        return None, 'Kampanye voucher tidak aktif.'

    today = timezone.localdate()
    if campaign.start_date > today:
        return None, 'Kampanye voucher belum dimulai.'
    if campaign.end_date and campaign.end_date < today:
        return None, 'Kampanye voucher sudah berakhir.'

    if campaign.merchant_config_id != order.store.merchant_config_id:
        return None, 'Voucher tidak berlaku di toko ini.'

    return voucher, None


def apply_voucher(code: str, order) -> OrderPromotion:
    """Validate and apply voucher to order. Returns OrderPromotion."""
    voucher, error = validate_voucher(code, order)
    if error:
        raise ValueError(error)

    campaign = voucher.campaign
    discount = calculate_discount(campaign, order)

    with transaction.atomic():
        promo = OrderPromotion.objects.create(
            order=order,
            campaign=campaign,
            voucher=voucher,
            discount_amount=discount,
            description=f'Voucher {code} — {campaign.name}',
        )
        Voucher.objects.filter(pk=voucher.pk).update(
            is_used=True,
            used_by=order.member,
            used_in_order=order,
            used_at=timezone.now(),
        )
        Campaign.objects.filter(pk=campaign.pk).update(uses_count=F('uses_count') + 1)
    return promo


def generate_voucher_codes(campaign: Campaign, count: int, prefix: str = '') -> list[Voucher]:
    """Generate `count` unique voucher codes for a campaign."""
    alphabet = string.ascii_uppercase + string.digits
    vouchers = []
    existing = set(Voucher.objects.filter(campaign=campaign).values_list('code', flat=True))
    for _ in range(count):
        while True:
            suffix = ''.join(secrets.choice(alphabet) for _ in range(8))
            code = f'{prefix}{suffix}' if prefix else suffix
            if code not in existing:
                existing.add(code)
                break
        vouchers.append(Voucher(campaign=campaign, code=code))
    return Voucher.objects.bulk_create(vouchers)
