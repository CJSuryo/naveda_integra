"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase
from django.contrib.admin.sites import AdminSite

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
            factor_to_base=Decimal('1'), is_base=True,
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


class BackfillItemUOMTests(TestCase):
    def test_backfill_sets_pcs_for_null_items(self):
        from apps.uom.backfill import backfill_default_uom
        item = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        self.assertIsNone(item.stock_uom)

        backfill_default_uom(ItemMasterPurchase, UnitOfMeasure)

        item.refresh_from_db()
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.assertEqual(item.stock_uom, pcs)
        self.assertEqual(item.purchase_uom, pcs)
        self.assertEqual(item.sales_uom, pcs)

    def test_backfill_does_not_override_existing(self):
        from apps.uom.backfill import backfill_default_uom
        kg = UnitOfMeasure.objects.get(kode='kg')
        item = ItemMasterPurchase.objects.create(nama='Tepung', tipe_item='RM',
                                                 stock_uom=kg)
        backfill_default_uom(ItemMasterPurchase, UnitOfMeasure)
        item.refresh_from_db()
        self.assertEqual(item.stock_uom, kg)  # unchanged


class ConvertTests(TestCase):
    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.kg = UnitOfMeasure.objects.get(kode='kg')
        self.g = UnitOfMeasure.objects.get(kode='g')
        self.L = UnitOfMeasure.objects.get(kode='L')
        self.mL = UnitOfMeasure.objects.get(kode='mL')
        self.carton = UnitOfMeasure.objects.get(kode='carton')
        self.item_a = ItemMasterPurchase.objects.create(
            nama='Kopi A', tipe_item='RM', stock_uom=self.pcs)
        self.item_b = ItemMasterPurchase.objects.create(
            nama='Kopi B', tipe_item='RM', stock_uom=self.pcs)
        ItemUOM.objects.create(item=self.item_a, uom=self.carton,
                               qty_in_stock_uom=Decimal('24'))
        ItemUOM.objects.create(item=self.item_b, uom=self.carton,
                               qty_in_stock_uom=Decimal('12'))

    def test_identity(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('5'), self.pcs, self.pcs), Decimal('5'))

    def test_physical_universal_kg_to_g(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('2'), self.kg, self.g), Decimal('2000'))

    def test_physical_universal_L_to_mL(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('1.5'), self.L, self.mL), Decimal('1500'))

    def test_packaging_carton_to_pcs_per_item(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('1'), self.carton, self.pcs, item=self.item_a),
                         Decimal('24'))
        self.assertEqual(convert(Decimal('1'), self.carton, self.pcs, item=self.item_b),
                         Decimal('12'))

    def test_packaging_pcs_to_carton(self):
        from apps.uom.conversion import convert
        self.assertEqual(convert(Decimal('48'), self.pcs, self.carton, item=self.item_a),
                         Decimal('2'))

    def test_packaging_without_item_raises(self):
        from apps.uom.conversion import convert, ConversionError
        with self.assertRaises(ConversionError):
            convert(Decimal('1'), self.carton, self.pcs)

    def test_incompatible_raises(self):
        from apps.uom.conversion import convert, ConversionError
        with self.assertRaises(ConversionError):
            convert(Decimal('1'), self.kg, self.pcs, item=self.item_a)


class AdminGuardTests(TestCase):
    def test_system_unit_delete_blocked(self):
        from apps.uom.admin import UnitOfMeasureAdmin
        admin = UnitOfMeasureAdmin(UnitOfMeasure, AdminSite())
        pcs = UnitOfMeasure.objects.get(kode='pcs')

        class MockUser:
            def has_perm(self, perm):
                return True

        class Req:  # minimal request stub
            user = MockUser()

        self.assertFalse(admin.has_delete_permission(Req(), obj=pcs))

    def test_custom_unit_delete_allowed(self):
        from apps.uom.admin import UnitOfMeasureAdmin
        admin = UnitOfMeasureAdmin(UnitOfMeasure, AdminSite())
        custom = UnitOfMeasure.objects.create(
            kode='sak', nama='Sak', dimension='count', factor_to_base=None,
            is_system=False)

        class MockUser:
            def has_perm(self, perm):
                return True

        class Req:
            user = MockUser()

        self.assertTrue(admin.has_delete_permission(Req(), obj=custom))
