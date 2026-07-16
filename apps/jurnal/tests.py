"""Unit tests for the jurnal app."""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
from apps.master_data.models import TipeTransaksi, Akun, AsetLv1, AsetLv2
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)

User = get_user_model()


def _create_user():
    return User.objects.create_user(email='jurnal@test.com', password='pass', name='Jurnal User')


class ItemModelTests(TestCase):
    def test_str(self):
        i = Item.objects.create(kode='A', nama='Persediaan')
        self.assertIn('A', str(i))

    def test_unique_kode(self):
        Item.objects.create(kode='A', nama='Persediaan')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Item.objects.create(kode='A', nama='Duplicate')


class TransactionPrefixModelTests(TestCase):
    def test_str(self):
        tp = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')
        self.assertIn('TRX-INV', str(tp))


class JurnalModelTests(TestCase):
    def setUp(self):
        self.tipe_eb = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe_eb)
        self.tipe = TipeTransaksi.objects.create(kode_transaksi='T01', nama='Pembelian')
        self.item = Item.objects.create(kode='A', nama='Persediaan')
        self.prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')
        self.akun = Akun.objects.create(kategori_id='aset', kategori_akun=1, nama='Test Akun')

    def test_jurnal_header_str(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            nomor_transaksi='TRX-INV-001',
            uraian_transaksi='Pembelian Barang',
            tipe_transaksi=self.tipe,
            item=self.item,
            transaction_prefix=self.prefix,
        )
        self.assertIn('2024-01-01', str(h))
        self.assertIn('TRX-INV-001', str(h))

    def test_jurnal_detail_str(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            nomor_transaksi='TRX-INV-002',
            uraian_transaksi='Pembelian Barang',
            tipe_transaksi=self.tipe,
            item=self.item,
        )
        d = JurnalDetail.objects.create(jurnal_header=h, akun=self.akun, debit=100000, kredit=0)
        self.assertIn(str(h.id), str(d))

    def test_jurnal_detail_defaults(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            nomor_transaksi='TRX-INV-003',
            uraian_transaksi='Test',
            tipe_transaksi=self.tipe,
            item=self.item,
        )
        d = JurnalDetail.objects.create(jurnal_header=h, akun=self.akun)
        self.assertEqual(d.debit, 0)
        self.assertEqual(d.kredit, 0)


class JurnalAutomasiModelTests(TestCase):
    def setUp(self):
        self.akun = Akun.objects.create(kategori_id='aset', kategori_akun=1, nama='Test')

    def test_automasi_str(self):
        a = JurnalAutomasi.objects.create(nama='Stok Awal Perlengkapan')
        self.assertIn('Stok Awal', str(a))

    def test_automasi_akun(self):
        a = JurnalAutomasi.objects.create(nama='Stok Awal')
        mapping = JurnalAutomasiAkun.objects.create(automasi=a, akun=self.akun)
        self.assertEqual(a.akun_mappings.count(), 1)
        self.assertIn('Stok Awal', str(mapping))


class AkunSignalTests(TestCase):
    """Test that saving Lv2 records auto-creates Akun rows."""

    def test_aset_lv2_creates_akun(self):
        lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=lv1)
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertEqual(akun.nama, 'Kas Kecil')

    def test_aset_lv2_delete_removes_akun(self):
        lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=lv1)
        lv2_pk = lv2.pk
        lv2.delete()
        self.assertFalse(Akun.objects.filter(kategori_id='aset', kategori_akun=lv2_pk).exists())

    def test_aset_lv2_update_syncs_akun(self):
        lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=lv1)
        lv2.nama = 'Kas Besar'
        lv2.save()
        akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)
        self.assertEqual(akun.nama, 'Kas Besar')


# ── View Tests ────────────────────────────────────────────────────────────────

class RekapJurnalViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.tipe = TipeTransaksi.objects.create(kode_transaksi='T01', nama='Pembelian')
        self.item = Item.objects.create(kode='A', nama='Persediaan')
        self.prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')
        self.header = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            nomor_transaksi='TRX-INV-001',
            uraian_transaksi='Test Header',
            item=self.item,
            transaction_prefix=self.prefix,
        )

    def test_rekap_jurnal(self):
        response = self.client.get(reverse('jurnal:rekap_jurnal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TRX-INV-001')

    def test_rekap_jurnal_filter_date(self):
        response = self.client.get(reverse('jurnal:rekap_jurnal'), {
            'tanggal_dari': '2024-01-01',
            'tanggal_sampai': '2024-01-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TRX-INV-001')

    def test_rekap_jurnal_filter_excludes(self):
        response = self.client.get(reverse('jurnal:rekap_jurnal'), {
            'tanggal_dari': '2025-01-01',
            'tanggal_sampai': '2025-12-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'TRX-INV-001')

    def test_header_detail(self):
        response = self.client.get(reverse('jurnal:header_detail', args=[self.header.pk]))
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('jurnal:rekap_jurnal'))
        self.assertEqual(response.status_code, 302)


class ManualJurnalViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.tipe_eb = TipeEntitas.objects.create(nama='FnB')
        self.eb1 = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe_eb)
        self.eb2 = EntitasBisnis.objects.create(nama='PT Other', tipe_entitas=self.tipe_eb)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb1, nama='Divisi A')
        self.lv3 = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Unit 1')
        self.akun = Akun.objects.create(kategori_id='aset', kategori_akun=1, nama='Test Akun')

    def test_manual_jurnal_page_shows_all_entitas_levels(self):
        response = self.client.get(reverse('jurnal:manual_jurnal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PT Test')
        self.assertContains(response, 'Divisi A')
        self.assertContains(response, 'Unit 1')
        self.assertContains(response, f'value="lv1:{self.eb1.pk}"')
        self.assertContains(response, f'value="lv2:{self.lv2.pk}"')
        self.assertContains(response, f'value="lv3:{self.lv3.pk}"')

    def test_manual_jurnal_create_with_lv2_selection(self):
        rows_json = json.dumps([
            {'akun_id': self.akun.pk, 'debit': 100000, 'kredit': 0},
            {'akun_id': self.akun.pk, 'debit': 0, 'kredit': 100000},
        ])
        response = self.client.post(reverse('jurnal:manual_jurnal'), {
            'tanggal': '2024-04-01',
            'uraian_transaksi': 'Pembayaran listrik',
            'entitas_bisnis': f'lv2:{self.lv2.pk}',
            'rows_data': rows_json,
        })
        self.assertEqual(response.status_code, 302)
        header = JurnalHeader.objects.latest('pk')
        self.assertEqual(header.entitas_bisnis, self.eb1)
        self.assertEqual(header.details.count(), 2)


class TransactionPrefixViewTests(TestCase):
    """TransactionPrefix is now read-only in master_data app."""
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')

    def test_list(self):
        response = self.client.get(reverse('master_data:prefix_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TRX-INV')


class AutomasiViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        self.lv2 = AsetLv2.objects.create(kode='1.1.8', nama='Persediaan Perlengkapan', aset=lv1)
        self.akun = Akun.objects.get(kategori_id='aset', kategori_akun=self.lv2.pk)
        self.automasi = JurnalAutomasi.objects.create(nama='Stok Awal')

    def test_automasi_list(self):
        response = self.client.get(reverse('jurnal:automasi_list'))
        self.assertEqual(response.status_code, 200)

    def test_automasi_create(self):
        data = {'nama': 'New Automasi'}
        response = self.client.post(reverse('jurnal:automasi_create'), data)
        self.assertRedirects(response, reverse('jurnal:automasi_list'))

    def test_automasi_detail(self):
        response = self.client.get(reverse('jurnal:automasi_detail', args=[self.automasi.pk]))
        self.assertEqual(response.status_code, 200)

    def test_add_akun_mapping(self):
        data = {'akun': self.akun.pk}
        response = self.client.post(
            reverse('jurnal:automasi_add_akun', args=[self.automasi.pk]), data
        )
        self.assertRedirects(response, reverse('jurnal:automasi_detail', args=[self.automasi.pk]))
        self.assertEqual(self.automasi.akun_mappings.count(), 1)

    def test_automasi_entry(self):
        """Test the automated entry creation flow."""
        JurnalAutomasiAkun.objects.create(automasi=self.automasi, akun=self.akun)
        item = Item.objects.create(kode='A', nama='Persediaan')
        prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')
        response = self.client.get(reverse('jurnal:automasi_entry', args=[self.automasi.pk]))
        self.assertEqual(response.status_code, 200)


class NeracaSaldoViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        self.lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=self.lv1)
        self.akun = Akun.objects.get(kategori_id='aset', kategori_akun=self.lv2.pk)
        self.header = JurnalHeader.objects.create(
            tanggal='2024-06-15',
            nomor_transaksi='NS-001',
            uraian_transaksi='Test Neraca',
        )
        JurnalDetail.objects.create(
            jurnal_header=self.header, akun=self.akun, debit=500000, kredit=0
        )

    def test_neraca_saldo_page(self):
        response = self.client.get(reverse('jurnal:neraca_saldo'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kas Kecil')

    def test_neraca_saldo_with_filter(self):
        response = self.client.get(reverse('jurnal:neraca_saldo'), {
            'tanggal_dari': '2024-01-01',
            'tanggal_sampai': '2024-12-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '500.000')

    def test_neraca_saldo_filter_excludes(self):
        response = self.client.get(reverse('jurnal:neraca_saldo'), {
            'tanggal_dari': '2025-01-01',
            'tanggal_sampai': '2025-12-31',
        })
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('jurnal:neraca_saldo'))
        self.assertEqual(response.status_code, 302)


class SaldoAwalPersediaanLedgerTests(TestCase):
    """Task 7: Saldo Awal persediaan rows must mirror into StockMovement,
    carry a per-row warehouse, and stay in sync across create/edit/delete."""

    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)

        self.tipe_eb = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe_eb)

        from apps.inventory.models import Warehouse
        self.wh1 = Warehouse.objects.create(entitas_bisnis=self.eb, kode='GD1', nama='Gudang Utama')
        self.wh2 = Warehouse.objects.create(entitas_bisnis=self.eb, kode='GD2', nama='Gudang Cadangan')

        # Akun with kode_akun '1.1.8' (persediaan prefix per AKUN_DETAIL_PREFIXES)
        aset_lv1 = AsetLv1.objects.create(kode='1.1', nama='Aset Lancar')
        aset_lv2 = AsetLv2.objects.create(kode='1.1.8', nama='Persediaan Barang', aset=aset_lv1)
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        # A second (offsetting) akun for the balancing credit line.
        ekuitas_lv1 = self._make_ekuitas_lv1()
        self.akun_modal = self._make_modal_akun(ekuitas_lv1)

        from apps.purchase.models import ItemMasterPurchase
        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi Arabica', tipe_item='RM', coa_account=self.akun_persediaan,
        )

    @staticmethod
    def _make_ekuitas_lv1():
        from apps.master_data.models import EkuitasLv1
        return EkuitasLv1.objects.create(kode='3', nama='Ekuitas')

    @staticmethod
    def _make_modal_akun(ekuitas_lv1):
        from apps.master_data.models import EkuitasLv2
        lv2 = EkuitasLv2.objects.create(kode='3.1', nama='Modal', ekuitas=ekuitas_lv1)
        return Akun.objects.get(kategori_id='ekuitas', kategori_akun=lv2.pk)

    def _rows_json(self, qty, unit_price, warehouse_id):
        return json.dumps([
            {
                'akun_id': self.akun_persediaan.pk,
                'debit': qty * unit_price,
                'kredit': 0,
                'detail_type': 'persediaan',
                'detail_rows': [{
                    'item_id': str(self.item.pk),
                    'item_text': 'RM — Kopi Arabica',
                    'qty': qty,
                    'unit_price': unit_price,
                    'warehouse_id': str(warehouse_id) if warehouse_id else '',
                    'total': qty * unit_price,
                }],
            },
            {
                'akun_id': self.akun_modal.pk,
                'debit': 0,
                'kredit': qty * unit_price,
            },
        ])

    def _post_create(self, qty, unit_price, warehouse_id):
        return self.client.post(reverse('jurnal:saldo_awal'), {
            'tanggal': '2026-01-01',
            'entitas_bisnis': f'lv1:{self.eb.pk}',
            'rows_data': self._rows_json(qty, unit_price, warehouse_id),
        })

    # -- (a) create ----------------------------------------------------------

    def test_create_writes_inventory_record_fifo_batch_and_stock_movement(self):
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.purchase.models import FIFOBatch

        response = self._post_create(10, 5000, self.wh1.pk)
        self.assertEqual(response.status_code, 302)

        inv = InventoryRecord.objects.get(item=self.item, entitas_bisnis=self.eb)
        self.assertEqual(inv.quantity, Decimal('10'))
        batch = FIFOBatch.objects.get(item=self.item, purchase_item=None)
        self.assertEqual(batch.quantity_in, Decimal('10'))

        mv = StockMovement.objects.get(movement_type='saldo_awal', item=self.item)
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertEqual(mv.warehouse_id, self.wh1.pk)
        self.assertEqual(mv.legacy_fifo_batch_id, batch.pk)
        self.assertEqual(mv.legacy_inventory_record_id, inv.pk)
        self.assertEqual(mv.entitas_bisnis_id, self.eb.pk)

    def test_create_rejects_warehouse_from_other_tenant(self):
        from apps.inventory.models import Warehouse, StockMovement

        other_tipe = TipeEntitas.objects.create(nama='Retail')
        other_eb = EntitasBisnis.objects.create(nama='PT Other', tipe_entitas=other_tipe)
        foreign_wh = Warehouse.objects.create(entitas_bisnis=other_eb, kode='FGN', nama='Gudang Asing')

        with self.assertRaises(ValueError):
            self._post_create(10, 5000, foreign_wh.pk)
        self.assertFalse(StockMovement.objects.filter(movement_type='saldo_awal').exists())

    # -- (b) edit: critical regression test for the reversal gap -------------

    def test_edit_reverses_old_stock_movement_and_creates_new_one(self):
        from apps.inventory.models import StockMovement
        from .models import JurnalHeader

        self._post_create(10, 5000, self.wh1.pk)
        header = JurnalHeader.objects.get(is_saldo_awal=True)
        old_mv = StockMovement.objects.get(movement_type='saldo_awal', item=self.item)
        old_mv_id = old_mv.pk

        response = self.client.post(
            reverse('jurnal:saldo_awal_edit', args=[header.pk]),
            {
                'tanggal': '2026-01-01',
                'entitas_bisnis': f'lv1:{self.eb.pk}',
                'rows_data': self._rows_json(25, 7000, self.wh2.pk),
            },
        )
        self.assertEqual(response.status_code, 302)

        # Old StockMovement is gone (reversed), not left dangling.
        self.assertFalse(StockMovement.objects.filter(pk=old_mv_id).exists())

        # Exactly one fresh StockMovement matching the new data.
        movements = StockMovement.objects.filter(movement_type='saldo_awal', item=self.item)
        self.assertEqual(movements.count(), 1)
        new_mv = movements.first()
        self.assertEqual(new_mv.qty, Decimal('25'))
        self.assertEqual(new_mv.warehouse_id, self.wh2.pk)

    # -- (c) delete: no orphaned StockMovement --------------------------------

    def test_delete_removes_stock_movement(self):
        from apps.inventory.models import StockMovement, InventoryRecord
        from apps.purchase.models import FIFOBatch
        from .models import JurnalHeader

        self._post_create(10, 5000, self.wh1.pk)
        header = JurnalHeader.objects.get(is_saldo_awal=True)
        self.assertTrue(StockMovement.objects.filter(movement_type='saldo_awal').exists())

        response = self.client.post(reverse('jurnal:saldo_awal_delete', args=[header.pk]))
        self.assertEqual(response.status_code, 302)

        self.assertFalse(StockMovement.objects.filter(movement_type='saldo_awal').exists())
        self.assertFalse(InventoryRecord.objects.filter(item=self.item).exists())
        self.assertFalse(FIFOBatch.objects.filter(item=self.item).exists())


class CreateSaldoAwalPersediaanFunctionTests(TestCase):
    """Direct unit tests for the extracted pure function, per the plan's
    preferred fallback (more reliable than exercising the full Client flow)."""

    def setUp(self):
        self.tipe_eb = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe_eb)

        from apps.inventory.models import Warehouse
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, kode='GD1', nama='Gudang Utama')

        from apps.purchase.models import ItemMasterPurchase
        self.item = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')

    def test_creates_linked_records_with_warehouse(self):
        from .views import create_saldo_awal_persediaan
        from apps.inventory.models import InventoryRecord, StockMovement
        from apps.purchase.models import FIFOBatch

        rows = [{
            'detail_type': 'persediaan',
            'detail_rows': [{
                'item_id': str(self.item.pk), 'qty': 3, 'unit_price': 1000,
                'warehouse_id': str(self.wh.pk),
            }],
        }]
        create_saldo_awal_persediaan(rows, self.eb.pk, '2026-01-01')

        inv = InventoryRecord.objects.get(item=self.item)
        batch = FIFOBatch.objects.get(item=self.item)
        mv = StockMovement.objects.get(item=self.item, movement_type='saldo_awal')
        self.assertEqual(mv.legacy_inventory_record_id, inv.pk)
        self.assertEqual(mv.legacy_fifo_batch_id, batch.pk)
        self.assertEqual(mv.warehouse_id, self.wh.pk)
        self.assertEqual(mv.qty, Decimal('3'))
        self.assertEqual(mv.unit_cost, Decimal('1000'))

    def test_cross_tenant_warehouse_raises(self):
        from .views import create_saldo_awal_persediaan
        from apps.inventory.models import Warehouse

        other_tipe = TipeEntitas.objects.create(nama='Retail')
        other_eb = EntitasBisnis.objects.create(nama='PT Other', tipe_entitas=other_tipe)
        foreign_wh = Warehouse.objects.create(entitas_bisnis=other_eb, kode='FGN', nama='Gudang Asing')

        rows = [{
            'detail_type': 'persediaan',
            'detail_rows': [{
                'item_id': str(self.item.pk), 'qty': 3, 'unit_price': 1000,
                'warehouse_id': str(foreign_wh.pk),
            }],
        }]
        with self.assertRaises(ValueError):
            create_saldo_awal_persediaan(rows, self.eb.pk, '2026-01-01')

    def test_no_warehouse_is_allowed(self):
        from .views import create_saldo_awal_persediaan
        from apps.inventory.models import StockMovement

        rows = [{
            'detail_type': 'persediaan',
            'detail_rows': [{
                'item_id': str(self.item.pk), 'qty': 3, 'unit_price': 1000,
            }],
        }]
        create_saldo_awal_persediaan(rows, self.eb.pk, '2026-01-01')
        mv = StockMovement.objects.get(item=self.item, movement_type='saldo_awal')
        self.assertIsNone(mv.warehouse_id)
