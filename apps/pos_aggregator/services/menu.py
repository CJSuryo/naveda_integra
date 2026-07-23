"""Outbound: build and publish the catalog to an aggregator.

We own the menu. The aggregator's storefront is a projection of
``pos_catalog``, priced per channel so the merchant is not silently paying the
aggregator's commission out of its in-store margin.

The external id we publish for each item is the ``CatalogItem`` primary key.
Owning both sides of that id is what makes the return trip a lookup instead of
a fuzzy name match when an order comes back.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from pos_catalog.models import CatalogItem, ProductModifierGroup

from ..constants import SyncStatus
from ..dto import (
    CanonicalMenu, CanonicalMenuItem, CanonicalMenuModifier, CanonicalMenuModifierGroup,
)
from ..models import AggregatorItemSetting, AggregatorStoreLink

logger = logging.getLogger(__name__)


class MenuError(Exception):
    pass


def build_menu(store_link: AggregatorStoreLink) -> CanonicalMenu:
    """Assemble the channel menu for one outlet."""
    credential = store_link.credential
    merchant = credential.merchant_config
    lv1_id = merchant.entitas_bisnis_lv2.entitas_bisnis_id

    catalog_items = (
        CatalogItem.objects
        .filter(entitas_bisnis_id=lv1_id, is_active=True)
        .select_related('item')
        .order_by('display_order', 'item__nama')
    )

    overrides = {
        s.catalog_item_id: s
        for s in AggregatorItemSetting.objects.filter(
            credential=credential, catalog_item__in=catalog_items
        )
    }

    modifier_groups = _modifier_groups_by_item(catalog_items)

    items = []
    for catalog_item in catalog_items:
        override = overrides.get(catalog_item.pk)
        if override and not override.is_available:
            continue
        price = (
            override.effective_price() if override
            else _marked_up(catalog_item.selling_price, credential.price_markup_pct)
        )
        items.append(CanonicalMenuItem(
            external_id=str(catalog_item.pk),
            name=catalog_item.display_name or catalog_item.item.nama,
            description=getattr(catalog_item.item, 'deskripsi', '') or '',
            price=price,
            is_available=True,
            image_url=catalog_item.product_image.url if catalog_item.product_image else '',
            display_order=catalog_item.display_order,
            category=_category_of(catalog_item),
            modifier_groups=modifier_groups.get(catalog_item.item_id, []),
        ))

    return CanonicalMenu(
        external_store_id=store_link.external_store_id,
        currency=merchant.currency,
        items=items,
    )


def _marked_up(price: Decimal, markup_pct: Decimal) -> Decimal:
    markup = markup_pct or Decimal('0')
    return (price * (Decimal('100') + markup) / Decimal('100')).quantize(Decimal('0.01'))


def _category_of(catalog_item) -> str:
    for attr in ('kategori', 'tipe_item'):
        value = getattr(catalog_item.item, attr, None)
        if value:
            return str(value)
    return 'Menu'


def _modifier_groups_by_item(catalog_items) -> dict[int, list[CanonicalMenuModifierGroup]]:
    item_ids = [c.item_id for c in catalog_items]
    links = (
        ProductModifierGroup.objects
        .filter(item_id__in=item_ids, modifier_group__is_active=True)
        .select_related('modifier_group')
        .prefetch_related('modifier_group__options')
        .order_by('display_order')
    )
    grouped: dict[int, list[CanonicalMenuModifierGroup]] = {}
    for link in links:
        group = link.modifier_group
        grouped.setdefault(link.item_id, []).append(CanonicalMenuModifierGroup(
            external_id=str(group.pk),
            name=group.name,
            min_selections=group.min_selections,
            max_selections=group.max_selections,
            is_required=group.is_required,
            options=[
                CanonicalMenuModifier(
                    external_id=str(option.pk),
                    name=option.name,
                    price=option.additional_price,
                    is_available=option.is_available,
                )
                for option in group.options.all().order_by('display_order')
                if option.is_available
            ],
        ))
    return grouped


def validate_menu(menu: CanonicalMenu) -> list[str]:
    """Dry-run checks. Returns operator-readable problems, empty when publishable.

    Run before publishing so a bad menu is caught here rather than as an opaque
    rejection from the aggregator minutes later.
    """
    problems = []
    if not menu.items:
        problems.append('Katalog kosong — tidak ada item aktif untuk dikirim.')
    if not menu.external_store_id:
        problems.append('Cabang belum terhubung ke outlet aggregator.')
    for item in menu.items:
        if item.price <= 0:
            problems.append(f'"{item.name}" memiliki harga 0 atau negatif.')
        if not item.name:
            problems.append(f'Item {item.external_id} tidak punya nama.')
        for group in item.modifier_groups:
            if group.is_required and not group.options:
                problems.append(
                    f'"{item.name}" punya grup wajib "{group.name}" tanpa pilihan.'
                )
    return problems


def publish_menu(store_link: AggregatorStoreLink) -> dict:
    """Build, validate and push the menu for one outlet."""
    from ..adapters import get_adapter

    menu = build_menu(store_link)
    problems = validate_menu(menu)
    if problems:
        store_link.menu_sync_status = SyncStatus.FAILED
        store_link.menu_sync_detail = '\n'.join(problems)
        store_link.save(update_fields=[
            'menu_sync_status', 'menu_sync_detail', 'updated_at'
        ])
        raise MenuError('\n'.join(problems))

    store_link.menu_sync_status = SyncStatus.IN_PROGRESS
    store_link.menu_sync_detail = ''
    store_link.save(update_fields=['menu_sync_status', 'menu_sync_detail', 'updated_at'])

    adapter = get_adapter(store_link.credential)
    try:
        result = adapter.push_menu(store_link, menu)
    except Exception as exc:
        store_link.menu_sync_status = SyncStatus.FAILED
        store_link.menu_sync_detail = str(exc)[:2000]
        store_link.save(update_fields=[
            'menu_sync_status', 'menu_sync_detail', 'updated_at'
        ])
        raise

    _remember_external_ids(store_link, menu)

    store_link.menu_sync_status = SyncStatus.SUCCESS
    store_link.menu_synced_at = timezone.now()
    store_link.menu_sync_detail = f'{len(menu.items)} item terkirim.'
    store_link.save(update_fields=[
        'menu_sync_status', 'menu_synced_at', 'menu_sync_detail', 'updated_at'
    ])
    return result


def _remember_external_ids(store_link, menu: CanonicalMenu) -> None:
    """Record which external id each catalog item was published under."""
    credential = store_link.credential
    for item in menu.items:
        AggregatorItemSetting.objects.update_or_create(
            credential=credential,
            catalog_item_id=int(item.external_id),
            defaults={'external_item_id': item.external_id},
        )


def push_availability(store_link, catalog_item, available: bool) -> dict:
    """Flip one item in or out of stock without republishing everything."""
    from ..adapters import get_adapter

    adapter = get_adapter(store_link.credential)
    setting, _ = AggregatorItemSetting.objects.get_or_create(
        credential=store_link.credential, catalog_item=catalog_item,
        defaults={'external_item_id': str(catalog_item.pk)},
    )
    setting.is_available = available
    setting.save(update_fields=['is_available', 'updated_at'])
    return adapter.push_item_availability(
        store_link, setting.external_item_id or str(catalog_item.pk), available
    )


def set_store_open(store_link, accepting: bool) -> dict:
    from ..adapters import get_adapter

    adapter = get_adapter(store_link.credential)
    result = adapter.push_store_status(store_link, accepting)
    store_link.is_accepting_orders = accepting
    store_link.save(update_fields=['is_accepting_orders', 'updated_at'])
    return result
