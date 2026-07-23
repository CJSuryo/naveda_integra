"""Inbound menu import: aggregator → Naveda catalog.

For a business that already sells on GoFood/GrabFood/ShopeeFood today and is
only now setting up Naveda, rebuilding the whole menu by hand is the biggest
friction in onboarding. This pulls what already exists on the aggregator and
seeds ``ItemMasterPurchase`` + ``CatalogItem`` rows from it, so the owner edits
an already-populated catalog instead of starting from zero.

Two rules that keep this from corrupting data on a second run:

* **Matching, not duplicating.** An item already linked via
  ``AggregatorItemSetting.external_item_id`` is recognised and only its channel
  price/availability is refreshed. An unlinked item is matched by exact name
  before a new ``ItemMasterPurchase`` is created — ``nama`` is globally unique,
  so a second import (or a second business selling the same dish) must reuse
  the existing row rather than collide with it.
* **The pulled price seeds the catalog price once, then never overwrites it.**
  Aggregator prices are channel prices (aggregator commission baked in). They
  always become that channel's ``AggregatorItemSetting.price``. They only ever
  become ``CatalogItem.selling_price`` at *creation* time, as a starting point
  for the owner to review — a re-import must never clobber a price the owner
  has since corrected in Naveda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from apps.purchase.models import ItemMasterPurchase
from pos_catalog.models import CatalogItem, ModifierGroup, ModifierOption, ProductModifierGroup

from .. import dto
from ..models import AggregatorItemSetting, AggregatorStoreLink

#: Imported items land here rather than RM/FG, since a pulled aggregator item is
#: a menu listing, not a raw material or a manufacturing-costed finished good.
IMPORTED_TIPE_ITEM = 'ITM'


@dataclass(slots=True)
class ImportResult:
    created_items: list[str] = field(default_factory=list)
    matched_existing: list[str] = field(default_factory=list)
    updated_channel_price: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_seen(self) -> int:
        return len(self.created_items) + len(self.matched_existing)


def import_menu_from_aggregator(store_link: AggregatorStoreLink, *, kategori=None) -> ImportResult:
    """Pull the live aggregator menu and seed Naveda's catalog from it.

    ``kategori`` is applied to every newly-created ``ItemMasterPurchase`` — pass
    ``None`` to leave it unset for the owner to assign later.
    """
    from ..adapters import get_adapter

    result = ImportResult()
    adapter = get_adapter(store_link.credential)
    menu = adapter.pull_menu(store_link)

    lv1_id = (
        store_link.credential.merchant_config.entitas_bisnis_lv2.entitas_bisnis_id
    )

    for item in menu.items:
        try:
            with transaction.atomic():
                _import_one_item(store_link, lv1_id, item, kategori, result)
        except Exception as exc:
            result.errors.append(f'{item.name or item.external_id}: {exc}')

    return result


def _import_one_item(store_link, lv1_id: int, item: dto.CanonicalMenuItem, kategori,
                     result: ImportResult) -> None:
    credential = store_link.credential

    existing_setting = AggregatorItemSetting.objects.filter(
        credential=credential, external_item_id=item.external_id
    ).select_related('catalog_item').first()

    if existing_setting:
        # Already linked from a previous pull or a previous push — only the
        # channel price/availability is current information here; the catalog
        # item itself may have been deliberately edited in Naveda since.
        existing_setting.price = item.price
        existing_setting.is_available = item.is_available
        existing_setting.save(update_fields=['price', 'is_available', 'updated_at'])
        result.matched_existing.append(item.name)
        result.updated_channel_price.append(item.name)
        return

    item_master = ItemMasterPurchase.objects.filter(nama__iexact=item.name).first()
    created_item_master = item_master is None
    if item_master is None:
        item_master = ItemMasterPurchase.objects.create(
            nama=item.name,
            tipe_item=IMPORTED_TIPE_ITEM,
            kategori=kategori,
            unit_price=item.price,
        )

    catalog_item, created_catalog_item = CatalogItem.objects.get_or_create(
        entitas_bisnis_id=lv1_id, item=item_master,
        defaults={
            'selling_price': item.price,
            'display_name': item.name,
            'display_order': item.display_order,
            'is_active': item.is_available,
        },
    )

    _import_modifier_groups(credential, item_master, item.modifier_groups)

    AggregatorItemSetting.objects.update_or_create(
        credential=credential, catalog_item=catalog_item,
        defaults={
            'price': item.price,
            'is_available': item.is_available,
            'external_item_id': item.external_id,
        },
    )

    if created_item_master or created_catalog_item:
        result.created_items.append(item.name)
    else:
        result.matched_existing.append(item.name)


def _import_modifier_groups(credential, item_master, groups: list[dto.CanonicalMenuModifierGroup]) -> None:
    """Recreate modifier groups on the item master, matched by name.

    Matched by ``(merchant_config, name)`` rather than the aggregator's group
    id: the id is meaningless in Naveda, and re-running the import must not
    pile up duplicate "Ukuran" groups every time.
    """
    for group in groups:
        if not group.name:
            continue
        modifier_group, _ = ModifierGroup.objects.get_or_create(
            merchant_config=credential.merchant_config, name=group.name,
            defaults={
                'is_required': group.is_required,
                'min_selections': group.min_selections,
                'max_selections': group.max_selections,
            },
        )
        ProductModifierGroup.objects.get_or_create(
            item=item_master, modifier_group=modifier_group,
        )
        for option in group.options:
            if not option.name:
                continue
            ModifierOption.objects.get_or_create(
                group=modifier_group, name=option.name,
                defaults={
                    'additional_price': option.price,
                    'is_available': option.is_available,
                },
            )
