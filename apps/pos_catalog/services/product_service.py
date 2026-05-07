from decimal import Decimal
from typing import List, Tuple
from django.db.models import Sum, Q
from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import FIFOBatch
from pos_config.models import StorePOSConfig
from pos_catalog.models import POSProduct, ProductStoreAvailability, ProductModifierGroup


def get_available_products(store: StorePOSConfig):
    """
    Return QuerySet of POSProduct for this store, respecting store-level availability overrides.
    Logic:
      - ProductStoreAvailability with is_available=True → available (overrides base)
      - ProductStoreAvailability with is_available=False → unavailable (overrides base)
      - No override + POSProduct.is_available=True → available
    """
    merchant = store.merchant_config

    overridden_available = ProductStoreAvailability.objects.filter(
        store=store, is_available=True
    ).values_list('product_id', flat=True)

    overridden_unavailable = ProductStoreAvailability.objects.filter(
        store=store, is_available=False
    ).values_list('product_id', flat=True)

    return POSProduct.objects.filter(
        merchant_config=merchant
    ).filter(
        Q(pk__in=overridden_available) |
        (Q(is_available=True) & ~Q(pk__in=overridden_unavailable))
    ).select_related('category', 'item_master').prefetch_related('modifier_links__modifier_group__options')


def check_stock(product: POSProduct, quantity: Decimal, entitas_bisnis: EntitasBisnis) -> Tuple[bool, Decimal]:
    """
    Check if sufficient stock exists for this product.
    Returns (in_stock: bool, available_qty: Decimal).
    Non-tracked products (services) always return (True, Decimal('0')).
    """
    if not product.track_inventory:
        return True, Decimal('0')

    available = FIFOBatch.objects.filter(
        item=product.item_master,
        remaining_qty__gt=0,
    ).aggregate(total=Sum('remaining_qty'))['total'] or Decimal('0')

    return available >= quantity, available


def validate_modifier_selections(product: POSProduct, selected_option_ids: List[int]) -> List[str]:
    """
    Validate that selected modifier option IDs satisfy the product's modifier group rules.
    Returns list of error strings (empty list if valid).
    """
    from pos_catalog.models import ModifierOption

    errors = []

    options = ModifierOption.objects.filter(pk__in=selected_option_ids).select_related('group')
    selected_by_group: dict[int, list] = {}
    for opt in options:
        selected_by_group.setdefault(opt.group_id, []).append(opt.pk)

    for link in ProductModifierGroup.objects.filter(product=product).select_related('modifier_group'):
        group = link.modifier_group
        count = len(selected_by_group.get(group.pk, []))

        if group.is_required and count < group.min_selections:
            errors.append(f'Pilihan "{group.name}" wajib dipilih minimal {group.min_selections} item.')
        if count > group.max_selections:
            errors.append(f'Pilihan "{group.name}" maksimal {group.max_selections} item.')

    return errors
