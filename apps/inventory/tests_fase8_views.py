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

    # NOTE: test_valuasi_renders + test_valuasi_xlsx_export together make exactly
    # 2 requests to laporan_valuasi, which is the full test-env rate limit for
    # this view (rate_from('export') == '2/m', see naveda_integra/settings/test.py).
    # Do not add a 3rd request to laporan_valuasi in this class without either
    # removing one of these two or bumping/documenting the limit — a 3rd hit
    # will trip the rate limiter and fail with a confusing 429/403.
    def test_valuasi_renders(self):
        self.assertEqual(self.client.get(reverse('inventory:laporan_valuasi')).status_code, 200)

    # NOTE: test_hpp_renders + test_hpp_pdf_export together make exactly 2
    # requests to laporan_hpp — same '2/m' test-env quota constraint as
    # laporan_valuasi above. Don't add a 3rd request to laporan_hpp here.
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

    def test_hpp_pdf_export(self):
        # Uses laporan_hpp (not laporan_valuasi) so it has its own independent
        # rate-limit bucket and doesn't touch the valuasi 2/2min quota above.
        # Exercises the shared print template inventory/_laporan_print.html
        # used by all four Fase 8 report PDF exports.
        resp = self.client.get(reverse('inventory:laporan_hpp'), {'export': 'pdf'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Laporan HPP', resp.content)
        self.assertIn(b'Qty Terjual', resp.content)
        self.assertIn(b'Total HPP', resp.content)
