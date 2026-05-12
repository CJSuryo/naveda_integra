from decimal import Decimal
from typing import List, Tuple
from django.db.models import Sum
from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import FIFOBatch, ItemMasterPurchase
from pos_config.models import StorePOSConfig
from pos_catalog.models import ProductModifierGroup


def check_stock(item: ItemMasterPurchase, quantity: Decimal, entitas_bisnis: EntitasBisnis) -> Tuple[bool, Decimal]:
    """
    Check if sufficient stock exists for this item.
    Returns (in_stock: bool, available_qty: Decimal).
    """
    available = FIFOBatch.objects.filter(
        item=item,
        remaining_qty__gt=0,
    ).aggregate(total=Sum('remaining_qty'))['total'] or Decimal('0')

    return available >= quantity, available


def validate_modifier_selections(item: ItemMasterPurchase, selected_option_ids: List[int]) -> List[str]:
    """
    Validate that selected modifier option IDs satisfy the item's modifier group rules.
    Returns list of error strings (empty list if valid).
    """
    from pos_catalog.models import ModifierOption

    errors = []

    options = ModifierOption.objects.filter(pk__in=selected_option_ids).select_related('group')
    selected_by_group: dict[int, list] = {}
    for opt in options:
        selected_by_group.setdefault(opt.group_id, []).append(opt.pk)

    for link in ProductModifierGroup.objects.filter(item=item).select_related('modifier_group'):
        group = link.modifier_group
        count = len(selected_by_group.get(group.pk, []))

        if group.is_required and count < group.min_selections:
            errors.append(f'Pilihan "{group.name}" wajib dipilih minimal {group.min_selections} item.')
        if count > group.max_selections:
            errors.append(f'Pilihan "{group.name}" maksimal {group.max_selections} item.')

    return errors
