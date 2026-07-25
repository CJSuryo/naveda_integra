"""Smoke tests Fase 8 — halaman laporan merender 200 + export xlsx."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger


class ReportViewSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='u1@example.com', password='pw12345', name='U1')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('5'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)

    def test_hub_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_hub')).status_code, 200)

    def test_valuasi_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_valuasi')).status_code, 200)

    def test_hpp_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_hpp')).status_code, 200)

    def test_velocity_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_velocity')).status_code, 200)

    def test_register_renders(self):
        self.assertEqual(self.client.get(reverse('aset_tetap:laporan_register')).status_code, 200)

    def test_valuasi_xlsx_export(self):
        resp = self.client.get(reverse('inventory:laporan_valuasi'), {'export': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
