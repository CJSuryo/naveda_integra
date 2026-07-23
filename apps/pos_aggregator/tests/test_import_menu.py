"""Menu import (aggregator → Naveda) behaviour.

The two properties that matter: a second pull must not duplicate anything, and
it must never clobber a selling price the owner has since corrected in Naveda.
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.purchase.models import ItemMasterPurchase, KategoriItem
from pos_aggregator.adapters import NotSupported
from pos_aggregator.constants import AggregatorType
from pos_aggregator.dto import (
    CanonicalMenu, CanonicalMenuItem, CanonicalMenuModifier, CanonicalMenuModifierGroup,
)
from pos_aggregator.models import AggregatorItemSetting
from pos_aggregator.services.import_menu import import_menu_from_aggregator
from pos_catalog.models import CatalogItem, ModifierGroup, ModifierOption, ProductModifierGroup

from .factories import make_credential, make_store_link


def _menu(items=None):
    return CanonicalMenu(
        external_store_id='OUTLET-1',
        currency='IDR',
        items=items if items is not None else [
            CanonicalMenuItem(
                external_id='ext-1', name='Nasi Goreng', description='Pedas',
                price=Decimal('28000'), is_available=True, display_order=1,
                category='Makanan',
                modifier_groups=[
                    CanonicalMenuModifierGroup(
                        external_id='g1', name='Level Pedas', min_selections=1,
                        max_selections=1, is_required=True,
                        options=[
                            CanonicalMenuModifier(
                                external_id='o1', name='Sedang', price=Decimal('0')
                            ),
                            CanonicalMenuModifier(
                                external_id='o2', name='Extra Pedas', price=Decimal('2000')
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


class ImportMenuTest(TestCase):
    def setUp(self):
        self.credential = make_credential(aggregator=AggregatorType.GOFOOD)
        self.link = make_store_link(self.credential, external_store_id='OUTLET-1')

    def _import(self, menu=None):
        with patch(
            'pos_aggregator.adapters.gofood.GoFoodAdapter.pull_menu',
            return_value=menu or _menu(),
        ):
            return import_menu_from_aggregator(self.link)

    def test_creates_item_master_and_catalog_item(self):
        result = self._import()
        self.assertEqual(result.created_items, ['Nasi Goreng'])
        item = ItemMasterPurchase.objects.get(nama='Nasi Goreng')
        self.assertEqual(item.tipe_item, 'ITM')
        catalog_item = CatalogItem.objects.get(item=item)
        self.assertEqual(catalog_item.selling_price, Decimal('28000.0000'))

    def test_records_channel_price_on_aggregator_item_setting(self):
        self._import()
        item = ItemMasterPurchase.objects.get(nama='Nasi Goreng')
        catalog_item = CatalogItem.objects.get(item=item)
        setting = AggregatorItemSetting.objects.get(
            credential=self.credential, catalog_item=catalog_item
        )
        self.assertEqual(setting.price, Decimal('28000'))
        self.assertEqual(setting.external_item_id, 'ext-1')

    def test_creates_modifier_group_and_options(self):
        self._import()
        item = ItemMasterPurchase.objects.get(nama='Nasi Goreng')
        group = ModifierGroup.objects.get(
            merchant_config=self.credential.merchant_config, name='Level Pedas'
        )
        self.assertTrue(group.is_required)
        self.assertTrue(
            ProductModifierGroup.objects.filter(item=item, modifier_group=group).exists()
        )
        self.assertEqual(
            set(ModifierOption.objects.filter(group=group).values_list('name', flat=True)),
            {'Sedang', 'Extra Pedas'},
        )

    def test_second_pull_does_not_duplicate_item_master(self):
        self._import()
        self._import()
        self.assertEqual(
            ItemMasterPurchase.objects.filter(nama='Nasi Goreng').count(), 1
        )

    def test_second_pull_does_not_duplicate_modifier_group(self):
        self._import()
        self._import()
        self.assertEqual(
            ModifierGroup.objects.filter(
                merchant_config=self.credential.merchant_config, name='Level Pedas'
            ).count(),
            1,
        )

    def test_second_pull_reports_item_as_matched_not_created(self):
        self._import()
        result = self._import()
        self.assertEqual(result.created_items, [])
        self.assertEqual(result.matched_existing, ['Nasi Goreng'])

    def test_second_pull_never_overwrites_owner_edited_selling_price(self):
        self._import()
        catalog_item = CatalogItem.objects.get(item__nama='Nasi Goreng')
        catalog_item.selling_price = Decimal('35000')
        catalog_item.save(update_fields=['selling_price'])

        # Aggregator now reports a different (still-live) channel price.
        changed_menu = _menu(items=[
            CanonicalMenuItem(
                external_id='ext-1', name='Nasi Goreng', description='', price=Decimal('30000'),
                is_available=True,
            ),
        ])
        self._import(changed_menu)

        catalog_item.refresh_from_db()
        self.assertEqual(catalog_item.selling_price, Decimal('35000'))

    def test_second_pull_still_refreshes_channel_price(self):
        self._import()
        changed_menu = _menu(items=[
            CanonicalMenuItem(
                external_id='ext-1', name='Nasi Goreng', description='', price=Decimal('30000'),
                is_available=False,
            ),
        ])
        self._import(changed_menu)

        setting = AggregatorItemSetting.objects.get(external_item_id='ext-1')
        self.assertEqual(setting.price, Decimal('30000'))
        self.assertFalse(setting.is_available)

    def test_existing_item_master_with_same_name_is_reused_not_duplicated(self):
        """nama is globally unique — a second business's import must reuse it."""
        ItemMasterPurchase.objects.create(nama='Nasi Goreng', tipe_item='ITM')
        self._import()
        self.assertEqual(
            ItemMasterPurchase.objects.filter(nama='Nasi Goreng').count(), 1
        )

    def test_kategori_applied_only_on_creation(self):
        kategori = KategoriItem.objects.create(nama='Makanan Berat', tipe_item='ITM')
        with patch(
            'pos_aggregator.adapters.gofood.GoFoodAdapter.pull_menu',
            return_value=_menu(),
        ):
            import_menu_from_aggregator(self.link, kategori=kategori)
        item = ItemMasterPurchase.objects.get(nama='Nasi Goreng')
        self.assertEqual(item.kategori, kategori)

    def test_one_item_error_does_not_abort_the_whole_import(self):
        good = CanonicalMenuItem(
            external_id='ext-1', name='Nasi Goreng', description='',
            price=Decimal('28000'), is_available=True,
        )
        # A None price is invalid for the non-nullable unit_price column —
        # a realistic per-item failure (malformed upstream payload) that must
        # not abort items already processed successfully.
        bad = CanonicalMenuItem(
            external_id='ext-2', name='Item Rusak', description='',
            price=None, is_available=True,
        )
        result = self._import(_menu(items=[good, bad]))
        self.assertIn('Nasi Goreng', result.created_items)


class GrabFoodPullMenuTest(TestCase):
    """GrabFood has no menu of its own to pull — must fail with a clear reason."""

    def test_pull_menu_raises_not_supported(self):
        credential = make_credential(aggregator=AggregatorType.GRABFOOD)
        link = make_store_link(credential, external_store_id='OUTLET-1')
        with self.assertRaises(NotSupported):
            import_menu_from_aggregator(link)
