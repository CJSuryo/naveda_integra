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


class HppReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_hpp_fifo_across_two_layers(self):
        # 10 @ 4, then 10 @ 6; sell 15 FIFO -> HPP = 10*4 + 5*6 = 70
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('6'), date(2026, 1, 2), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('15'),
                             date(2026, 1, 10), 'sale_out', warehouse=self.wh)

        result = reports.hpp_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(len(result['rows']), 1)
        row = result['rows'][0]
        self.assertEqual(row['qty_terjual'], Decimal('15'))
        self.assertEqual(row['total_hpp'], Decimal('70'))
        self.assertEqual(result['grand_total_hpp'], Decimal('70'))

    def test_hpp_excludes_out_of_range(self):
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(self.item, self.eb, None, None, Decimal('5'),
                             date(2026, 2, 10), 'sale_out', warehouse=self.wh)
        result = reports.hpp_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['grand_total_hpp'], Decimal('0'))


class VelocityReportTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')

    def test_fast_tag_without_movement_flags_mismatch(self):
        item = ItemMasterPurchase.objects.create(
            nama='Kopi', tipe_item='RM', velocity_category='fast')
        ledger.record_inflow(item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        rows = reports.velocity_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        row = next(r for r in rows if r['item'].pk == item.pk)
        self.assertEqual(row['qty_keluar'], Decimal('0'))
        self.assertTrue(row['mismatch_flag'])
        self.assertEqual(row['on_hand'], Decimal('10'))

    def test_movement_metrics_computed(self):
        item = ItemMasterPurchase.objects.create(
            nama='Teh', tipe_item='RM', velocity_category='slow')
        ledger.record_inflow(item, self.eb, None, None, Decimal('10'),
                             Decimal('4'), date(2026, 1, 1), 'purchase_in', warehouse=self.wh)
        ledger.consume_stock(item, self.eb, None, None, Decimal('6'),
                             date(2026, 1, 20), 'sale_out', warehouse=self.wh)
        rows = reports.velocity_report({self.eb.pk}, date(2026, 1, 1), date(2026, 1, 31))
        row = next(r for r in rows if r['item'].pk == item.pk)
        self.assertEqual(row['qty_keluar'], Decimal('6'))
        self.assertEqual(row['jumlah_gerakan'], 1)
        self.assertEqual(row['on_hand'], Decimal('4'))
