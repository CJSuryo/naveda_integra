"""Unit tests for the inventory app."""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from .models import MutasiInventoryHeader, MutasiInventoryDetail, InventoryRecord

User = get_user_model()


from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase as DjangoTestCase

from apps.inventory.models import StockMovement, StockConsumption


class StockMovementModelTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_inflow_layer(self):
        mv = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('10'),
        )
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertIn('purchase_in', str(mv))

    def test_stock_consumption_links_out_and_in(self):
        inflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-01',
            movement_type='purchase_in', qty=Decimal('10'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('4'),
        )
        outflow = StockMovement.objects.create(
            item=self.item, entitas_bisnis=self.eb, tanggal='2026-01-02',
            movement_type='sale_out', qty=Decimal('-6'), unit_cost=Decimal('5'),
            remaining_qty=Decimal('0'),
        )
        alloc = StockConsumption.objects.create(
            out_movement=outflow, in_movement=inflow,
            qty=Decimal('6'), unit_cost=Decimal('5'),
        )
        self.assertEqual(alloc.in_movement, inflow)
        self.assertEqual(alloc.out_movement, outflow)


class RecordInflowTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.item = ItemMasterPurchase.objects.create(nama='Teh', tipe_item='RM')

    def test_record_inflow_creates_layer(self):
        from apps.inventory.ledger import record_inflow
        mv = record_inflow(
            self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
            '2026-01-01', 'purchase_in',
        )
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertEqual(mv.movement_type, 'purchase_in')

    def test_available_stock_lv1_only(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in')
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('5'),
                      '2026-01-02', 'purchase_in')
        self.assertEqual(get_available_stock(self.item, self.eb), Decimal('14'))

    def test_available_stock_hierarchical_sums_parent(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        # 6 di lv3, 10 di lv1 → dari sudut pandang lv3 tersedia 16 (naik ke induk)
        record_inflow(self.item, self.eb, self.lv2, self.lv3, Decimal('6'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in')
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3),
            Decimal('16'),
        )

    def test_available_stock_sibling_isolated(self):
        from apps.entitas_bisnis.models import EntitasBisnisLv3
        from apps.inventory.ledger import record_inflow, get_available_stock
        sibling = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        record_inflow(self.item, self.eb, self.lv2, self.lv3, Decimal('6'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        # Dari sudut pandang sibling (Outlet B), stok Outlet A tak terlihat (0)
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, sibling),
            Decimal('0'),
        )

    def test_available_stock_sibling_sees_shared_but_not_private(self):
        from apps.entitas_bisnis.models import EntitasBisnisLv3
        from apps.inventory.ledger import record_inflow, get_available_stock
        sibling = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        # Private stock at Outlet A only
        record_inflow(self.item, self.eb, self.lv2, self.lv3, Decimal('6'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        # Shared stock at pure lv1 (visible to both branches via hierarchical fallback)
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in')
        # Outlet A sees its own private 6 + the shared 10 = 16
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3),
            Decimal('16'),
        )
        # Outlet B (sibling) sees ONLY the shared 10 — never Outlet A's private 6
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, sibling),
            Decimal('10'),
        )


class ConsumeStockNonBulkTests(DjangoTestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            EntitasBisnis as EB, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EB.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        self.item = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')

    def _inflow(self, qty, cost, tanggal, lv2=None, lv3=None):
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, lv2, lv3, Decimal(qty),
                             Decimal(cost), tanggal, 'purchase_in')

    def test_fifo_order_and_cogs(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        self._inflow('10', '8', '2026-01-02')
        result = consume_stock(self.item, self.eb, None, None, Decimal('12'),
                               '2026-01-03', 'sale_out')
        # 10@5 + 2@8 = 66
        self.assertEqual(result.total_cost, Decimal('66'))
        self.assertFalse(result.report.used_fallback)

    def test_insufficient_raises(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._inflow('5', '5', '2026-01-01')
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, None, None, Decimal('9'),
                          '2026-01-03', 'sale_out')

    def test_cross_branch_leak_prevented(self):
        """Regresi bug §A-4: jual di Outlet A tak boleh makan stok Outlet B."""
        from apps.inventory.ledger import consume_stock, InsufficientStockError, get_available_stock
        self._inflow('10', '5', '2026-01-01', lv2=self.lv2, lv3=self.lv3b)  # stok B
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, self.lv2, self.lv3a, Decimal('1'),
                          '2026-01-03', 'sale_out')
        # Stok B tetap utuh
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3b),
            Decimal('10'),
        )

    def test_hierarchical_fallback_to_parent(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('3', '5', '2026-01-01', lv2=self.lv2, lv3=self.lv3a)  # 3 di lv3
        self._inflow('10', '5', '2026-01-02')                              # 10 di lv1
        result = consume_stock(self.item, self.eb, self.lv2, self.lv3a, Decimal('8'),
                               '2026-01-03', 'sale_out')
        self.assertTrue(result.report.used_fallback)
        levels = {row['level']: row['qty'] for row in result.report.by_level}
        self.assertEqual(levels['lv3'], Decimal('3'))
        self.assertEqual(levels['lv1'], Decimal('5'))

    def test_remaining_qty_decremented(self):
        from apps.inventory.ledger import consume_stock
        layer = self._inflow('10', '5', '2026-01-01')
        consume_stock(self.item, self.eb, None, None, Decimal('4'),
                      '2026-01-03', 'sale_out')
        layer.refresh_from_db()
        self.assertEqual(layer.remaining_qty, Decimal('6'))

    def test_atomicity_no_partial_commit_on_shortfall(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        from apps.inventory.models import StockMovement, StockConsumption
        layer = self._inflow('5', '5', '2026-01-01')
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, None, None, Decimal('9'),
                          '2026-01-03', 'sale_out')
        layer.refresh_from_db()
        self.assertEqual(layer.remaining_qty, Decimal('5'))
        self.assertFalse(StockMovement.objects.filter(movement_type='sale_out').exists())
        self.assertFalse(StockConsumption.objects.exists())

    def test_source_attached_to_outflow(self):
        from apps.inventory.ledger import consume_stock
        self._inflow('10', '5', '2026-01-01')
        # Use self.item itself as a stand-in "source" object — any saved model instance works.
        result = consume_stock(self.item, self.eb, None, None, Decimal('4'),
                               '2026-01-03', 'sale_out', source=self.item)
        from django.contrib.contenttypes.models import ContentType
        expected_ct = ContentType.objects.get_for_model(type(self.item))
        self.assertEqual(result.out_movement.source_content_type, expected_ct)
        self.assertEqual(result.out_movement.source_object_id, self.item.pk)


class ConsumeStockBulkTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Pasir', tipe_item='RMB')

    def _bulk_inflow(self, total_value, tanggal):
        # Bulk: qty=1, unit_cost=total_value
        from apps.inventory.ledger import record_inflow
        return record_inflow(self.item, self.eb, None, None, Decimal('1'),
                             Decimal(total_value), tanggal, 'purchase_in')

    def test_bulk_value_deduction(self):
        from apps.inventory.ledger import consume_stock
        layer1 = self._bulk_inflow('1000', '2026-01-01')
        layer2 = self._bulk_inflow('500', '2026-01-02')
        # Konsumsi nilai 1200 → habiskan layer 1000, sisakan 300 dari layer 500
        result = consume_stock(self.item, self.eb, None, None, Decimal('1200'),
                               '2026-01-03', 'sale_out')
        self.assertEqual(result.total_cost, Decimal('1200'))

        layer1.refresh_from_db()
        layer2.refresh_from_db()
        # Layer 1 (value 1000) fully consumed
        self.assertEqual(layer1.remaining_qty, Decimal('0'))
        # Layer 2 (value 500) has 300 left: remaining_qty = 300/500 = 0.6
        self.assertEqual(layer2.remaining_qty, Decimal('0.6'))

        # Per-layer StockConsumption.unit_cost is the LAYER's own original cost,
        # not the value taken from it in this consumption.
        unit_costs = sorted(a.unit_cost for a in result.allocations)
        self.assertEqual(unit_costs, [Decimal('500'), Decimal('1000')])

    def test_bulk_insufficient_value_raises(self):
        from apps.inventory.ledger import consume_stock, InsufficientStockError
        self._bulk_inflow('300', '2026-01-01')
        with self.assertRaises(InsufficientStockError):
            consume_stock(self.item, self.eb, None, None, Decimal('900'),
                          '2026-01-03', 'sale_out')


class MirrorAndReverseTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def _inflow_with_legacy(self, qty, cost, tanggal):
        from apps.purchase.models import FIFOBatch
        from apps.inventory.models import InventoryRecord
        from apps.inventory.ledger import record_inflow
        batch = FIFOBatch.objects.create(
            item=self.item, tanggal=tanggal, quantity_in=Decimal(qty),
            unit_price=Decimal(cost), remaining_qty=Decimal(qty),
        )
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal(qty),
            unit_price=Decimal(cost), tanggal=tanggal,
        )
        mv = record_inflow(self.item, self.eb, None, None, Decimal(qty), Decimal(cost),
                          tanggal, 'purchase_in',
                          legacy_fifo_batch=batch, legacy_inventory_record=rec)
        return mv, batch, rec

    def test_consume_mirrors_legacy(self):
        from apps.inventory.ledger import consume_stock
        mv, batch, rec = self._inflow_with_legacy('10', '5', '2026-01-01')
        consume_stock(self.item, self.eb, None, None, Decimal('4'),
                      '2026-01-03', 'sale_out')
        batch.refresh_from_db(); rec.refresh_from_db()
        self.assertEqual(batch.remaining_qty, Decimal('6'))
        self.assertEqual(rec.quantity, Decimal('6'))

    def test_reverse_restores_everything(self):
        from apps.inventory.ledger import consume_stock, reverse_movements
        from apps.inventory.models import StockMovement, StockConsumption
        mv, batch, rec = self._inflow_with_legacy('10', '5', '2026-01-01')
        result = consume_stock(self.item, self.eb, None, None, Decimal('4'),
                               '2026-01-03', 'sale_out', source=rec)
        reverse_movements(rec)
        mv.refresh_from_db(); batch.refresh_from_db(); rec.refresh_from_db()
        self.assertEqual(mv.remaining_qty, Decimal('10'))
        self.assertEqual(batch.remaining_qty, Decimal('10'))
        self.assertEqual(rec.quantity, Decimal('10'))
        self.assertFalse(
            StockMovement.objects.filter(movement_type='sale_out').exists())
        self.assertFalse(StockConsumption.objects.exists())

    def test_reverse_restores_bulk_value(self):
        """Bulk item variant: reversal must restore layer VALUE, not qty."""
        from apps.purchase.models import ItemMasterPurchase as IMP
        from apps.inventory.ledger import record_inflow, consume_stock, reverse_movements
        bulk_item = IMP.objects.create(nama='Pasir', tipe_item='RMB')
        layer = record_inflow(bulk_item, self.eb, None, None, Decimal('1'),
                              Decimal('1000'), '2026-01-01', 'purchase_in')
        result = consume_stock(bulk_item, self.eb, None, None, Decimal('400'),
                               '2026-01-03', 'sale_out', source=self.item)
        layer.refresh_from_db()
        # 1000 - 400 = 600 value left; remaining_qty = 600/1000 = 0.6
        self.assertEqual(layer.remaining_qty, Decimal('0.6'))
        reverse_movements(self.item)
        layer.refresh_from_db()
        self.assertEqual(layer.remaining_qty, Decimal('1'))

    def test_consume_mirrors_batch_value(self):
        """Regression test: FIFOBatch.batch_value must stay in sync, not go stale."""
        from apps.inventory.ledger import consume_stock
        mv, batch, rec = self._inflow_with_legacy('10', '5', '2026-01-01')
        consume_stock(self.item, self.eb, None, None, Decimal('4'),
                      '2026-01-03', 'sale_out')
        batch.refresh_from_db()
        # 6 remaining @ unit_price 5 = 30
        self.assertEqual(batch.batch_value, Decimal('30'))

    def test_consume_without_legacy_links_does_not_error(self):
        """Layers with no legacy_fifo_batch/legacy_inventory_record must be handled gracefully."""
        from apps.inventory.ledger import record_inflow, consume_stock
        layer = record_inflow(self.item, self.eb, None, None, Decimal('10'),
                              Decimal('5'), '2026-01-01', 'purchase_in')
        # No legacy_fifo_batch/legacy_inventory_record passed — both None.
        result = consume_stock(self.item, self.eb, None, None, Decimal('4'),
                               '2026-01-03', 'sale_out')
        self.assertEqual(result.total_cost, Decimal('20'))
        layer.refresh_from_db()
        self.assertEqual(layer.remaining_qty, Decimal('6'))


class InventoryModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)

    def test_mutasi_header_str(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        self.assertIn(str(h.id), str(h))

    def test_mutasi_detail_str(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        d = MutasiInventoryDetail.objects.create(mutasi_inventory_header=h)
        self.assertIn(str(h.id), str(d))

    def test_cascade_delete(self):
        h = MutasiInventoryHeader.objects.create(entitas_bisnis=self.entitas)
        MutasiInventoryDetail.objects.create(mutasi_inventory_header=h)
        h.delete()
        self.assertEqual(MutasiInventoryDetail.objects.count(), 0)


class InventoryRecordModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_auto_inventory_number(self):
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        self.assertTrue(rec.inventory_number.startswith('RM-'))
        self.assertEqual(rec.total_value, 50000)

    def test_sequential_numbering(self):
        r1 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        r2 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=5, unit_price=6000,
        )
        # Both should have same prefix, sequential suffix
        prefix = r1.inventory_number.rsplit('-', 1)[0]
        self.assertEqual(r2.inventory_number, f'{prefix}-002')

    def test_str(self):
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )
        self.assertEqual(str(rec), rec.inventory_number)


class InventoryViewTests(TestCase):
    def setUp(self):
        from apps.accounts.models import Role
        role = Role.objects.create(kode='admin', nama='Admin')
        self.user = User.objects.create_user(email='test@test.com', password='pass', role=role)
        self.client = Client()
        self.client.login(email='test@test.com', password='pass')

        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.record = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, unit_price=5000,
        )

    def test_list_view(self):
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.record.inventory_number)

    def test_detail_view(self):
        resp = self.client.get(reverse('inventory:detail', args=[self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.record.inventory_number)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('inventory:list'))
        self.assertEqual(resp.status_code, 302)


class ReverseInflowMovementsTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_reverse_inflow_deletes_unconsumed_layer(self):
        from apps.inventory.ledger import record_inflow, reverse_inflow_movements
        from apps.inventory.models import StockMovement
        mv = record_inflow(self.item, self.eb, None, None, Decimal('10'),
                           Decimal('5'), '2026-01-01', 'purchase_in', source=self.item)
        reverse_inflow_movements(self.item)
        self.assertFalse(StockMovement.objects.filter(pk=mv.pk).exists())

    def test_reverse_inflow_raises_if_already_consumed(self):
        from django.db.models import ProtectedError
        from apps.inventory.ledger import record_inflow, consume_stock, reverse_inflow_movements
        record_inflow(self.item, self.eb, None, None, Decimal('10'),
                      Decimal('5'), '2026-01-01', 'purchase_in', source=self.item)
        consume_stock(self.item, self.eb, None, None, Decimal('3'),
                      '2026-01-02', 'sale_out')
        with self.assertRaises(ProtectedError):
            reverse_inflow_movements(self.item)


class BackfillStockMovementsTests(DjangoTestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_backfill_creates_layers_with_eb_and_links(self):
        from apps.purchase.models import FIFOBatch, PurchaseItem
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.inventory.backfill import backfill_stock_movements
        batch = FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01', quantity_in=Decimal('10'),
            unit_price=Decimal('5'), remaining_qty=Decimal('6'))
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('6'),
            unit_price=Decimal('5'), tanggal='2026-01-01')
        n = backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)
        self.assertEqual(n, 1)
        mv = StockMovement.objects.get()
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertEqual(mv.remaining_qty, Decimal('6'))
        self.assertEqual(mv.entitas_bisnis, self.eb)
        self.assertEqual(mv.legacy_fifo_batch_id, batch.id)
        self.assertEqual(mv.legacy_inventory_record_id, rec.id)

    def test_backwards_scoped_to_backfilled_rows_only(self):
        """Migration 0007's backwards() must not delete StockMovement rows created
        by normal dual-write (Task 7/8/9), even though those rows also carry
        legacy_fifo_batch. Only rows backfill_stock_movements itself created
        (no source object) should be removed.
        """
        from apps.purchase.models import FIFOBatch, PurchaseItem
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.inventory.backfill import backfill_stock_movements, backfilled_movements_queryset
        from apps.inventory.ledger import record_inflow

        # A historical batch that gets backfilled (simulates the migration's forwards()).
        batch = FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01', quantity_in=Decimal('10'),
            unit_price=Decimal('5'), remaining_qty=Decimal('6'))
        rec = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('6'),
            unit_price=Decimal('5'), tanggal='2026-01-01')
        backfill_stock_movements(FIFOBatch, InventoryRecord, StockMovement, PurchaseItem)
        backfilled_mv = StockMovement.objects.get()
        self.assertIsNone(backfilled_mv.source_content_type_id)

        # A real, post-backfill purchase going through the normal dual-write path
        # (apps.purchase.services.create_stock_movements calls record_inflow with
        # both legacy_fifo_batch AND source set).
        batch2 = FIFOBatch.objects.create(
            item=self.item, tanggal='2026-02-01', quantity_in=Decimal('4'),
            unit_price=Decimal('7'), remaining_qty=Decimal('4'))
        real_mv = record_inflow(
            self.item, self.eb, None, None, Decimal('4'), Decimal('7'), '2026-02-01',
            'purchase_in', source=batch2, legacy_fifo_batch=batch2, legacy_inventory_record=None,
        )
        self.assertIsNotNone(real_mv.source_content_type_id)

        # Sanity: the naive filter this migration used to use would wrongly catch both.
        self.assertEqual(
            StockMovement.objects.filter(legacy_fifo_batch__isnull=False).count(), 2)

        backfilled_movements_queryset(StockMovement).delete()

        remaining = list(StockMovement.objects.all())
        self.assertEqual(remaining, [real_mv])


class ReconcileCommandTests(DjangoTestCase):
    def test_reconcile_runs_clean(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('reconcile_stock_ledger', stdout=out)
        self.assertIn('Rekonsiliasi cocok', out.getvalue())
