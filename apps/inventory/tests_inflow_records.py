"""Tests: inflow transaksi (adjustment/opname/transfer/retur pelanggan) membuat
InventoryRecord sendiri agar muncul di daftar & detail persediaan, ter-decrement
saat dikonsumsi, dan terhapus saat pembatalan."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import (
    Warehouse, InventoryRecord, StockAdjustment, StockAdjustmentItem,
    StockOpname, StockOpnameItem, StockTransfer, StockTransferItem,
    ReturCustomer, ReturCustomerItem,
)
from apps.inventory import ledger
from apps.inventory.services import (
    process_adjustment, process_opname, process_transfer,
    process_retur_customer, reverse_adjustment,
)


class _Base(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.selisih = Akun.objects.create(kode_akun='5.9.1', nama='Selisih')
        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi', tipe_item='RM', metode_biaya_persediaan='fifo')
        self.item.coa_account = self.persediaan
        self.item.save()


class AdjustmentInflowRecordTests(_Base):
    def _adj_in(self, qty):
        adj = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(
            adjustment=adj, item=self.item, qty=Decimal(qty), unit_cost=Decimal('100'))
        process_adjustment(adj)
        return adj

    def test_adjustment_in_creates_inventory_record(self):
        before = InventoryRecord.objects.count()
        self._adj_in('7')
        self.assertEqual(InventoryRecord.objects.count(), before + 1)
        rec = InventoryRecord.objects.latest('id')
        self.assertEqual(rec.item, self.item)
        self.assertEqual(rec.entitas_bisnis, self.eb)
        self.assertEqual(rec.quantity, Decimal('7'))
        self.assertEqual(rec.unit_price, Decimal('100'))

    def test_record_linked_to_inflow_movement(self):
        self._adj_in('7')
        rec = InventoryRecord.objects.latest('id')
        mv = rec.stock_movements.get(movement_type='adjustment_in')
        self.assertEqual(mv.qty, Decimal('7'))
        self.assertEqual(mv.legacy_inventory_record_id, rec.pk)

    def test_record_decrements_when_consumed(self):
        self._adj_in('10')
        rec = InventoryRecord.objects.latest('id')
        # konsumsi 4 via adjustment_out
        adj = StockAdjustment.objects.create(
            tanggal='2026-02-02', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(
            adjustment=adj, item=self.item, qty=Decimal('-4'), unit_cost=Decimal('100'))
        process_adjustment(adj)
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('6'))

    def test_reversal_deletes_created_record(self):
        adj = self._adj_in('7')
        rec_id = InventoryRecord.objects.latest('id').pk
        reverse_adjustment(adj)
        self.assertFalse(InventoryRecord.objects.filter(pk=rec_id).exists())

    def test_negative_adjustment_does_not_create_record(self):
        # seed stock, lalu adjustment_out saja — tidak boleh bikin record baru
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)
        before = InventoryRecord.objects.count()
        adj = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(
            adjustment=adj, item=self.item, qty=Decimal('-3'), unit_cost=Decimal('100'))
        process_adjustment(adj)
        self.assertEqual(InventoryRecord.objects.count(), before)


class OpnameInflowRecordTests(_Base):
    def test_opname_surplus_creates_record(self):
        opn = StockOpname.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih)
        StockOpnameItem.objects.create(
            opname=opn, item=self.item, qty_sistem=Decimal('0'),
            qty_fisik=Decimal('5'), unit_cost=Decimal('100'))
        before = InventoryRecord.objects.count()
        process_opname(opn)
        self.assertEqual(InventoryRecord.objects.count(), before + 1)
        rec = InventoryRecord.objects.latest('id')
        self.assertEqual(rec.quantity, Decimal('5'))


class TransferInflowRecordTests(_Base):
    def test_transfer_creates_record_at_destination(self):
        eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
        wh2 = Warehouse.objects.create(entitas_bisnis=eb2, nama='G2')
        perantara = Akun.objects.create(kode_akun='1.1.9', nama='Perantara')
        ledger.record_inflow(self.item, self.eb, None, None, Decimal('10'),
                             Decimal('100'), '2026-01-01', 'adjustment_in', warehouse=self.wh)
        trf = StockTransfer.objects.create(
            tanggal='2026-02-01', eb_asal=self.eb, warehouse_asal=self.wh,
            eb_tujuan=eb2, warehouse_tujuan=wh2, akun_perantara=perantara)
        StockTransferItem.objects.create(transfer=trf, item=self.item, qty=Decimal('4'))
        before = InventoryRecord.objects.count()
        process_transfer(trf)
        self.assertEqual(InventoryRecord.objects.count(), before + 1)
        rec = InventoryRecord.objects.latest('id')
        self.assertEqual(rec.entitas_bisnis, eb2)
        self.assertEqual(rec.quantity, Decimal('4'))


class ReturCustomerInflowRecordTests(_Base):
    def test_retur_customer_creates_record(self):
        pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        piutang = Akun.objects.create(kode_akun='1.1.3', nama='Piutang')
        hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')
        rtc = ReturCustomer.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh)
        ReturCustomerItem.objects.create(
            retur=rtc, item=self.item, qty=Decimal('3'),
            unit_cost=Decimal('100'), harga_jual=Decimal('150'))
        before = InventoryRecord.objects.count()
        process_retur_customer(rtc, akun_pendapatan=pendapatan,
                               akun_piutang=piutang, akun_hpp=hpp)
        self.assertEqual(InventoryRecord.objects.count(), before + 1)
        rec = InventoryRecord.objects.latest('id')
        self.assertEqual(rec.quantity, Decimal('3'))


class InflowRecordDetailLabelTests(_Base):
    def setUp(self):
        super().setUp()
        from apps.accounts.models import Role
        User = get_user_model()
        role = Role.objects.create(kode='admin', nama='Admin')
        self.user = User.objects.create_user(email='inflow@test.com', password='x', role=role)
        self.client = Client()
        self.client.force_login(self.user)

    def test_detail_labels_adjustment_not_saldo_awal(self):
        adj = StockAdjustment.objects.create(
            tanggal='2026-02-01', entitas_bisnis=self.eb, warehouse=self.wh,
            akun_selisih=self.selisih)
        StockAdjustmentItem.objects.create(
            adjustment=adj, item=self.item, qty=Decimal('7'), unit_cost=Decimal('100'))
        process_adjustment(adj)
        rec = InventoryRecord.objects.latest('id')
        resp = self.client.get(reverse('inventory:detail', args=[rec.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Penyesuaian Masuk')
        self.assertNotContains(resp, 'Masuk (Saldo Awal)')
        self.assertContains(resp, adj.nomor)
