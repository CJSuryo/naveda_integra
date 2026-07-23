"""Authorization scoping for POS stores and merchants.

A ``StorePOSConfig`` belongs to an ``EntitasBisnisLv3`` (a branch), whose
``parent_lv2`` rolls up to a lv1 ``EntitasBisnis`` — the same entity that
``UserEntitasBisnis`` links a user to. A user may only act on stores under
entities they are linked to. Superusers and admins see every store.

Use ``accessible_store_qs(request.user)`` anywhere a view fetches a store or an
order by primary key, and ``accessible_merchant_qs(request.user)`` anywhere a
view fetches a merchant or its aggregator credentials, so a user cannot reach
another tenant's POS data by guessing ids.
"""
from pos_config.models import MerchantPOSConfig, StorePOSConfig


def _is_unrestricted(user) -> bool:
    return user is None or user.is_superuser or getattr(user, 'is_admin', False)


def _linked_eb_ids(user):
    from apps.accounts.models import UserEntitasBisnis
    return UserEntitasBisnis.objects.filter(user=user).values_list(
        'entitas_bisnis_id', flat=True
    )


def accessible_lv2_qs(user):
    """EntitasBisnisLv2 queryset limited to operating companies the user may access.

    Use this to scope any view that fetches a lv2 by pk *before* a
    ``MerchantPOSConfig`` necessarily exists for it (e.g. the aggregator
    "connect a channel" flow, which get_or_creates the config on first visit) —
    ``accessible_merchant_qs`` cannot scope a row that hasn't been created yet.
    """
    from apps.entitas_bisnis.models import EntitasBisnisLv2
    qs = EntitasBisnisLv2.objects.all()
    if _is_unrestricted(user):
        return qs
    return qs.filter(entitas_bisnis_id__in=_linked_eb_ids(user))


def accessible_store_qs(user):
    """StorePOSConfig queryset limited to branches the user may access."""
    qs = StorePOSConfig.objects.all()
    if _is_unrestricted(user):
        return qs
    return qs.filter(
        entitas_bisnis_lv3__parent_lv2__entitas_bisnis_id__in=_linked_eb_ids(user)
    )


def accessible_merchant_qs(user):
    """MerchantPOSConfig queryset limited to operating companies the user may access."""
    qs = MerchantPOSConfig.objects.all()
    if _is_unrestricted(user):
        return qs
    return qs.filter(entitas_bisnis_lv2__entitas_bisnis_id__in=_linked_eb_ids(user))
