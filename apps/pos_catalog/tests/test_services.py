from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.purchase.models import ItemMasterPurchase, KategoriItem, FIFOBatch
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from pos_catalog.models import POSProduct, ProductStoreAvailability, ModifierGroup, ModifierOption, ProductModifierGroup
from pos_catalog.services.product_service import get_available_products, check_stock, validate_modifier_selections


def make_setup():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Cabang Utama')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    kat = KategoriItem.objects.create(nama='Makanan', tipe_item='ITM')
    item = ItemMasterPurchase.objects.create(nama='Nasi Goreng', tipe_item='ITM', kategori=kat)
    product = POSProduct.objects.create(
        item_master=item, merchant_config=merchant,
        pos_name='Nasi Goreng', selling_price=25000, is_available=True,
    )
    return eb, lv2, merchant, store, item, product


class GetAvailableProductsTest(TestCase):
    def test_returns_available_products(self):
        eb, lv2, merchant, store, item, product = make_setup()
        result = get_available_products(store)
        self.assertIn(product, result)

    def test_excludes_unavailable_products(self):
        eb, lv2, merchant, store, item, product = make_setup()
        product.is_available = False
        product.save()
        result = get_available_products(store)
        self.assertNotIn(product, result)

    def test_store_override_can_disable_available_product(self):
        eb, lv2, merchant, store, item, product = make_setup()
        ProductStoreAvailability.objects.create(product=product, store=store, is_available=False)
        result = get_available_products(store)
        self.assertNotIn(product, result)

    def test_store_override_can_enable_unavailable_product(self):
        eb, lv2, merchant, store, item, product = make_setup()
        product.is_available = False
        product.save()
        ProductStoreAvailability.objects.create(product=product, store=store, is_available=True)
        result = get_available_products(store)
        self.assertIn(product, result)


class CheckStockTest(TestCase):
    def test_returns_true_when_stock_sufficient(self):
        eb, lv2, merchant, store, item, product = make_setup()
        FIFOBatch.objects.create(
            item=item,
            tanggal='2026-05-01',
            quantity_in=Decimal('10'),
            unit_price=Decimal('5000'),
            remaining_qty=Decimal('10'),
        )
        in_stock, available_qty = check_stock(product, Decimal('5'), eb)
        self.assertTrue(in_stock)
        self.assertEqual(available_qty, Decimal('10'))

    def test_returns_true_for_non_tracked_product(self):
        eb, lv2, merchant, store, item, product = make_setup()
        product.track_inventory = False
        product.save()
        in_stock, available_qty = check_stock(product, Decimal('999'), eb)
        self.assertTrue(in_stock)

    def test_returns_false_when_stock_insufficient(self):
        eb, lv2, merchant, store, item, product = make_setup()
        in_stock, available_qty = check_stock(product, Decimal('5'), eb)
        self.assertFalse(in_stock)
        self.assertEqual(available_qty, Decimal('0'))


class ValidateModifierSelectionsTest(TestCase):
    def setUp(self):
        eb, lv2, self.merchant, store, item, self.product = make_setup()
        self.required_group = ModifierGroup.objects.create(
            merchant_config=self.merchant, name='Ukuran',
            is_required=True, min_selections=1, max_selections=1
        )
        self.option_s = ModifierOption.objects.create(group=self.required_group, name='S', additional_price=0)
        self.option_l = ModifierOption.objects.create(group=self.required_group, name='L', additional_price=5000)
        self.optional_group = ModifierGroup.objects.create(
            merchant_config=self.merchant, name='Topping',
            is_required=False, min_selections=0, max_selections=3
        )
        self.topping1 = ModifierOption.objects.create(group=self.optional_group, name='Telur', additional_price=3000)
        self.topping2 = ModifierOption.objects.create(group=self.optional_group, name='Keju', additional_price=5000)
        ProductModifierGroup.objects.create(product=self.product, modifier_group=self.required_group)
        ProductModifierGroup.objects.create(product=self.product, modifier_group=self.optional_group)

    def test_no_errors_for_valid_selection(self):
        errors = validate_modifier_selections(self.product, [self.option_s.pk])
        self.assertEqual(errors, [])

    def test_error_when_required_group_missing(self):
        errors = validate_modifier_selections(self.product, [])
        self.assertTrue(any('Ukuran' in e for e in errors))

    def test_error_when_exceeding_max_selections(self):
        topping3 = ModifierOption.objects.create(group=self.optional_group, name='Ayam', additional_price=8000)
        topping4 = ModifierOption.objects.create(group=self.optional_group, name='Udang', additional_price=10000)
        errors = validate_modifier_selections(
            self.product,
            [self.option_s.pk, self.topping1.pk, self.topping2.pk, topping3.pk, topping4.pk]
        )
        self.assertTrue(any('Topping' in e for e in errors))

    def test_no_errors_with_no_optional_selections(self):
        errors = validate_modifier_selections(self.product, [self.option_s.pk])
        self.assertEqual(errors, [])
