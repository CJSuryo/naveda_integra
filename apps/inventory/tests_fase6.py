"""Tests Fase 6 — transaksi & kontrol stok."""
from decimal import Decimal
from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import StockMovement
from apps.inventory import ledger


class MovementTypeChoicesTests(TestCase):
    def test_new_movement_types_registered(self):
        codes = {c for c, _ in StockMovement.MOVEMENT_TYPE_CHOICES}
        for expected in {
            'adjustment_in', 'adjustment_out', 'opname_in', 'opname_out',
            'transfer_in', 'transfer_out', 'return_customer', 'return_supplier',
        }:
            self.assertIn(expected, codes)


class ReversalSetTests(TestCase):
    def test_outflow_set_includes_fase6(self):
        for t in {'adjustment_out', 'opname_out', 'transfer_out', 'return_supplier'}:
            self.assertIn(t, ledger.OUTFLOW_MOVEMENT_TYPES)

    def test_inflow_set_includes_fase6(self):
        for t in {'adjustment_in', 'opname_in', 'transfer_in', 'return_customer'}:
            self.assertIn(t, ledger.INFLOW_MOVEMENT_TYPES)


from apps.master_data.models import Akun


class StockAdjustmentModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='Gudang 1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.akun = Akun.objects.create(kode_akun='5.9.1', nama='Selisih Persediaan')

    def test_create_header_generates_nomor(self):
        from apps.inventory.models import StockAdjustment
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.akun,
        )
        self.assertTrue(h.nomor.startswith('TRX-ADJ-'))
        self.assertEqual(h.status, 'draft')

    def test_item_signed_qty(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.akun,
        )
        d = StockAdjustmentItem.objects.create(
            adjustment=h, item=self.item, qty=Decimal('-3'), unit_cost=Decimal('5'),
        )
        self.assertEqual(d.qty, Decimal('-3'))


class ProcessAdjustmentTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih Persediaan')

    def _header(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        h = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih,
        )
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item,
                                           qty=Decimal('10'), unit_cost=Decimal('5'))
        return h

    def test_increase_creates_inflow_and_balanced_journal(self):
        from apps.inventory.services import process_adjustment
        from apps.inventory.ledger import get_available_stock
        h = self._header()
        header = process_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'posted')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('10'))
        deb = sum(d.debit for d in header.details.all())
        kre = sum(d.kredit for d in header.details.all())
        self.assertEqual(deb, kre)
        self.assertEqual(deb, Decimal('50'))

    def test_decrease_consumes_stock(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment
        record_inflow(self.item, self.eb, None, None, Decimal('20'), Decimal('4'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = StockAdjustment.objects.create(tanggal='2026-02-02', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item, qty=Decimal('-5'))
        process_adjustment(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('15'))
