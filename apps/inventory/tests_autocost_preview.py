"""Tests: auto unit cost (per metode costing) + preview jurnal & mutasi."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger


class CurrentUnitCostTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.item.coa_account = self.persediaan
        self.item.save()
        # dua layer harga berbeda: 100 (lebih tua), lalu 120 (lebih baru)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('120'), '2026-01-05', 'adjustment_in', warehouse=self.wh)

    def test_fifo_returns_oldest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='fifo')
        self.assertEqual(c, Decimal('100'))

    def test_lifo_returns_newest_layer_cost(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='lifo')
        self.assertEqual(c, Decimal('120'))

    def test_average_returns_weighted_average(self):
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh, metode='average')
        self.assertEqual(c, Decimal('110'))  # (10*100 + 10*120)/20

    def test_none_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        c = ledger.current_unit_cost(other, self.eb, warehouse=self.wh, metode='fifo')
        self.assertIsNone(c)

    def test_defaults_to_item_method(self):
        self.item.metode_biaya_persediaan = 'lifo'
        self.item.save()
        c = ledger.current_unit_cost(self.item, self.eb, warehouse=self.wh)
        self.assertEqual(c, Decimal('120'))


class StockAvailableEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='u1@example.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM',
                                                      metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('4'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)

    def test_returns_available_and_unit_cost(self):
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': self.item.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertEqual(Decimal(data['available']), Decimal('4'))
        self.assertEqual(Decimal(data['unit_cost']), Decimal('100'))

    def test_unit_cost_null_when_no_stock(self):
        other = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')
        resp = self.client.get('/inventory/api/stock-available/',
                               {'item': other.pk, 'warehouse': self.wh.pk})
        data = resp.json()
        self.assertIsNone(data['unit_cost'])
