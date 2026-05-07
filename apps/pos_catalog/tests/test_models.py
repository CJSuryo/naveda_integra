from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from apps.entitas_bisnis.models import EntitasBisnisLv2
from pos_catalog.models import POSCategory, POSProduct, ModifierGroup, ModifierOption, ProductModifierGroup


def make_merchant():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    return MerchantPOSConfig.objects.create(entitas_bisnis=eb)


def make_item_master(nama='Nasi Goreng', tipe='ITM'):
    kat = KategoriItem.objects.create(nama='Makanan', tipe_item=tipe)
    return ItemMasterPurchase.objects.create(nama=nama, tipe_item=tipe, kategori=kat)


class ModifierGroupValidationTest(TestCase):
    def setUp(self):
        self.merchant = make_merchant()

    def test_clean_raises_if_min_greater_than_max(self):
        group = ModifierGroup(
            merchant_config=self.merchant, name='Ukuran',
            is_required=False, min_selections=3, max_selections=1
        )
        with self.assertRaises(ValidationError):
            group.clean()

    def test_clean_raises_if_required_and_min_is_zero(self):
        group = ModifierGroup(
            merchant_config=self.merchant, name='Ukuran',
            is_required=True, min_selections=0, max_selections=1
        )
        with self.assertRaises(ValidationError):
            group.clean()

    def test_clean_passes_valid_required_group(self):
        group = ModifierGroup(
            merchant_config=self.merchant, name='Ukuran',
            is_required=True, min_selections=1, max_selections=1
        )
        group.clean()  # no exception

    def test_clean_passes_valid_optional_multi_group(self):
        group = ModifierGroup(
            merchant_config=self.merchant, name='Topping',
            is_required=False, min_selections=0, max_selections=5
        )
        group.clean()  # no exception


class POSProductTest(TestCase):
    def setUp(self):
        self.merchant = make_merchant()
        self.item = make_item_master()

    def test_create_pos_product(self):
        product = POSProduct.objects.create(
            item_master=self.item,
            merchant_config=self.merchant,
            pos_name='Nasi Goreng Spesial',
            selling_price=25000,
        )
        self.assertEqual(str(product), 'Nasi Goreng Spesial')

    def test_one_item_master_cannot_link_to_two_pos_products(self):
        POSProduct.objects.create(
            item_master=self.item, merchant_config=self.merchant,
            pos_name='Nasi Goreng', selling_price=25000,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            POSProduct.objects.create(
                item_master=self.item, merchant_config=self.merchant,
                pos_name='Duplicate', selling_price=10000,
            )
