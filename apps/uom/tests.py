"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase

from apps.purchase.models import ItemMasterPurchase
from .models import UnitOfMeasure, ItemUOM


class UnitOfMeasureModelTests(TestCase):
    def test_create_physical_unit(self):
        kg = UnitOfMeasure.objects.create(
            kode='kg', nama='Kilogram', dimension='weight',
            factor_to_base=Decimal('1000'), is_base=False, is_system=True,
        )
        self.assertEqual(str(kg), 'kg - Kilogram')
        self.assertEqual(kg.factor_to_base, Decimal('1000'))

    def test_packaging_unit_allows_null_factor(self):
        carton = UnitOfMeasure.objects.create(
            kode='carton', nama='Karton', dimension='count',
            factor_to_base=None, is_base=False, is_system=True,
        )
        self.assertIsNone(carton.factor_to_base)

    def test_kode_unique(self):
        UnitOfMeasure.objects.create(kode='pcs', nama='Pieces', dimension='count',
                                     factor_to_base=Decimal('1'), is_base=True)
        with self.assertRaises(Exception):
            UnitOfMeasure.objects.create(kode='pcs', nama='Dup', dimension='count',
                                         factor_to_base=Decimal('1'))


class ItemUOMModelTests(TestCase):
    def setUp(self):
        self.item = ItemMasterPurchase.objects.create(nama='Kopi Sachet', tipe_item='RM')
        self.carton = UnitOfMeasure.objects.create(
            kode='carton', nama='Karton', dimension='count', factor_to_base=None,
        )

    def test_create_item_uom(self):
        iu = ItemUOM.objects.create(
            item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'),
        )
        self.assertEqual(iu.qty_in_stock_uom, Decimal('24'))
        self.assertIn('carton', str(iu))

    def test_unique_item_uom(self):
        ItemUOM.objects.create(item=self.item, uom=self.carton,
                               qty_in_stock_uom=Decimal('24'))
        with self.assertRaises(Exception):
            ItemUOM.objects.create(item=self.item, uom=self.carton,
                                   qty_in_stock_uom=Decimal('12'))
