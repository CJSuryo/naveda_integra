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


class ReverseAdjustmentTests(ProcessAdjustmentTests):
    def test_reverse_restores_stock_and_removes_journal(self):
        from apps.inventory.services import process_adjustment, reverse_adjustment
        from apps.inventory.ledger import get_available_stock
        from apps.jurnal.models import JurnalHeader
        h = self._header()  # +10
        header = process_adjustment(h)
        reverse_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('0'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header.pk).exists())

    def test_reverse_consume_adjustment_restores_consumed_layer(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment, reverse_adjustment
        record_inflow(self.item, self.eb, None, None, Decimal('20'), Decimal('4'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = StockAdjustment.objects.create(tanggal='2026-02-03', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item, qty=Decimal('-5'))
        process_adjustment(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('15'))
        reverse_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('20'))


class AdjustmentFormTests(TestCase):
    def test_form_fields(self):
        from apps.inventory.forms import StockAdjustmentForm
        f = StockAdjustmentForm()
        for name in ('tanggal', 'entitas_bisnis', 'warehouse', 'akun_selisih', 'keterangan'):
            self.assertIn(name, f.fields)

    def test_formset_requires_at_least_one_item(self):
        from apps.inventory.forms import StockAdjustmentItemFormSet
        data = {
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': '', 'items-0-qty': '', 'items-0-unit_cost': '',
        }
        fs = StockAdjustmentItemFormSet(data=data)
        self.assertFalse(fs.is_valid())


from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class AdjustmentViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u@example.com', password='p', name='U')
        self.client.force_login(self.user)

    def test_list_renders(self):
        resp = self.client.get(reverse('inventory:adjustment_list'))
        self.assertEqual(resp.status_code, 200)

    def test_create_get_renders(self):
        resp = self.client.get(reverse('inventory:adjustment_create'))
        self.assertEqual(resp.status_code, 200)

    def test_create_post_success_posts_adjustment(self):
        from apps.master_data.models import Akun
        from apps.purchase.models import ItemMasterPurchase
        from apps.inventory.models import Warehouse, StockAdjustment
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        item.coa_account = persediaan
        item.save()
        selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        data = {
            'tanggal': '2026-03-01', 'entitas_bisnis': self.eb.pk, 'warehouse': wh.pk,
            'akun_selisih': selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': item.pk, 'items-0-qty': '10', 'items-0-unit_cost': '5',
        }
        resp = self.client.post(reverse('inventory:adjustment_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockAdjustment.objects.filter(status='posted').count(), 1)

    def test_create_post_invalid_rerenders_with_errors(self):
        data = {
            'tanggal': '', 'entitas_bisnis': '', 'warehouse': '',
            'akun_selisih': '', 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': '', 'items-0-qty': '', 'items-0-unit_cost': '',
        }
        resp = self.client.post(reverse('inventory:adjustment_create'), data)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['form'].is_valid())

    def test_delete_draft_just_deletes(self):
        from apps.master_data.models import Akun
        from apps.inventory.models import Warehouse, StockAdjustment
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        selisih = Akun.objects.create(kode_akun='5.9.2', nama='Selisih2')
        adj = StockAdjustment.objects.create(tanggal='2026-03-02', entitas_bisnis=self.eb,
                                             warehouse=wh, akun_selisih=selisih)
        resp = self.client.post(reverse('inventory:adjustment_delete', args=[adj.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(StockAdjustment.objects.filter(pk=adj.pk).exists())


class StockOpnameModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.akun = Akun.objects.create(kode_akun='5.9.2', nama='Selisih Opname')

    def test_selisih_autocompute(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.akun)
        d = StockOpnameItem.objects.create(opname=h, item=self.item,
                                           qty_sistem=Decimal('10'), qty_fisik=Decimal('8'),
                                           unit_cost=Decimal('5'))
        self.assertEqual(d.selisih, Decimal('-2'))
        self.assertTrue(h.nomor.startswith('TRX-OPN-'))


class ProcessOpnameTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.selisih = Akun.objects.create(kode_akun='5.9.2', nama='Selisih Opname')

    def test_posting_minus_consumes_and_balances(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=h, item=self.item, qty_sistem=Decimal('10'),
                                       qty_fisik=Decimal('8'), unit_cost=Decimal('5'))
        header = process_opname(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('8'))
        self.assertEqual(sum(d.debit for d in header.details.all()),
                         sum(d.kredit for d in header.details.all()))

    def test_zero_selisih_no_movement(self):
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname
        h = StockOpname.objects.create(tanggal='2026-03-01', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=h, item=self.item, qty_sistem=Decimal('5'),
                                       qty_fisik=Decimal('5'), unit_cost=Decimal('5'))
        header = process_opname(h)
        self.assertIsNone(header)  # tidak ada selisih → tidak ada jurnal

    def test_reverse_restores_stock_and_removes_journal(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockOpname, StockOpnameItem
        from apps.inventory.services import process_opname, reverse_opname
        from apps.jurnal.models import JurnalHeader
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-02', 'purchase_in', warehouse=self.wh)
        h = StockOpname.objects.create(tanggal='2026-03-02', entitas_bisnis=self.eb,
                                       warehouse=self.wh, akun_selisih=self.selisih)
        StockOpnameItem.objects.create(opname=h, item=self.item, qty_sistem=Decimal('10'),
                                       qty_fisik=Decimal('8'), unit_cost=Decimal('5'))
        header = process_opname(h)
        reverse_opname(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('10'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header.pk).exists())


class OpnameViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u2@example.com', password='p', name='U2')
        self.client.force_login(self.user)

    def test_list_and_create_render(self):
        self.assertEqual(self.client.get(reverse('inventory:opname_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:opname_create')).status_code, 200)

    def test_create_post_success_posts_opname(self):
        from apps.master_data.models import Akun
        from apps.purchase.models import ItemMasterPurchase
        from apps.inventory.models import Warehouse, StockOpname
        from apps.inventory.ledger import record_inflow
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        item.coa_account = persediaan
        item.save()
        selisih = Akun.objects.create(kode_akun='5.9.2', nama='Selisih')
        # Seed existing stock so the opname's decrease (10 -> 8) can be consumed.
        record_inflow(item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=wh)
        data = {
            'tanggal': '2026-03-01', 'entitas_bisnis': self.eb.pk, 'warehouse': wh.pk,
            'akun_selisih': selisih.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': item.pk, 'items-0-qty_sistem': '10',
            'items-0-qty_fisik': '8', 'items-0-unit_cost': '5',
        }
        resp = self.client.post(reverse('inventory:opname_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockOpname.objects.filter(status='posted').count(), 1)

    def test_create_post_invalid_rerenders_with_errors(self):
        data = {
            'tanggal': '', 'entitas_bisnis': '', 'warehouse': '',
            'akun_selisih': '', 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': '', 'items-0-qty_sistem': '', 'items-0-qty_fisik': '',
            'items-0-unit_cost': '',
        }
        resp = self.client.post(reverse('inventory:opname_create'), data)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['form'].is_valid())

    def test_delete_draft_just_deletes(self):
        from apps.master_data.models import Akun
        from apps.inventory.models import Warehouse, StockOpname
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        selisih = Akun.objects.create(kode_akun='5.9.3', nama='Selisih2')
        opn = StockOpname.objects.create(tanggal='2026-03-02', entitas_bisnis=self.eb,
                                         warehouse=wh, akun_selisih=selisih)
        resp = self.client.post(reverse('inventory:opname_delete', args=[opn.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(StockOpname.objects.filter(pk=opn.pk).exists())


class StockTransferModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_transfer(self):
        from apps.inventory.models import StockTransfer, StockTransferItem
        h = StockTransfer.objects.create(
            tanggal='2026-04-01', eb_asal=self.eb, warehouse_asal=self.wh1,
            eb_tujuan=self.eb, warehouse_tujuan=self.wh2)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('5'))
        self.assertTrue(h.nomor.startswith('TRX-TRF-'))
        self.assertFalse(h.is_cross_entity)


class ProcessTransferTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G2')
        self.wh3 = Warehouse.objects.create(entitas_bisnis=self.eb2, nama='G3')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.perantara = Akun.objects.create(kode_akun='1.1.9', nama='Perantara Transfer')

    def test_intra_entity_moves_stock_no_journal(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-01', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb,
                                         warehouse_tujuan=self.wh2)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh1), Decimal('6'))
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh2), Decimal('4'))
        self.assertIsNone(h.jurnal_header_asal)

    def test_cross_entity_creates_two_balanced_journals(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-01', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb2,
                                         warehouse_tujuan=self.wh3, akun_perantara=self.perantara)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        h.refresh_from_db()
        self.assertEqual(get_available_stock(self.item, self.eb2, warehouse=self.wh3), Decimal('4'))
        for hdr in (h.jurnal_header_asal, h.jurnal_header_tujuan):
            self.assertIsNotNone(hdr)
            self.assertEqual(sum(d.debit for d in hdr.details.all()),
                             sum(d.kredit for d in hdr.details.all()))

    def test_self_transfer_same_entity_same_warehouse_rejected(self):
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        h = StockTransfer.objects.create(tanggal='2026-04-02', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb,
                                         warehouse_tujuan=self.wh1)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('1'))
        with self.assertRaises(ValueError):
            process_transfer(h)

    def test_cross_entity_without_akun_perantara_rejected(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-03', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb2,
                                         warehouse_tujuan=self.wh3)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        with self.assertRaises(ValueError):
            process_transfer(h)

    def test_reverse_cross_entity_restores_stock_and_removes_both_journals(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer, reverse_transfer
        from apps.jurnal.models import JurnalHeader
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-04', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-04', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb2,
                                         warehouse_tujuan=self.wh3, akun_perantara=self.perantara)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        h.refresh_from_db()
        header_asal_pk = h.jurnal_header_asal.pk
        header_tujuan_pk = h.jurnal_header_tujuan.pk
        reverse_transfer(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh1), Decimal('10'))
        self.assertEqual(get_available_stock(self.item, self.eb2, warehouse=self.wh3), Decimal('0'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header_asal_pk).exists())
        self.assertFalse(JurnalHeader.objects.filter(pk=header_tujuan_pk).exists())

    def test_reverse_intra_entity_restores_stock_no_journal_errors(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import StockTransfer, StockTransferItem
        from apps.inventory.services import process_transfer, reverse_transfer
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-05', 'purchase_in', warehouse=self.wh1)
        h = StockTransfer.objects.create(tanggal='2026-04-05', eb_asal=self.eb,
                                         warehouse_asal=self.wh1, eb_tujuan=self.eb,
                                         warehouse_tujuan=self.wh2)
        StockTransferItem.objects.create(transfer=h, item=self.item, qty=Decimal('4'))
        process_transfer(h)
        reverse_transfer(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh1), Decimal('10'))
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh2), Decimal('0'))
