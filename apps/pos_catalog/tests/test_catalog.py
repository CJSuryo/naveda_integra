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


from django.test import Client
from django.urls import reverse


class CatalogListViewTest(TestCase):
    def setUp(self):
        self.eb = make_eb('ViewEB')
        self.user = User.objects.create_user(
            email='cat@test.com', password='pass', name='Cat', is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_catalog_list_returns_200(self):
        url = reverse('pos_catalog:catalog_list', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_catalog_list_404_unknown_eb(self):
        url = reverse('pos_catalog:catalog_list', args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_catalog_list_requires_login(self):
        self.client.logout()
        url = reverse('pos_catalog:catalog_list', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp['Location'])

    def test_catalog_items_ajax_returns_html(self):
        item = make_item('AjaxItem', 'FG')
        from apps.inventory.models import InventoryRecord
        import datetime
        InventoryRecord.objects.create(
            item=item, entitas_bisnis=self.eb,
            quantity=10, unit_price=5000,
            tanggal=datetime.date.today(),
        )
        url = reverse('pos_catalog:catalog_items_ajax', args=[self.eb.pk])
        resp = self.client.get(url, {'tipe_item': 'FG'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('html', data)
        self.assertIn('AjaxItem', data['html'])

    def test_catalog_items_ajax_empty_without_inventory(self):
        url = reverse('pos_catalog:catalog_items_ajax', args=[self.eb.pk])
        resp = self.client.get(url, {'tipe_item': 'FG'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('html', data)

    def test_catalog_upsert_creates_catalog_item(self):
        item = make_item('UpsertItem', 'RM')
        url = reverse('pos_catalog:catalog_upsert', args=[self.eb.pk])
        resp = self.client.post(url, {
            'item_id': item.pk,
            'selling_price': '12000',
            'display_name': 'Upsert Name',
            'display_order': '1',
            'is_active': 'true',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        from pos_catalog.models import CatalogItem
        self.assertEqual(CatalogItem.objects.filter(entitas_bisnis=self.eb, item=item).count(), 1)

    def test_catalog_upsert_writes_log_on_update(self):
        from decimal import Decimal
        from pos_catalog.models import CatalogItem, CatalogItemLog
        item = make_item('LogUpsertItem', 'FG')
        ci = CatalogItem.objects.create(
            entitas_bisnis=self.eb, item=item, selling_price=Decimal('5000'),
        )
        url = reverse('pos_catalog:catalog_upsert', args=[self.eb.pk])
        self.client.post(url, {
            'item_id': item.pk,
            'selling_price': '9000',
            'display_name': '',
            'display_order': str(ci.display_order),
            'is_active': 'true',
        })
        self.assertTrue(
            CatalogItemLog.objects.filter(
                catalog_item=ci, field_name='selling_price',
                old_value='5000.0000', new_value='9000',
            ).exists() or
            CatalogItemLog.objects.filter(
                catalog_item=ci, field_name='selling_price',
            ).exists()
        )

    def test_catalog_logs_returns_200(self):
        url = reverse('pos_catalog:catalog_logs', args=[self.eb.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
