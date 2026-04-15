"""Purchase module tests."""
import json
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun, AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2, EkuitasLv1, EkuitasLv2
from apps.jurnal.models import JurnalHeader, JurnalDetail

from .models import (
    KategoriItem, ItemMasterPurchase, SubTransactionType,
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, FIFOBatch,
)
from .services import create_automated_journals, create_fifo_batches


class KategoriItemModelTests(TestCase):
    def test_str(self):
        k = KategoriItem.objects.create(nama='Coffee', tipe_item='RM')
        self.assertEqual(str(k), 'Coffee (Raw Material)')

    def test_unique_nama_tipe(self):
        KategoriItem.objects.create(nama='Coffee', tipe_item='RM')
        with self.assertRaises(Exception):
            KategoriItem.objects.create(nama='Coffee', tipe_item='RM')


class ItemMasterPurchaseModelTests(TestCase):
    def test_auto_generate_item_id_rm(self):
        item = ItemMasterPurchase.objects.create(nama='Kopi Arabica', tipe_item='RM')
        self.assertEqual(item.item_id, 'RM-0001')

    def test_auto_generate_item_id_fg(self):
        item = ItemMasterPurchase.objects.create(nama='Es Kopi Susu', tipe_item='FG')
        self.assertEqual(item.item_id, 'FG-0001')

    def test_auto_generate_item_id_itm(self):
        item = ItemMasterPurchase.objects.create(nama='Serbet', tipe_item='ITM')
        self.assertEqual(item.item_id, 'ITM-0001')

    def test_sequential_ids(self):
        ItemMasterPurchase.objects.create(nama='Item A', tipe_item='RM')
        item2 = ItemMasterPurchase.objects.create(nama='Item B', tipe_item='RM')
        self.assertEqual(item2.item_id, 'RM-0002')

    def test_str(self):
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.assertEqual(str(item), 'RM-0001 - Kopi')

    def test_unique_nama(self):
        ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        with self.assertRaises(Exception):
            ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='FG')


class SubTransactionTypeModelTests(TestCase):
    def setUp(self):
        lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        lv2 = AsetLv2.objects.create(aset=lv1, kode='1', nama='Kas')
        self.akun = Akun.objects.get(kategori_id='aset', kategori_akun=lv2.pk)

    def test_str(self):
        stt = SubTransactionType.objects.create(
            nama='Stok Awal', direction='inflow', default_offset_account=self.akun,
        )
        self.assertIn('Stok Awal', str(stt))
        self.assertIn('Inflow', str(stt))


class PurchaseHeaderModelTests(TestCase):
    def test_auto_generate_transaction_id(self):
        ph = PurchaseHeader.objects.create(tanggal='2026-01-01')
        self.assertEqual(ph.transaction_id, 'PUR-INV-001')

    def test_sequential_transaction_ids(self):
        PurchaseHeader.objects.create(tanggal='2026-01-01')
        ph2 = PurchaseHeader.objects.create(tanggal='2026-01-02')
        self.assertEqual(ph2.transaction_id, 'PUR-INV-002')

    def test_str(self):
        ph = PurchaseHeader.objects.create(tanggal='2026-01-01')
        self.assertEqual(str(ph), 'PUR-INV-001')


class PurchaseItemModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Cafe ABC', tipe_entitas=self.tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item = ItemMasterPurchase.objects.create(nama='Kopi Arabica', tipe_item='RM', coa_account=self.akun_persediaan)
        self.stt = SubTransactionType.objects.create(
            nama='Stok Awal', direction='inflow', default_offset_account=self.akun_modal,
        )
        self.ph = PurchaseHeader.objects.create(tanggal='2026-01-01')
        self.peb = PurchaseEntitasBisnis.objects.create(purchase_header=self.ph, entitas_bisnis=self.eb)

    def test_total_value_computed(self):
        pi = PurchaseItem.objects.create(
            purchase_eb=self.peb,
            item=self.item,
            sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan,
            offset_coa_account=self.akun_modal,
            quantity=Decimal('10'),
            unit_price=Decimal('50000'),
        )
        self.assertEqual(pi.total_value, Decimal('500000'))

    def test_str(self):
        pi = PurchaseItem.objects.create(
            purchase_eb=self.peb,
            item=self.item,
            sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan,
            offset_coa_account=self.akun_modal,
            quantity=Decimal('5'),
            unit_price=Decimal('100'),
        )
        self.assertIn('RM-0001', str(pi))


class FIFOBatchModelTests(TestCase):
    def test_batch_value_computed(self):
        item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        batch = FIFOBatch.objects.create(
            item=item, tanggal='2026-01-01',
            quantity_in=Decimal('10'), unit_price=Decimal('1000'),
            remaining_qty=Decimal('10'),
        )
        self.assertEqual(batch.batch_value, Decimal('10000'))


class PurchaseServicesTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Cafe ABC', tipe_entitas=self.tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi Arabica', tipe_item='RM', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Stok Awal', direction='inflow', default_offset_account=self.akun_modal,
        )

        self.ph = PurchaseHeader.objects.create(tanggal='2026-01-15', deskripsi='Test purchase')
        self.peb = PurchaseEntitasBisnis.objects.create(purchase_header=self.ph, entitas_bisnis=self.eb)
        self.pi = PurchaseItem.objects.create(
            purchase_eb=self.peb,
            item=self.item,
            sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan,
            offset_coa_account=self.akun_modal,
            quantity=Decimal('20'),
            unit_price=Decimal('5000'),
        )

    def test_create_automated_journals(self):
        headers = create_automated_journals(self.ph)
        self.assertEqual(len(headers), 1)
        header = headers[0]
        self.assertTrue(header.nomor_transaksi.startswith('TRX-PUR-'))
        self.assertEqual(header.entitas_bisnis, self.eb)
        self.assertFalse(header.is_penyesuaian)

        details = header.details.all()
        self.assertEqual(details.count(), 2)
        debit_detail = details.filter(debit__gt=0).first()
        credit_detail = details.filter(kredit__gt=0).first()
        self.assertEqual(debit_detail.akun, self.akun_persediaan)
        self.assertEqual(debit_detail.debit, Decimal('100000'))
        self.assertEqual(credit_detail.akun, self.akun_modal)
        self.assertEqual(credit_detail.kredit, Decimal('100000'))

    def test_create_fifo_batches(self):
        batches = create_fifo_batches(self.ph)
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch.item, self.item)
        self.assertEqual(batch.quantity_in, Decimal('20'))
        self.assertEqual(batch.remaining_qty, Decimal('20'))
        self.assertEqual(batch.unit_price, Decimal('5000'))

    def test_outflow_no_fifo_batch(self):
        """Outflow sub-transaction type should not create FIFO batches."""
        stt_out = SubTransactionType.objects.create(
            nama='Retur', direction='outflow', default_offset_account=self.akun_modal,
        )
        ph2 = PurchaseHeader.objects.create(tanggal='2026-01-16')
        peb2 = PurchaseEntitasBisnis.objects.create(purchase_header=ph2, entitas_bisnis=self.eb)
        PurchaseItem.objects.create(
            purchase_eb=peb2, item=self.item, sub_transaction_type=stt_out,
            coa_account=self.akun_persediaan, offset_coa_account=self.akun_modal,
            quantity=Decimal('5'), unit_price=Decimal('5000'),
        )
        batches = create_fifo_batches(ph2)
        self.assertEqual(len(batches), 0)


class PurchaseViewTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(kode='admin', nama='Admin')
        self.user = User.objects.create_user(email='test@test.com', password='pass1234', role=self.role)
        self.client = Client()
        self.client.login(email='test@test.com', password='pass1234')

        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Cafe ABC', tipe_entitas=self.tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi Arabica', tipe_item='RM', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Stok Awal', direction='inflow', default_offset_account=self.akun_modal,
        )

    def test_purchase_list_get(self):
        resp = self.client.get(reverse('purchase:list'))
        self.assertEqual(resp.status_code, 200)

    def test_purchase_create_get(self):
        resp = self.client.get(reverse('purchase:create'))
        self.assertEqual(resp.status_code, 200)

    def test_purchase_create_post(self):
        groups = [{
            'entitas_bisnis_id': self.eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'coa_account_id': self.akun_persediaan.pk,
                'offset_coa_account_id': self.akun_modal.pk,
                'quantity': '10',
                'unit_price': '5000',
            }],
        }]
        resp = self.client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PurchaseHeader.objects.count(), 1)
        # Journal + FIFO should be created
        self.assertEqual(JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-PUR-').count(), 1)
        self.assertEqual(FIFOBatch.objects.count(), 1)

    def test_purchase_detail(self):
        ph = PurchaseHeader.objects.create(tanggal='2026-01-01')
        resp = self.client.get(reverse('purchase:detail', args=[ph.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_purchase_update_get(self):
        """Edit page should load with existing purchase data."""
        groups = [{
            'entitas_bisnis_id': self.eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'coa_account_id': self.akun_persediaan.pk,
                'offset_coa_account_id': self.akun_modal.pk,
                'quantity': '10',
                'unit_price': '5000',
            }],
        }]
        self.client.post(reverse('purchase:create'), {
            'tanggal': '2026-03-01',
            'deskripsi': 'Edit Test',
            'eb_groups_data': json.dumps(groups),
        })
        ph = PurchaseHeader.objects.first()
        resp = self.client.get(reverse('purchase:update', args=[ph.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should contain the existing group data as JSON for pre-filling
        self.assertContains(resp, 'Edit Purchase')
        self.assertContains(resp, str(self.item))

    def test_purchase_delete_locked(self):
        ph = PurchaseHeader.objects.create(tanggal='2026-01-01', is_locked=True)
        resp = self.client.post(reverse('purchase:delete', args=[ph.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(PurchaseHeader.objects.filter(pk=ph.pk).exists())

    def test_purchase_delete_success(self):
        groups = [{
            'entitas_bisnis_id': self.eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'coa_account_id': self.akun_persediaan.pk,
                'offset_coa_account_id': self.akun_modal.pk,
                'quantity': '10',
                'unit_price': '5000',
            }],
        }]
        self.client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test',
            'eb_groups_data': json.dumps(groups),
        })
        ph = PurchaseHeader.objects.first()
        resp = self.client.post(reverse('purchase:delete', args=[ph.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PurchaseHeader.objects.exists())

    def test_purchase_list_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('purchase:list'))
        self.assertEqual(resp.status_code, 302)

    # ── Item Master Views ────────────────────────────────────────────────────

    def test_item_master_list(self):
        resp = self.client.get(reverse('purchase:item_master_list'))
        # Now redirects to persediaan_list
        self.assertEqual(resp.status_code, 302)

    def test_persediaan_list(self):
        resp = self.client.get(reverse('purchase:persediaan_list'))
        self.assertEqual(resp.status_code, 200)

    def test_item_master_create_post(self):
        resp = self.client.post(reverse('purchase:item_master_create'), {
            'nama': 'Gula Pasir',
            'tipe_item': 'RM',
            'unit_price': '15000',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ItemMasterPurchase.objects.filter(nama='Gula Pasir').exists())

    def test_item_master_update(self):
        resp = self.client.post(reverse('purchase:item_master_update', args=[self.item.pk]), {
            'nama': 'Kopi Robusta',
            'tipe_item': 'RM',
            'unit_price': '40000',
        })
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.nama, 'Kopi Robusta')

    def test_item_master_delete(self):
        item2 = ItemMasterPurchase.objects.create(nama='Gula', tipe_item='RM')
        resp = self.client.post(reverse('purchase:item_master_delete', args=[item2.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ItemMasterPurchase.objects.filter(pk=item2.pk).exists())

    # ── Settings Views ───────────────────────────────────────────────────────

    def test_settings_list(self):
        resp = self.client.get(reverse('purchase:settings_list'))
        self.assertEqual(resp.status_code, 200)

    def test_settings_create(self):
        resp = self.client.post(reverse('purchase:settings_create'), {
            'nama': 'Pembelian Tunai',
            'module': 'purchase',
            'direction': 'inflow',
            'default_offset_account': self.akun_modal.pk,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SubTransactionType.objects.filter(nama='Pembelian Tunai').exists())

    def test_settings_update(self):
        resp = self.client.post(reverse('purchase:settings_update', args=[self.stt.pk]), {
            'nama': 'Stok Awal v2',
            'module': 'purchase',
            'direction': 'inflow',
            'default_offset_account': self.akun_modal.pk,
        })
        self.assertEqual(resp.status_code, 302)
        self.stt.refresh_from_db()
        self.assertEqual(self.stt.nama, 'Stok Awal v2')

    def test_settings_delete(self):
        stt2 = SubTransactionType.objects.create(
            nama='Temp', direction='outflow', default_offset_account=self.akun_modal,
        )
        resp = self.client.post(reverse('purchase:settings_delete', args=[stt2.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SubTransactionType.objects.filter(pk=stt2.pk).exists())

    # ── Kategori Views ───────────────────────────────────────────────────────

    def test_kategori_list(self):
        resp = self.client.get(reverse('purchase:kategori_list'))
        self.assertEqual(resp.status_code, 200)

    def test_kategori_crud(self):
        resp = self.client.post(reverse('purchase:kategori_create'), {'nama': 'Coffee', 'tipe_item': 'RM'})
        self.assertEqual(resp.status_code, 302)
        k = KategoriItem.objects.get(nama='Coffee')
        resp = self.client.post(reverse('purchase:kategori_update', args=[k.pk]), {'nama': 'Coffee Updated', 'tipe_item': 'RM'})
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(reverse('purchase:kategori_delete', args=[k.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(KategoriItem.objects.filter(pk=k.pk).exists())

    # ── API Views ────────────────────────────────────────────────────────────

    def test_api_item_autocomplete(self):
        resp = self.client.get(reverse('purchase:api_item_autocomplete'), {'term': 'Kopi'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data), 1)

    def test_api_item_create_new(self):
        resp = self.client.post(
            reverse('purchase:api_item_create'),
            json.dumps({'nama': 'Bahan Baru Sekali'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data['created'])
        self.assertEqual(data['nama'], 'Bahan Baru Sekali')
        self.assertEqual(data['tipe_item'], 'RM')
        self.assertTrue(ItemMasterPurchase.objects.filter(nama='Bahan Baru Sekali').exists())

    def test_api_item_create_duplicate_returns_existing(self):
        resp = self.client.post(
            reverse('purchase:api_item_create'),
            json.dumps({'nama': 'Kopi Arabica'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['created'])
        self.assertEqual(data['id'], self.item.pk)

    def test_api_item_create_missing_nama(self):
        resp = self.client.post(
            reverse('purchase:api_item_create'),
            json.dumps({'nama': ''}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_stt_offset(self):
        resp = self.client.get(reverse('purchase:api_stt_offset'), {'stt_id': self.stt.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['offset_account_id'], self.akun_modal.pk)

    def test_journal_preview(self):
        payload = {
            'eb_groups': [{
                'entitas_bisnis_id': self.eb.pk,
                'entitas_bisnis_name': 'Cafe ABC',
                'items': [{
                    'item_name': 'Kopi',
                    'coa_account_text': 'Persediaan',
                    'offset_coa_account_text': 'Modal',
                    'quantity': '10',
                    'unit_price': '5000',
                }],
            }],
        }
        resp = self.client.post(
            reverse('purchase:api_journal_preview'),
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['entries']), 2)
        self.assertEqual(data['entries'][0]['debit'], '50000')
        self.assertEqual(data['entries'][0]['kredit'], '')
        self.assertEqual(data['entries'][1]['debit'], '')
        self.assertEqual(data['entries'][1]['kredit'], '50000')
