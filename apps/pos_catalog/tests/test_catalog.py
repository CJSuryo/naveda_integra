from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import KategoriItem, ItemMasterPurchase
from pos_catalog.models import CatalogItem, CatalogItemLog
from apps.accounts.models import User


def make_eb(nama='Kafe Test'):
    tipe = TipeEntitas.objects.create(nama=f'FnB-{nama}')
    return EntitasBisnis.objects.create(nama=nama, tipe_entitas=tipe, relasi='pelanggan')


def make_item(nama='Kopi', tipe='FG'):
    kat, _ = KategoriItem.objects.get_or_create(nama=f'Kat-{tipe}', defaults={'tipe_item': tipe})
    return ItemMasterPurchase.objects.create(nama=nama, tipe_item=tipe, kategori=kat)


class CatalogItemModelTest(TestCase):
    def setUp(self):
        self.eb = make_eb()
        self.item = make_item()

    def test_create_catalog_item(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb,
            item=self.item,
            selling_price=Decimal('15000'),
        )
        self.assertEqual(ci.is_active, True)
        self.assertEqual(ci.display_order, 1)

    def test_str_uses_display_name_if_set(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item,
            selling_price=Decimal('10000'), display_name='Kopi Susu',
        )
        self.assertIn('Kopi Susu', str(ci))

    def test_str_falls_back_to_item_nama(self):
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item,
            selling_price=Decimal('10000'),
        )
        self.assertIn(self.item.nama, str(ci))

    def test_unique_together_eb_item(self):
        CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('10000'),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CatalogItem.objects.create(
                entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('20000'),
            )

    def test_display_order_auto_increments(self):
        item2 = make_item('Teh', 'FG')
        ci1 = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('10000'),
        )
        ci2 = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=item2, selling_price=Decimal('8000'),
        )
        self.assertEqual(ci1.display_order, 1)
        self.assertEqual(ci2.display_order, 2)


class CatalogItemLogTest(TestCase):
    def setUp(self):
        self.eb = make_eb('LogEB')
        self.item = make_item('LogItem')
        self.ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=self.item, selling_price=Decimal('5000'),
        )

    def test_create_log(self):
        log = CatalogItemLog.objects.create(
            catalog_item=self.ci,
            field_name='selling_price',
            old_value='5000',
            new_value='6000',
        )
        self.assertEqual(log.catalog_item, self.ci)
        self.assertIsNone(log.changed_by)

    def test_log_cascade_delete(self):
        CatalogItemLog.objects.create(
            catalog_item=self.ci, field_name='is_active',
            old_value='True', new_value='False',
        )
        self.ci.delete()
        self.assertEqual(CatalogItemLog.objects.count(), 0)
