"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase

from apps.purchase.models import ItemMasterPurchase
from .models import UnitOfMeasure, ItemUOM


class UnitOfMeasureModelTests(TestCase):
    def test_create_physical_unit(self):
        oz = UnitOfMeasure.objects.create(
            kode='oz', nama='Ounce', dimension='weight',
            factor_to_base=Decimal('28.35'), is_base=False, is_system=True,
        )
        self.assertEqual(str(oz), 'oz - Ounce')
        self.assertEqual(oz.factor_to_base, Decimal('28.35'))

    def test_packaging_unit_allows_null_factor(self):
        bag = UnitOfMeasure.objects.create(
            kode='bag', nama='Bag', dimension='count',
            factor_to_base=None, is_base=False, is_system=True,
        )
        self.assertIsNone(bag.factor_to_base)

    def test_kode_unique(self):
        UnitOfMeasure.objects.create(kode='custom_unit', nama='Custom Unit', dimension='count',
                                     factor_to_base=Decimal('1'), is_base=True)
        with self.assertRaises(Exception):
            UnitOfMeasure.objects.create(kode='custom_unit', nama='Dup', dimension='count',
                                         factor_to_base=Decimal('1'))


class ItemUOMModelTests(TestCase):
    def setUp(self):
        self.item = ItemMasterPurchase.objects.create(nama='Kopi Sachet', tipe_item='RM')
        self.bag = UnitOfMeasure.objects.create(
            kode='bag', nama='Bag', dimension='count', factor_to_base=None, is_system=False,
        )

    def test_create_item_uom(self):
        iu = ItemUOM.objects.create(
            item=self.item, uom=self.bag, qty_in_stock_uom=Decimal('24'),
        )
        self.assertEqual(iu.qty_in_stock_uom, Decimal('24'))
        self.assertIn('bag', str(iu))

    def test_unique_item_uom(self):
        ItemUOM.objects.create(item=self.item, uom=self.bag,
                               qty_in_stock_uom=Decimal('24'))
        with self.assertRaises(Exception):
            ItemUOM.objects.create(item=self.item, uom=self.bag,
                                   qty_in_stock_uom=Decimal('12'))


class ItemMasterUOMFieldsTests(TestCase):
    def test_item_has_uom_fields(self):
        pcs = UnitOfMeasure.objects.create(
            kode='test_uom_pcs', nama='Test Pieces', dimension='count',
            factor_to_base=Decimal('1'), is_base=False,
        )
        item = ItemMasterPurchase.objects.create(
            nama='Gula', tipe_item='RM',
            stock_uom=pcs, purchase_uom=pcs, sales_uom=pcs,
        )

        reloaded = ItemMasterPurchase.objects.get(pk=item.pk)

        self.assertEqual(reloaded.stock_uom, pcs)
        self.assertEqual(reloaded.purchase_uom, pcs)
        self.assertEqual(reloaded.sales_uom, pcs)


class SeedUnitsTests(TestCase):
    """Seed runs via migration; data must be present in the test DB."""

    def test_base_unit_per_dimension(self):
        for dim in ('count', 'weight', 'volume', 'length', 'area'):
            bases = UnitOfMeasure.objects.filter(dimension=dim, is_base=True)
            self.assertEqual(bases.count(), 1, f'dimension {dim} must have exactly one base')

    def test_known_units_seeded(self):
        for kode in ('pcs', 'kg', 'g', 'ton', 'mL', 'L', 'mm', 'cm', 'm',
                     'carton', 'box', 'lusin'):
            self.assertTrue(
                UnitOfMeasure.objects.filter(kode=kode, is_system=True).exists(),
                f'{kode} not seeded',
            )

    def test_packaging_units_have_null_factor(self):
        for kode in ('carton', 'box', 'pack', 'dus', 'roll', 'botol'):
            u = UnitOfMeasure.objects.get(kode=kode)
            self.assertIsNone(u.factor_to_base, f'{kode} should have null factor')

    def test_lusin_factor(self):
        self.assertEqual(UnitOfMeasure.objects.get(kode='lusin').factor_to_base,
                         Decimal('12'))
