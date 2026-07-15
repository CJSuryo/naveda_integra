"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase

from .models import UnitOfMeasure


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
