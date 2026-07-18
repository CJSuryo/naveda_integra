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
        for name in ('tanggal', 'eb_hierarki', 'warehouse', 'akun_selisih', 'keterangan'):
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
            'tanggal': '2026-03-01', 'eb_hierarki': f'lv1:{self.eb.pk}', 'warehouse': wh.pk,
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
            'tanggal': '2026-03-01', 'eb_hierarki': f'lv1:{self.eb.pk}', 'warehouse': wh.pk,
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


class TransferViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u3@example.com', password='p', name='U3')
        self.client.force_login(self.user)

    def test_list_and_create_render(self):
        self.assertEqual(self.client.get(reverse('inventory:transfer_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:transfer_create')).status_code, 200)

    def test_create_post_intra_entity_success(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import Warehouse, StockTransfer
        from apps.purchase.models import ItemMasterPurchase
        wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='TG1')
        wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='TG2')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        item.coa_account = Akun.objects.create(kode_akun='1.1.9', nama='Persediaan Transfer')
        item.save()
        record_inflow(item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=wh1)
        data = {
            'tanggal': '2026-04-01', 'eb_asal': self.eb.pk, 'warehouse_asal': wh1.pk,
            'eb_tujuan': self.eb.pk, 'warehouse_tujuan': wh2.pk, 'akun_perantara': '',
            'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': item.pk, 'items-0-qty': '4',
        }
        resp = self.client.post(reverse('inventory:transfer_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(StockTransfer.objects.filter(status='posted').count(), 1)

    def test_create_post_invalid_rerenders_with_errors(self):
        data = {
            'tanggal': '', 'eb_asal': '', 'warehouse_asal': '',
            'eb_tujuan': '', 'warehouse_tujuan': '', 'akun_perantara': '', 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': '', 'items-0-qty': '',
        }
        resp = self.client.post(reverse('inventory:transfer_create'), data)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['form'].is_valid())

    def test_delete_draft_just_deletes(self):
        from apps.inventory.models import Warehouse, StockTransfer
        wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='TG3')
        wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, nama='TG4')
        trf = StockTransfer.objects.create(tanggal='2026-04-02', eb_asal=self.eb,
                                           warehouse_asal=wh1, eb_tujuan=self.eb,
                                           warehouse_tujuan=wh2)
        resp = self.client.post(reverse('inventory:transfer_delete', args=[trf.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(StockTransfer.objects.filter(pk=trf.pk).exists())


class ReturCustomerModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_header(self):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturCustomerItem.objects.create(retur=h, item=self.item, qty=Decimal('2'),
                                         unit_cost=Decimal('5'), harga_jual=Decimal('9'))
        self.assertTrue(h.nomor.startswith('TRX-RTC-'))


class ReturSupplierModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_create_header(self):
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        self.assertTrue(h.nomor.startswith('TRX-RTS-'))


class ProcessReturCustomerTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        self.pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        self.piutang = Akun.objects.create(kode_akun='1.1.2', nama='Piutang')

    def test_standalone_return_restores_stock_and_balances(self):
        from apps.inventory.ledger import get_available_stock
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturCustomerItem.objects.create(
            retur=h, item=self.item, qty=Decimal('2'), unit_cost=Decimal('5'),
            harga_jual=Decimal('9'))
        header = process_retur_customer(h, akun_pendapatan=self.pendapatan,
                                        akun_piutang=self.piutang, akun_hpp=self.hpp)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('2'))
        deb = sum(x.debit for x in header.details.all())
        kre = sum(x.kredit for x in header.details.all())
        self.assertEqual(deb, kre)
        self.assertEqual(deb, Decimal('28'))  # pendapatan 2*9=18 + HPP-balik 2*5=10

    def test_missing_accounts_without_sales_item_rejected(self):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturCustomerItem.objects.create(
            retur=h, item=self.item, qty=Decimal('2'), unit_cost=Decimal('5'),
            harga_jual=Decimal('9'))
        with self.assertRaises(ValueError):
            process_retur_customer(h)  # tanpa sales_item & tanpa akun eksplisit

    def test_reverse_restores_consumed_stock_and_removes_journal(self):
        from apps.inventory.ledger import get_available_stock
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer, reverse_retur_customer
        from apps.jurnal.models import JurnalHeader
        h = ReturCustomer.objects.create(tanggal='2026-05-03', entitas_bisnis=self.eb,
                                         warehouse=self.wh)
        ReturCustomerItem.objects.create(
            retur=h, item=self.item, qty=Decimal('2'), unit_cost=Decimal('5'),
            harga_jual=Decimal('9'))
        header = process_retur_customer(h, akun_pendapatan=self.pendapatan,
                                        akun_piutang=self.piutang, akun_hpp=self.hpp)
        reverse_retur_customer(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('0'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header.pk).exists())


class ProcessReturSupplierTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.hutang = Akun.objects.create(kode_akun='2.1.1', nama='Hutang Usaha')

    def test_supplier_return_consumes_and_balances(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        from apps.inventory.services import process_retur_supplier
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_lawan=self.hutang)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        header = process_retur_supplier(h)
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('7'))
        self.assertEqual(sum(x.debit for x in header.details.all()),
                         sum(x.kredit for x in header.details.all()))
        self.assertEqual(sum(x.debit for x in header.details.all()), Decimal('15'))

    def test_missing_akun_lawan_rejected(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        from apps.inventory.services import process_retur_supplier
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh)  # akun_lawan kosong
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        with self.assertRaises(ValueError):
            process_retur_supplier(h)

    def test_reverse_restores_consumed_stock_and_removes_journal(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        from apps.inventory.services import process_retur_supplier, reverse_retur_supplier
        from apps.jurnal.models import JurnalHeader
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-03', 'purchase_in', warehouse=self.wh)
        h = ReturSupplier.objects.create(tanggal='2026-05-03', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_lawan=self.hutang)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        header = process_retur_supplier(h)
        reverse_retur_supplier(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')
        self.assertEqual(get_available_stock(self.item, self.eb, warehouse=self.wh), Decimal('10'))
        self.assertFalse(JurnalHeader.objects.filter(pk=header.pk).exists())


class ReturViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u4@example.com', password='p', name='U4')
        self.client.force_login(self.user)

    def test_list_and_create_render(self):
        self.assertEqual(self.client.get(reverse('inventory:retur_customer_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:retur_customer_create')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:retur_supplier_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:retur_supplier_create')).status_code, 200)

    def test_create_post_retur_customer_success_with_override_akun(self):
        from apps.inventory.models import Warehouse, ReturCustomer
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RC1')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        item.coa_account = Akun.objects.create(kode_akun='1.1.10', nama='Persediaan RC')
        item.save()
        akun_pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        akun_piutang = Akun.objects.create(kode_akun='1.1.3', nama='Piutang')
        akun_hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        data = {
            'tanggal': '2026-05-05', 'sales_header': '', 'entitas_bisnis': self.eb.pk,
            'entitas_bisnis_lv2': '', 'entitas_bisnis_lv3': '', 'warehouse': wh.pk,
            'keterangan': '', 'akun_pendapatan': akun_pendapatan.pk,
            'akun_piutang': akun_piutang.pk, 'akun_hpp': akun_hpp.pk,
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': item.pk, 'items-0-qty': '2',
            'items-0-unit_cost': '5', 'items-0-harga_jual': '9',
        }
        resp = self.client.post(reverse('inventory:retur_customer_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ReturCustomer.objects.filter(status='posted').count(), 1)

    def test_create_post_retur_supplier_success(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import Warehouse, ReturSupplier
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RS1')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        item.coa_account = Akun.objects.create(kode_akun='1.1.11', nama='Persediaan RS')
        item.save()
        record_inflow(item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=wh)
        akun_lawan = Akun.objects.create(kode_akun='2.1.2', nama='Hutang RS')
        data = {
            'tanggal': '2026-05-06', 'purchase_header': '', 'entitas_bisnis': self.eb.pk,
            'entitas_bisnis_lv2': '', 'entitas_bisnis_lv3': '', 'warehouse': wh.pk,
            'akun_lawan': akun_lawan.pk, 'keterangan': '',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-item': item.pk, 'items-0-qty': '3',
        }
        resp = self.client.post(reverse('inventory:retur_supplier_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ReturSupplier.objects.filter(status='posted').count(), 1)

    def test_delete_draft_retur_customer_just_deletes(self):
        from apps.inventory.models import Warehouse, ReturCustomer
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RC2')
        h = ReturCustomer.objects.create(tanggal='2026-05-07', entitas_bisnis=self.eb, warehouse=wh)
        resp = self.client.post(reverse('inventory:retur_customer_delete', args=[h.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ReturCustomer.objects.filter(pk=h.pk).exists())

    def test_delete_draft_retur_supplier_just_deletes(self):
        from apps.inventory.models import Warehouse, ReturSupplier
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RS2')
        h = ReturSupplier.objects.create(tanggal='2026-05-07', entitas_bisnis=self.eb, warehouse=wh)
        resp = self.client.post(reverse('inventory:retur_supplier_delete', args=[h.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ReturSupplier.objects.filter(pk=h.pk).exists())


class ReorderSettingTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_unique_item_warehouse(self):
        from django.db import IntegrityError
        from apps.inventory.models import ItemReorderSetting
        ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                          minimum_stock=Decimal('5'), reorder_point=Decimal('10'))
        with self.assertRaises(IntegrityError):
            ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                              minimum_stock=Decimal('3'), reorder_point=Decimal('8'))


class ReorderIndicatorTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')

    def test_status_levels(self):
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import ItemReorderSetting
        from apps.inventory.services import reorder_status
        ItemReorderSetting.objects.create(item=self.item, warehouse=self.wh,
                                          minimum_stock=Decimal('5'), reorder_point=Decimal('10'))
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('1'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'critical')  # <=5
        record_inflow(self.item, self.eb, None, None, Decimal('4'), Decimal('1'),
                      '2026-01-02', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'warning')   # 8, <=10
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('1'),
                      '2026-01-03', 'purchase_in', warehouse=self.wh)
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'ok')        # 18

    def test_no_setting_returns_none(self):
        from apps.inventory.services import reorder_status
        self.assertEqual(reorder_status(self.item, self.eb, self.wh), 'none')


class ReorderViewTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.user = User.objects.create_user(email='u5@example.com', password='p', name='U5')
        self.client.force_login(self.user)

    def test_list_and_create_render(self):
        self.assertEqual(self.client.get(reverse('inventory:reorder_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('inventory:reorder_create')).status_code, 200)

    def test_create_post_success(self):
        from apps.inventory.models import Warehouse, ItemReorderSetting
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RO1')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        data = {'item': item.pk, 'warehouse': wh.pk, 'minimum_stock': '5',
                'reorder_point': '10', 'reorder_qty': '20'}
        resp = self.client.post(reverse('inventory:reorder_create'), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ItemReorderSetting.objects.count(), 1)

    def test_delete(self):
        from apps.inventory.models import Warehouse, ItemReorderSetting
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='RO2')
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        s = ItemReorderSetting.objects.create(item=item, warehouse=wh,
                                              minimum_stock=Decimal('5'), reorder_point=Decimal('10'))
        resp = self.client.post(reverse('inventory:reorder_delete', args=[s.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ItemReorderSetting.objects.filter(pk=s.pk).exists())


class MixedInventoryAccountGuardTests(TestCase):
    """Dokumen dengan item ber-coa_account persediaan berbeda harus ditolak."""

    def setUp(self):
        from apps.master_data.models import Akun
        from apps.inventory.models import Warehouse
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan_a = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan A')
        self.persediaan_b = Akun.objects.create(kode_akun='1.1.5', nama='Persediaan B')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item_a = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.item_a.coa_account = self.persediaan_a
        self.item_a.save()
        self.item_b = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')
        self.item_b.coa_account = self.persediaan_b
        self.item_b.save()

    def test_adjustment_mixed_accounts_rejected(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment
        h = StockAdjustment.objects.create(tanggal='2026-02-01', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item_a,
                                           qty=Decimal('5'), unit_cost=Decimal('2'))
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item_b,
                                           qty=Decimal('5'), unit_cost=Decimal('2'))
        with self.assertRaises(ValueError):
            process_adjustment(h)
        # tidak ada movement/stok yang tercipta (rollback via atomic pemanggil / raise dini)
        h.refresh_from_db()
        self.assertEqual(h.status, 'draft')

    def test_adjustment_single_account_ok(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment
        h = StockAdjustment.objects.create(tanggal='2026-02-01', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item_a,
                                           qty=Decimal('5'), unit_cost=Decimal('2'))
        header = process_adjustment(h)
        h.refresh_from_db()
        self.assertEqual(h.status, 'posted')
        self.assertEqual(sum(d.debit for d in header.details.all()),
                         sum(d.kredit for d in header.details.all()))


class StockAvailableEndpointTests(TestCase):
    """Endpoint AJAX prefill Qty Sistem opname."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.inventory.models import Warehouse
        User = get_user_model()
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.user = User.objects.create_user(email='sa@example.com', password='p', name='SA')
        self.client.force_login(self.user)

    def test_returns_available_stock(self):
        from django.urls import reverse
        from apps.inventory.ledger import record_inflow
        record_inflow(self.item, self.eb, None, None, Decimal('7'), Decimal('3'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        resp = self.client.get(reverse('inventory:stock_available'),
                               {'item': self.item.pk, 'warehouse': self.wh.pk, 'eb': self.eb.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.json()['available']), Decimal('7'))

    def test_missing_params_returns_null(self):
        from django.urls import reverse
        resp = self.client.get(reverse('inventory:stock_available'), {'item': self.item.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['available'])


class ReturCustomerGroupedJournalTests(TestCase):
    """Opsi A: jurnal retur pelanggan dipecah per kombinasi akun pendapatan/piutang/HPP."""

    def setUp(self):
        from apps.master_data.models import Akun
        from apps.inventory.models import Warehouse
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        # Divisi Retail
        self.pend_retail = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan Retail')
        self.piutang_retail = Akun.objects.create(kode_akun='1.1.2', nama='Piutang Retail')
        # Divisi Sparepart
        self.pend_spare = Akun.objects.create(kode_akun='4.1.2', nama='Pendapatan Sparepart')
        self.piutang_spare = Akun.objects.create(kode_akun='1.1.3', nama='Piutang Sparepart')
        self.item_a = ItemMasterPurchase.objects.create(nama='Ban', tipe_item='RM')
        self.item_a.coa_account = self.persediaan
        self.item_a.save()
        self.item_b = ItemMasterPurchase.objects.create(nama='Busi', tipe_item='RM')
        self.item_b.coa_account = self.persediaan
        self.item_b.save()

    def _sales_item(self, item, revenue, piutang):
        from django.utils import timezone
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        from apps.purchase.models import SubTransactionType
        sh = SalesHeader.objects.create(transaction_id=f'SO-{revenue.kode_akun}-{item.pk}',
                                        tanggal=timezone.now().date())
        seb = SalesEntitasBisnis.objects.create(sales_header=sh, entitas_bisnis=self.eb)
        stt, _ = SubTransactionType.objects.get_or_create(
            nama='Penjualan',
            defaults={'module': 'sales', 'direction': 'out',
                      'default_offset_account': self.hpp})
        return SalesItem.objects.create(
            sales_eb=seb, item=item, sub_transaction_type=stt,
            quantity=Decimal('1'), selling_price=Decimal('10'),
            offset_coa_account=self.hpp, revenue_account=revenue, payment_account=piutang)

    def test_two_divisions_produce_separate_revenue_lines(self):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer
        si_a = self._sales_item(self.item_a, self.pend_retail, self.piutang_retail)
        si_b = self._sales_item(self.item_b, self.pend_spare, self.piutang_spare)
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb, warehouse=self.wh)
        ReturCustomerItem.objects.create(retur=h, item=self.item_a, sales_item=si_a,
                                         qty=Decimal('2'), unit_cost=Decimal('5'), harga_jual=Decimal('50'))
        ReturCustomerItem.objects.create(retur=h, item=self.item_b, sales_item=si_b,
                                         qty=Decimal('1'), unit_cost=Decimal('4'), harga_jual=Decimal('30'))
        header = process_retur_customer(h)
        details = list(header.details.all())
        # jurnal balance
        self.assertEqual(sum(x.debit for x in details), sum(x.kredit for x in details))
        # dua akun pendapatan berbeda muncul terpisah, dengan nilai masing-masing
        pend_retail_lines = [x for x in details if x.akun_id == self.pend_retail.pk]
        pend_spare_lines = [x for x in details if x.akun_id == self.pend_spare.pk]
        self.assertEqual(len(pend_retail_lines), 1)
        self.assertEqual(len(pend_spare_lines), 1)
        self.assertEqual(pend_retail_lines[0].debit, Decimal('100'))  # 2*50
        self.assertEqual(pend_spare_lines[0].debit, Decimal('30'))    # 1*30
        # piutang per divisi
        self.assertEqual(sum(x.kredit for x in details if x.akun_id == self.piutang_retail.pk), Decimal('100'))
        self.assertEqual(sum(x.kredit for x in details if x.akun_id == self.piutang_spare.pk), Decimal('30'))
        # HPP tergabung (akun persediaan & HPP sama) = 2*5 + 1*4 = 14
        self.assertEqual(sum(x.debit for x in details if x.akun_id == self.persediaan.pk), Decimal('14'))


class JournalPenyesuaianFlagTests(TestCase):
    """adjustment/opname = is_penyesuaian True; transfer/retur = False."""

    def setUp(self):
        from apps.master_data.models import Akun
        from apps.inventory.models import Warehouse
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.item.coa_account = self.persediaan
        self.item.save()
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')

    def test_adjustment_flagged_penyesuaian(self):
        from apps.inventory.models import StockAdjustment, StockAdjustmentItem
        from apps.inventory.services import process_adjustment
        h = StockAdjustment.objects.create(tanggal='2026-02-01', entitas_bisnis=self.eb,
                                           warehouse=self.wh, akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(adjustment=h, item=self.item,
                                           qty=Decimal('5'), unit_cost=Decimal('2'))
        header = process_adjustment(h)
        self.assertTrue(header.is_penyesuaian)

    def test_retur_supplier_not_penyesuaian(self):
        from apps.master_data.models import Akun
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import ReturSupplier, ReturSupplierItem
        from apps.inventory.services import process_retur_supplier
        record_inflow(self.item, self.eb, None, None, Decimal('10'), Decimal('5'),
                      '2026-01-01', 'purchase_in', warehouse=self.wh)
        hutang = Akun.objects.create(kode_akun='2.1.1', nama='Hutang')
        h = ReturSupplier.objects.create(tanggal='2026-05-02', entitas_bisnis=self.eb,
                                         warehouse=self.wh, akun_lawan=hutang)
        ReturSupplierItem.objects.create(retur=h, item=self.item, qty=Decimal('3'))
        header = process_retur_supplier(h)
        self.assertFalse(header.is_penyesuaian)


class WarehouseScopeValidationTests(TestCase):
    """Gudang yang dipilih harus milik entitas bisnis yang dipilih."""

    def setUp(self):
        from apps.inventory.models import Warehouse
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb_a = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.eb_b = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        self.wh_b = Warehouse.objects.create(entitas_bisnis=self.eb_b, nama='Gudang B')
        self.akun = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')

    def test_adjustment_rejects_warehouse_of_other_entity(self):
        from apps.inventory.forms import StockAdjustmentForm
        form = StockAdjustmentForm(data={
            'tanggal': '2026-02-01', 'eb_hierarki': f'lv1:{self.eb_a.pk}',
            'warehouse': self.wh_b.pk, 'akun_selisih': self.akun.pk, 'keterangan': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('warehouse', form.errors)

    def test_adjustment_accepts_matching_warehouse(self):
        from apps.inventory.models import Warehouse
        from apps.inventory.forms import StockAdjustmentForm
        wh_a = Warehouse.objects.create(entitas_bisnis=self.eb_a, nama='Gudang A')
        form = StockAdjustmentForm(data={
            'tanggal': '2026-02-01', 'eb_hierarki': f'lv1:{self.eb_a.pk}',
            'warehouse': wh_a.pk, 'akun_selisih': self.akun.pk, 'keterangan': '',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_widget_marks_options_with_data_eb(self):
        from apps.inventory.forms import StockAdjustmentForm
        html = str(StockAdjustmentForm()['warehouse'])
        self.assertIn('data-eb="%d"' % self.eb_b.pk, html)
        self.assertIn('data-eb-filter="id_eb_hierarki"', html)


class ReturCustomerPPNTests(TestCase):
    """Cara benar: PPN Keluaran diretur proporsional lewat modul pajak (SPT konsisten)."""

    def setUp(self):
        from apps.inventory.models import Warehouse
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        self.pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        self.piutang = Akun.objects.create(kode_akun='1.1.2', nama='Piutang')
        self.ppn_keluaran = Akun.objects.create(kode_akun='2.1.4', nama='PPN Keluaran')
        self.utang_ppn = Akun.objects.create(kode_akun='2.1.5', nama='Utang PPN')
        self.item = ItemMasterPurchase.objects.create(nama='Ban', tipe_item='RM')
        self.item.coa_account = self.persediaan
        self.item.save()

    def _sold_item_with_ppn(self, qty_sold, dpp, ppn):
        from datetime import date
        from django.utils import timezone
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        from apps.purchase.models import SubTransactionType
        from apps.pajak.models import PajakTransaksi
        sh = SalesHeader.objects.create(transaction_id='SO-PPN-1', tanggal=timezone.now().date())
        seb = SalesEntitasBisnis.objects.create(sales_header=sh, entitas_bisnis=self.eb)
        stt, _ = SubTransactionType.objects.get_or_create(
            nama='Penjualan',
            defaults={'module': 'sales', 'direction': 'out', 'default_offset_account': self.hpp})
        si = SalesItem.objects.create(
            sales_eb=seb, item=self.item, sub_transaction_type=stt,
            quantity=qty_sold, selling_price=dpp / qty_sold, total_sales=dpp,
            offset_coa_account=self.hpp, revenue_account=self.pendapatan,
            payment_account=self.piutang)
        PajakTransaksi.objects.create(
            source_type='sales_item', source_id=si.pk, masa_pajak=date(2026, 4, 1),
            jenis_pajak='ppn_umum', dpp=dpp, tarif_persen=Decimal('11'),
            jumlah_pajak=ppn, sifat_pajak='potong_pungut', status='final',
            akun_pajak=self.ppn_keluaran, akun_lawan=self.utang_ppn, entitas_bisnis=self.eb)
        return si

    def _retur(self, si, qty):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb, warehouse=self.wh)
        d = ReturCustomerItem.objects.create(retur=h, item=self.item, sales_item=si,
                                             qty=qty, unit_cost=Decimal('5'), harga_jual=Decimal('100000'))
        return h, d

    def test_partial_return_reverses_proportional_ppn(self):
        from apps.inventory.services import process_retur_customer
        from apps.pajak.models import PajakTransaksi
        si = self._sold_item_with_ppn(Decimal('10'), Decimal('1000000'), Decimal('110000'))
        h, d = self._retur(si, Decimal('4'))  # 4 dari 10 → 40%
        process_retur_customer(h)
        pt = PajakTransaksi.objects.get(source_type='retur_customer_item', source_id=d.pk)
        self.assertEqual(pt.status, 'final')
        self.assertEqual(pt.jumlah_pajak, Decimal('44000'))  # 110000 × 4/10
        details = list(pt.jurnal_header.details.all())
        debited = next(x for x in details if x.debit > 0)
        self.assertEqual(debited.akun_id, self.ppn_keluaran.pk)  # PPN Keluaran didebit → berkurang
        self.assertEqual(debited.debit, Decimal('44000.00'))

    def test_reverse_cancels_retur_ppn(self):
        from apps.inventory.services import process_retur_customer, reverse_retur_customer
        from apps.pajak.models import PajakTransaksi
        si = self._sold_item_with_ppn(Decimal('10'), Decimal('1000000'), Decimal('110000'))
        h, d = self._retur(si, Decimal('4'))
        process_retur_customer(h)
        reverse_retur_customer(h)
        pt = PajakTransaksi.objects.get(source_type='retur_customer_item', source_id=d.pk)
        self.assertEqual(pt.status, 'dibatalkan')

    def test_item_without_sales_item_no_ppn(self):
        from apps.inventory.models import ReturCustomer, ReturCustomerItem
        from apps.inventory.services import process_retur_customer
        from apps.pajak.models import PajakTransaksi
        h = ReturCustomer.objects.create(tanggal='2026-05-01', entitas_bisnis=self.eb, warehouse=self.wh)
        ReturCustomerItem.objects.create(retur=h, item=self.item, qty=Decimal('2'),
                                         unit_cost=Decimal('5'), harga_jual=Decimal('100000'))
        process_retur_customer(h, akun_pendapatan=self.pendapatan,
                               akun_piutang=self.piutang, akun_hpp=self.hpp)
        self.assertFalse(PajakTransaksi.objects.filter(source_type='retur_customer_item').exists())


class ReturPpnPreviewUITests(TestCase):
    """Endpoint preview PPN retur + field sales_item pada form."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.inventory.models import Warehouse
        User = get_user_model()
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        self.pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        self.piutang = Akun.objects.create(kode_akun='1.1.2', nama='Piutang')
        self.ppn_keluaran = Akun.objects.create(kode_akun='2.1.4', nama='PPN Keluaran')
        self.utang_ppn = Akun.objects.create(kode_akun='2.1.5', nama='Utang PPN')
        self.item = ItemMasterPurchase.objects.create(nama='Ban', tipe_item='RM')
        self.user = User.objects.create_user(email='ppn@example.com', password='p', name='P')
        self.client.force_login(self.user)

    def _sold_item(self, qty_sold, dpp, ppn, cogs):
        from datetime import date
        from django.utils import timezone
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        from apps.purchase.models import SubTransactionType
        from apps.pajak.models import PajakTransaksi
        sh = SalesHeader.objects.create(transaction_id='SO-UI-1', tanggal=timezone.now().date())
        seb = SalesEntitasBisnis.objects.create(sales_header=sh, entitas_bisnis=self.eb)
        stt, _ = SubTransactionType.objects.get_or_create(
            nama='Penjualan',
            defaults={'module': 'sales', 'direction': 'out', 'default_offset_account': self.hpp})
        si = SalesItem.objects.create(
            sales_eb=seb, item=self.item, sub_transaction_type=stt,
            quantity=qty_sold, selling_price=dpp / qty_sold, total_sales=dpp,
            cogs_amount=cogs, offset_coa_account=self.hpp,
            revenue_account=self.pendapatan, payment_account=self.piutang)
        PajakTransaksi.objects.create(
            source_type='sales_item', source_id=si.pk, masa_pajak=date(2026, 4, 1),
            jenis_pajak='ppn_umum', dpp=dpp, tarif_persen=Decimal('11'),
            jumlah_pajak=ppn, sifat_pajak='potong_pungut', status='final',
            akun_pajak=self.ppn_keluaran, akun_lawan=self.utang_ppn, entitas_bisnis=self.eb)
        return si

    def test_preview_returns_proportional_ppn_and_prefill(self):
        from django.urls import reverse
        si = self._sold_item(Decimal('10'), Decimal('1000000'), Decimal('110000'), Decimal('500000'))
        resp = self.client.get(reverse('inventory:retur_ppn_preview'),
                               {'sales_item': si.pk, 'qty': '4'})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(Decimal(data['ppn']), Decimal('44000.00'))     # 110000 × 4/10
        self.assertEqual(data['item'], self.item.pk)
        self.assertEqual(Decimal(data['unit_cost']), Decimal('50000'))  # cogs 500000 / 10
        self.assertEqual(Decimal(data['harga_jual']), Decimal('100000'))

    def test_form_has_sales_item_with_scope_attr(self):
        from apps.inventory.forms import ReturCustomerItemForm
        si = self._sold_item(Decimal('10'), Decimal('1000000'), Decimal('110000'), Decimal('0'))
        f = ReturCustomerItemForm()
        self.assertIn('sales_item', f.fields)
        html = str(f['sales_item'])
        self.assertIn('data-parent-filter="id_sales_header"', html)
        self.assertIn('data-sales-header="%d"' % si.sales_eb.sales_header_id, html)
