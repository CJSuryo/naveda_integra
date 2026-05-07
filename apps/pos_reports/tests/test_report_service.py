import datetime
from decimal import Decimal
from django.db import IntegrityError
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from apps.pos_reports.models import DailySalesSnapshot


def _make_store():
    tipe = TipeEntitas.objects.create(nama='FnB Reports')
    eb = EntitasBisnis.objects.create(nama='Reports Merchant', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Reports')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    return store


class DailySalesSnapshotModelTest(TestCase):

    def setUp(self):
        self.store = _make_store()

    def test_unique_per_store_date(self):
        today = datetime.date.today()
        DailySalesSnapshot.objects.create(store=self.store, date=today)
        with self.assertRaises(IntegrityError):
            DailySalesSnapshot.objects.create(store=self.store, date=today)

    def test_defaults_zero(self):
        snap = DailySalesSnapshot.objects.create(store=self.store, date=datetime.date.today())
        self.assertEqual(snap.total_orders, 0)
        self.assertEqual(snap.gross_sales, Decimal('0'))
