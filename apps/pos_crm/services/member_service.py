from decimal import Decimal
from django.db import transaction

from apps.pos_crm.models import Member, MemberTierConfig, MemberPointLog


def lookup_member(phone: str, merchant) -> Member | None:
    return Member.objects.filter(
        merchant_config=merchant, phone=phone, is_active=True
    ).first()


def register_member(merchant, name: str, phone: str, email: str = '', birth_date=None) -> Member:
    if Member.objects.filter(merchant_config=merchant, phone=phone).exists():
        raise ValueError(f'Nomor {phone} sudah terdaftar sebagai member.')
    return Member.objects.create(
        merchant_config=merchant,
        name=name,
        phone=phone,
        email=email,
        birth_date=birth_date,
    )


def add_points(member: Member, order) -> MemberPointLog:
    """Compute and credit points for a completed order. Updates total_spent and total_orders."""
    tier_config = MemberTierConfig.objects.filter(
        merchant_config=member.merchant_config,
        tier=member.tier,
    ).first()
    ppt = tier_config.points_per_thousand if tier_config else 1
    points_earned = int(order.total_amount / Decimal('1000')) * ppt

    with transaction.atomic():
        log = MemberPointLog.objects.create(
            member=member,
            order=order,
            points=points_earned,
            reason=f'Pembelian {order.order_number}',
        )
        Member.objects.filter(pk=member.pk).update(
            points=member.points + points_earned,
            total_spent=member.total_spent + order.total_amount,
            total_orders=member.total_orders + 1,
        )
        member.refresh_from_db()
        check_tier_upgrade(member)
    return log


def redeem_points(member: Member, order, points_to_redeem: int):
    """Deduct points and return (discount_amount, MemberPointLog).

    Raises ValueError if member has insufficient points.
    """
    if member.points < points_to_redeem:
        raise ValueError(
            f'Poin tidak cukup. Tersedia: {member.points}, diminta: {points_to_redeem}'
        )
    tier_config = MemberTierConfig.objects.filter(
        merchant_config=member.merchant_config,
        tier=member.tier,
    ).first()
    point_value = tier_config.point_value if tier_config else Decimal('100')
    discount = Decimal(str(points_to_redeem)) * point_value

    with transaction.atomic():
        log = MemberPointLog.objects.create(
            member=member,
            order=order,
            points=-points_to_redeem,
            reason=f'Penukaran poin — {order.order_number}',
        )
        Member.objects.filter(pk=member.pk).update(points=member.points - points_to_redeem)
        member.refresh_from_db()
    return discount, log


def check_tier_upgrade(member: Member) -> bool:
    """Check if member should be upgraded based on total_spent. Returns True if tier changed."""
    tier_order = ['REGULAR', 'SILVER', 'GOLD', 'PLATINUM']
    configs = MemberTierConfig.objects.filter(
        merchant_config=member.merchant_config
    ).order_by('-min_total_spent')

    best_tier = member.tier
    for config in configs:
        if member.total_spent >= config.min_total_spent:
            if tier_order.index(config.tier) > tier_order.index(best_tier):
                best_tier = config.tier

    if best_tier != member.tier:
        Member.objects.filter(pk=member.pk).update(tier=best_tier)
        member.tier = best_tier
        return True
    return False


def deduct_points_for_refund(member: Member, order) -> MemberPointLog | None:
    """Remove points earned on a refunded order. No-op if no log found."""
    original_log = MemberPointLog.objects.filter(
        member=member, order=order, points__gt=0
    ).first()
    if not original_log:
        return None
    with transaction.atomic():
        log = MemberPointLog.objects.create(
            member=member,
            order=order,
            points=-original_log.points,
            reason=f'Refund order {order.order_number}',
        )
        Member.objects.filter(pk=member.pk).update(
            points=member.points - original_log.points,
            total_spent=member.total_spent - order.total_amount,
            total_orders=member.total_orders - 1,
        )
        member.refresh_from_db()
    return log
