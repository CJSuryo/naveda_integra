"""Authorization scoping for POS stores.

A ``StorePOSConfig`` belongs to an ``EntitasBisnisLv2`` which rolls up to a
lv1 ``EntitasBisnis`` — the same entity that ``UserEntitasBisnis`` links a user
to. A user may only act on stores under entities they are linked to. Superusers
and admins see every store.

Use ``accessible_store_qs(request.user)`` anywhere a view fetches a store or an
order by primary key, so a user cannot reach another tenant's POS data by
guessing ids.
"""
from pos_config.models import StorePOSConfig


def accessible_store_qs(user):
    """StorePOSConfig queryset limited to stores the user may access."""
    qs = StorePOSConfig.objects.all()
    if user is None or user.is_superuser or getattr(user, 'is_admin', False):
        return qs
    from apps.accounts.models import UserEntitasBisnis
    eb_ids = UserEntitasBisnis.objects.filter(user=user).values_list(
        'entitas_bisnis_id', flat=True
    )
    return qs.filter(entitas_bisnis_lv2__entitas_bisnis_id__in=eb_ids)
