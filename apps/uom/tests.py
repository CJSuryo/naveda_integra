"""Tests for the uom app."""
from decimal import Decimal

from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.purchase.models import ItemMasterPurchase
from .models import UnitOfMeasure, ItemUOM

User = get_user_model()


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


class ForDropdownOrderingTests(TestCase):
    def setUp(self):
        # Deliberately created out of the expected output order, and with
        # unique kodes so this test doesn't depend on the seeded system units.
        self.w_kg = UnitOfMeasure.objects.create(
            kode='t_kg', nama='Test Kg', dimension='weight', factor_to_base=Decimal('1'))
        self.c_box = UnitOfMeasure.objects.create(
            kode='t_box', nama='Test Box', dimension='count', factor_to_base=None)
        self.w_gram = UnitOfMeasure.objects.create(
            kode='t_gram', nama='Test Gram', dimension='weight', factor_to_base=Decimal('0.001'))
        self.c_pcs = UnitOfMeasure.objects.create(
            kode='t_pcs', nama='Test Pcs', dimension='count', factor_to_base=Decimal('1'))

    def test_orders_by_dimension_then_factor_then_kode(self):
        kodes = list(
            UnitOfMeasure.objects
            .filter(kode__in=['t_kg', 't_box', 't_gram', 't_pcs'])
            .for_dropdown()
            .values_list('kode', flat=True)
        )
        # count (DIMENSION_CHOICES[0]) before weight (DIMENSION_CHOICES[1]);
        # within count: factor=1 before null; within weight: 0.001 before 1.
        self.assertEqual(kodes, ['t_pcs', 't_box', 't_gram', 't_kg'])


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


class UnitViewTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            email='u1@example.com', password='pw123456', name='U1')
        self.client.force_login(self.client_user)

    def test_list_renders(self):
        resp = self.client.get(reverse('uom:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'pcs')  # seeded unit visible

    def test_create_custom_unit(self):
        resp = self.client.post(reverse('uom:create'), {
            'kode': 'sak', 'nama': 'Sak', 'dimension': 'count',
            'factor_to_base': '', 'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(UnitOfMeasure.objects.filter(kode='sak').exists())


class ItemMasterAdminInlineTests(TestCase):
    def test_itemuom_inline_registered(self):
        from django.contrib import admin as dj_admin
        from apps.purchase.models import ItemMasterPurchase
        from apps.uom.models import ItemUOM
        model_admin = dj_admin.site._registry[ItemMasterPurchase]
        inline_models = [inline.model for inline in model_admin.inlines]
        self.assertIn(ItemUOM, inline_models)


class ConvertInputToBaseTests(TestCase):
    def setUp(self):
        from apps.uom.conversion import convert_input_to_base
        self._convert = staticmethod(convert_input_to_base)
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.carton = UnitOfMeasure.objects.create(
            kode='ctn-x', nama='Carton', dimension='count', factor_to_base=None)
        self.item = ItemMasterPurchase.objects.create(
            nama='Konv', tipe_item='ITM', stock_uom=self.pcs)
        ItemUOM.objects.create(item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'))

    def test_none_uom_passthrough(self):
        from apps.uom.conversion import convert_input_to_base
        qty, price = convert_input_to_base(self.item, None, Decimal('5'), Decimal('1000'))
        self.assertEqual(qty, Decimal('5'))
        self.assertEqual(price, Decimal('1000'))

    def test_stock_uom_passthrough(self):
        from apps.uom.conversion import convert_input_to_base
        qty, price = convert_input_to_base(self.item, self.pcs, Decimal('5'), Decimal('1000'))
        self.assertEqual(qty, Decimal('5'))
        self.assertEqual(price, Decimal('1000'))

    def test_carton_to_pcs_converts_qty_and_price(self):
        from apps.uom.conversion import convert_input_to_base
        # 10 carton @ Rp 24.000/carton, 1 carton = 24 pcs
        qty, price = convert_input_to_base(self.item, self.carton, Decimal('10'), Decimal('24000'))
        self.assertEqual(qty, Decimal('240'))          # 10 * 24
        self.assertEqual(price, Decimal('1000'))        # total 240.000 / 240 pcs


class MasterSatuanMenuTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='menu@example.com', password='pw123456', name='M')
        self.client.force_login(self.user)

    def test_sidebar_links_master_satuan(self):
        # Halaman inventory memuat base.html dengan submenu Inventory
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('uom:list'))


class ItemUOMCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='iu@example.com', password='pw123456', name='I')
        self.client.force_login(self.user)
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.carton = UnitOfMeasure.objects.create(
            kode='ctn-t', nama='Carton Test', dimension='count', factor_to_base=None)
        self.item = ItemMasterPurchase.objects.create(
            nama='Item A', tipe_item='ITM', stock_uom=self.pcs)

    def test_list_renders(self):
        ItemUOM.objects.create(item=self.item, uom=self.carton, qty_in_stock_uom=Decimal('24'))
        resp = self.client.get(reverse('uom:conversion_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '24')

    def test_create(self):
        resp = self.client.post(reverse('uom:conversion_create'), {
            'item': self.item.pk, 'uom': self.carton.pk, 'qty_in_stock_uom': '24',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ItemUOM.objects.filter(item=self.item, uom=self.carton).exists())

    def test_reject_uom_equal_stock_uom(self):
        resp = self.client.post(reverse('uom:conversion_create'), {
            'item': self.item.pk, 'uom': self.pcs.pk, 'qty_in_stock_uom': '1',
        })
        self.assertEqual(resp.status_code, 200)  # form invalid, re-render
        self.assertFalse(ItemUOM.objects.filter(item=self.item, uom=self.pcs).exists())


class ItemUOMFormGroupedDropdownTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='grp@example.com', password='pw123456', name='G')
        self.client.force_login(self.user)
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(
            nama='Grouped Item', tipe_item='ITM', stock_uom=self.pcs)

    def test_conversion_create_form_renders_optgroups_in_dimension_order(self):
        resp = self.client.get(reverse('uom:conversion_create'))
        content = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        count_pos = content.index('<optgroup label="Count / Jumlah">')
        weight_pos = content.index('<optgroup label="Berat">')
        volume_pos = content.index('<optgroup label="Volume">')
        length_pos = content.index('<optgroup label="Panjang">')
        area_pos = content.index('<optgroup label="Luas">')
        self.assertTrue(count_pos < weight_pos < volume_pos < length_pos < area_pos)
