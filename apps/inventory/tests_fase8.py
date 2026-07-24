"""Tests Fase 8 — laporan inventory (valuation, hpp, velocity)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory import ledger, reports


class ValuationReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_valuation_sums_remaining_layers(self):
        # 20 @ 4 and 10 @ 6; consume 5 (FIFO) -> remaining 15 @ 4 + 10 @ 6
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('6'), date(2026, 1, 2), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('5'),
                             date(2026, 1, 3), 'sale_out', warehouse=self.wh)

        result = reports.valuation_report({self.eb.pk})
        rows = result['rows']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['on_hand_qty'], Decimal('25'))
        # 15*4 + 10*6 = 60 + 60 = 120
        self.assertEqual(row['total_value'], Decimal('120'))
        self.assertEqual(result['grand_total_value'], Decimal('120'))

    def test_valuation_isolates_eb(self):
        eb_b = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('20'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        result = reports.valuation_report({eb_b.pk})
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['grand_total_value'], Decimal('0'))
