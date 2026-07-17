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
