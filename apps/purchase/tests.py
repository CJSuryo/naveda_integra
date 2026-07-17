"""Purchase module tests."""
import json
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User, Role
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import (
    Akun, AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2, EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2,
)
from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem

from .models import (
    KategoriItem, ItemMasterPurchase, SubTransactionType,
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, FIFOBatch,
)
from .services import create_automated_journals, create_fifo_batches


class ItemMasterFormUomTests(TestCase):
    """Registration simplification: stock_uom is the one required unit; purchase
    and sales units are optional transaction defaults, not mandatory setup."""

    def _form(self):
        from apps.purchase.forms import ItemMasterPurchaseForm
        return ItemMasterPurchaseForm(tipe_item_choices=['ITM'])

    def test_stock_uom_required_for_inventory_item(self):
        self.assertTrue(self._form().fields['stock_uom'].required)

    def test_purchase_uom_not_in_registration_form(self):
        # Registration asks for the stock unit only; purchase unit is chosen
        # freely at transaction time, not fixed here.
        self.assertNotIn('purchase_uom', self._form().fields)

    def test_sales_uom_not_in_registration_form(self):
        self.assertNotIn('sales_uom', self._form().fields)

    def test_asset_item_has_no_stock_uom_field(self):
        from apps.purchase.forms import ItemMasterPurchaseForm
        form = ItemMasterPurchaseForm(tipe_item_choices=['ATP'])
        self.assertNotIn('stock_uom', form.fields)


class RegistrationUomUiTests(TestCase):
    """Rendered UIs must ask for the stock unit only — no purchase/sales unit
    inputs at item registration or in the purchase quick-add modal."""

    def setUp(self):
        role = Role.objects.create(kode='admin', nama='Admin UI UOM')
        self.user = User.objects.create_user(
            email='ui-uom@test.com', password='pass1234', role=role)
        self.client = Client()
        self.client.force_login(self.user)

    def test_item_master_form_has_no_purchase_sales_unit(self):
        resp = self.client.get(reverse('purchase:item_master_create'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn('name="purchase_uom"', body)
        self.assertNotIn('name="sales_uom"', body)

    def test_purchase_detail_renders_with_no_items(self):
        """A purchase header with zero entitas groups/items must still render
        (Prefetch-based item loading must not choke on an empty relation)."""
        ph = PurchaseHeader.objects.create(tanggal='2026-01-01')
        resp = self.client.get(reverse('purchase:detail', args=[ph.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_purchase_item_row_satuan_column_is_visible_not_advanced(self):
        """The per-line Satuan (input_uom) selector must live in the always-
        visible item row, next to Qty — not inside the advanced-row block
        that's collapsed by default behind the 'Advanced' toggle."""
        resp = self.client.get(reverse('purchase:create'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('class="uom-cell"', body)
        main_row_marker = body.index('tr.innerHTML =')
        advanced_row_marker = body.index("trAdv.innerHTML =")
        uom_cell_pos = body.index('class="uom-cell"')
        self.assertTrue(main_row_marker < uom_cell_pos < advanced_row_marker)

    def test_purchase_quick_add_modal_has_no_purchase_sales_unit(self):
        resp = self.client.get(reverse('purchase:create'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn('modal_purchase_uom', body)
        self.assertNotIn('modal_sales_uom', body)
        # The per-line transaction unit selector must remain.
        self.assertIn('modal_stock_uom', body)


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
        from apps.uom.models import UnitOfMeasure
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        resp = self.client.post(reverse('purchase:item_master_create'), {
            'nama': 'Gula Pasir',
            'tipe_item': 'RM',
            'unit_price': '15000',
            'stock_uom': pcs.pk,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(ItemMasterPurchase.objects.filter(nama='Gula Pasir').exists())

    def test_item_master_update(self):
        from apps.uom.models import UnitOfMeasure
        pcs = UnitOfMeasure.objects.get(kode='pcs')
        resp = self.client.post(reverse('purchase:item_master_update', args=[self.item.pk]), {
            'nama': 'Kopi Robusta',
            'tipe_item': 'RM',
            'unit_price': '40000',
            'stock_uom': pcs.pk,
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

    def test_settings_delete_protected_by_sales_item(self):
        """Bug 2 regression: deleting an STT referenced by a SalesItem must be
        blocked (ProtectedError / non-2xx response) because SalesItem has a
        PROTECT FK to SubTransactionType.  The view must handle this gracefully.
        """
        stt_sales = SubTransactionType.objects.create(
            nama='Penjualan Tunai', module='sales', direction='outflow',
            default_offset_account=self.akun_modal,
        )
        tipe = TipeEntitas.objects.create(nama='Test')
        eb = EntitasBisnis.objects.create(nama='EB Test', tipe_entitas=tipe)
        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pend Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        header = SalesHeader.objects.create()
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=eb, payment_account=self.akun_modal,
        )
        SalesItem.objects.create(
            sales_eb=eb_group,
            item=self.item,
            sub_transaction_type=stt_sales,
            quantity=Decimal('1'),
            selling_price=Decimal('10000'),
            offset_coa_account=self.akun_persediaan,
            revenue_account=akun_pendapatan,
        )
        # Attempting to delete should NOT succeed (PROTECT FK).
        # After the fix the view redirects back with an error message instead of 500.
        resp = self.client.post(reverse('purchase:settings_delete', args=[stt_sales.pk]))
        self.assertEqual(resp.status_code, 302)
        # The STT must still exist in the database.
        self.assertTrue(
            SubTransactionType.objects.filter(pk=stt_sales.pk).exists(),
            'STT referenced by a SalesItem must not be deletable.',
        )

    def test_is_saldo_awal_field_on_jurnal_header(self):
        """Bug 3 regression: JurnalHeader.is_saldo_awal must exist and be
        queryable.  Any queryset evaluation on JurnalHeader (e.g. during
        purchase deletion) will fail if this column is absent.
        """
        h = JurnalHeader.objects.create(
            nomor_transaksi='TRX-SALDO-001',
            uraian_transaksi='Saldo Awal Test',
            tanggal='2026-01-01',
            is_saldo_awal=True,
        )
        h.refresh_from_db()
        self.assertTrue(h.is_saldo_awal)

        # Verify filter works (this is the query pattern used in reverse_automated_journals)
        self.assertEqual(JurnalHeader.objects.filter(is_saldo_awal=True).count(), 1)
        self.assertEqual(JurnalHeader.objects.filter(is_saldo_awal=False).count(), 0)

    def test_purchase_delete_does_not_delete_saldo_awal_journals(self):
        """Saldo awal journals have different nomor_transaksi so they must not be
        removed when a purchase is deleted (reverse_automated_journals only
        matches TRX-PUR- prefixed entries).
        """
        import json
        groups = [{
            'entitas_bisnis_id': self.eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'coa_account_id': self.akun_persediaan.pk,
                'offset_coa_account_id': self.akun_modal.pk,
                'quantity': '5',
                'unit_price': '1000',
            }],
        }]
        self.client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test',
            'eb_groups_data': json.dumps(groups),
        })
        # Create an unrelated saldo awal journal that must survive the delete
        jh = JurnalHeader.objects.create(
            nomor_transaksi='TRX-SALDO-AWAL-001',
            uraian_transaksi='Saldo Awal',
            tanggal='2026-01-01',
            is_saldo_awal=True,
        )
        ph = PurchaseHeader.objects.first()
        self.client.post(reverse('purchase:delete', args=[ph.pk]))
        # Purchase journal removed, saldo awal journal untouched
        self.assertFalse(PurchaseHeader.objects.exists())
        self.assertTrue(JurnalHeader.objects.filter(pk=jh.pk).exists())


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


class CreateStockMovementsTests(TestCase):
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

        self.header = PurchaseHeader.objects.create(tanggal='2026-01-01')
        self.peb = PurchaseEntitasBisnis.objects.create(
            purchase_header=self.header, entitas_bisnis=self.eb)
        self.pi = PurchaseItem.objects.create(
            purchase_eb=self.peb, item=self.item, sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan, offset_coa_account=self.akun_modal,
            quantity=Decimal('10'), unit_price=Decimal('5'))

    def test_creates_linked_stock_movement(self):
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
        )
        from apps.inventory.models import StockMovement
        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        movements = create_stock_movements(self.header)
        self.assertEqual(len(movements), 1)
        mv = movements[0]
        self.assertEqual(mv.qty, Decimal('10'))
        self.assertIsNotNone(mv.legacy_fifo_batch)
        self.assertIsNotNone(mv.legacy_inventory_record)
        self.assertEqual(mv.entitas_bisnis, self.eb)

    def test_multiple_purchase_items_link_to_own_batch_and_record(self):
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
        )
        from apps.purchase.models import PurchaseItem

        pi2 = PurchaseItem.objects.create(
            purchase_eb=self.peb, item=self.item, sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan, offset_coa_account=self.akun_modal,
            quantity=Decimal('99'), unit_price=Decimal('7'))

        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        movements = create_stock_movements(self.header)

        self.assertEqual(len(movements), 2)
        mv_for_pi1 = next(m for m in movements if m.legacy_fifo_batch.purchase_item_id == self.pi.id)
        mv_for_pi2 = next(m for m in movements if m.legacy_fifo_batch.purchase_item_id == pi2.id)

        self.assertNotEqual(mv_for_pi1.legacy_fifo_batch_id, mv_for_pi2.legacy_fifo_batch_id)
        self.assertNotEqual(mv_for_pi1.legacy_inventory_record_id, mv_for_pi2.legacy_inventory_record_id)
        self.assertEqual(mv_for_pi1.legacy_inventory_record.purchase_item_id, self.pi.id)
        self.assertEqual(mv_for_pi2.legacy_inventory_record.purchase_item_id, pi2.id)
        self.assertEqual(mv_for_pi1.qty, Decimal('10'))
        self.assertEqual(mv_for_pi2.qty, Decimal('99'))

    def test_reverse_stock_movements_deletes_layers(self):
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
            reverse_stock_movements,
        )
        from apps.inventory.models import StockMovement
        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        create_stock_movements(self.header)
        self.assertTrue(StockMovement.objects.filter(source_object_id=self.pi.id).exists())
        reverse_stock_movements(self.header)
        self.assertFalse(StockMovement.objects.filter(
            item=self.item, movement_type='purchase_in').exists())

    def test_reverse_stock_movements_does_not_touch_other_purchase(self):
        """Cross-purchase isolation: reversing purchase A must not affect purchase B's layers."""
        from apps.purchase.models import PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
            reverse_stock_movements,
        )
        from apps.inventory.models import StockMovement

        # Purchase A: the existing self.header/self.pi from setUp.
        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        create_stock_movements(self.header)

        # Purchase B: a separate purchase, same item.
        header_b = PurchaseHeader.objects.create(tanggal='2026-01-02')
        peb_b = PurchaseEntitasBisnis.objects.create(
            purchase_header=header_b, entitas_bisnis=self.eb)
        pi_b = PurchaseItem.objects.create(
            purchase_eb=peb_b, item=self.item, sub_transaction_type=self.stt,
            coa_account=self.akun_persediaan, offset_coa_account=self.akun_modal,
            quantity=Decimal('20'), unit_price=Decimal('6'))
        create_fifo_batches(header_b)
        create_inventory_records(header_b)
        create_stock_movements(header_b)

        # Reverse purchase A only.
        reverse_stock_movements(self.header)

        # Purchase A's layer is gone.
        self.assertFalse(StockMovement.objects.filter(
            source_object_id=self.pi.id, movement_type='purchase_in').exists())
        # Purchase B's layer survives, untouched.
        mv_b = StockMovement.objects.get(source_object_id=pi_b.id, movement_type='purchase_in')
        self.assertEqual(mv_b.qty, Decimal('20'))

    def test_purchase_stock_movement_carries_warehouse(self):
        from apps.inventory.models import Warehouse, StockMovement
        from apps.purchase.services import (
            create_fifo_batches, create_inventory_records, create_stock_movements,
        )
        wh = Warehouse.objects.create(entitas_bisnis=self.eb, kode='PGD', nama='Gudang Beli')
        self.pi.warehouse = wh
        self.pi.save(update_fields=['warehouse'])

        create_fifo_batches(self.header)
        create_inventory_records(self.header)
        create_stock_movements(self.header)

        mv = StockMovement.objects.get(
            source_object_id=self.pi.pk, source_content_type__model='purchaseitem')
        self.assertEqual(mv.warehouse_id, wh.pk)


class PurchaseUomConversionTests(TestCase):
    """Konversi diterapkan lewat helper; ledger tetap dalam base."""
    def setUp(self):
        from apps.uom.models import UnitOfMeasure, ItemUOM
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(
            nama='Beli', tipe_item='ITM', stock_uom=self.pcs)
        self.ctn = UnitOfMeasure.objects.create(
            kode='ctn-p', nama='Carton', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.item, uom=self.ctn, qty_in_stock_uom=Decimal('24'))

    def test_helper_carton_purchase(self):
        from apps.uom.conversion import convert_input_to_base
        qty, price = convert_input_to_base(self.item, self.ctn, Decimal('10'), Decimal('24000'))
        self.assertEqual(qty, Decimal('240'))
        self.assertEqual(price, Decimal('1000'))

    def _create_purchase_via_view(self, client):
        """Shared setup: POST a purchase creating an inventory-backed item, and
        return (purchase_header, purchase_item)."""
        tipe = TipeEntitas.objects.create(nama='FnB UOM Detail')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Detail', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        stt = SubTransactionType.objects.create(
            nama='Stok Awal UOM Detail', direction='inflow', default_offset_account=akun_modal,
        )

        groups = [{
            'entitas_bisnis_id': eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'coa_account_id': akun_persediaan.pk,
                'offset_coa_account_id': akun_modal.pk,
                'quantity': '10',
                'unit_price': '24000',
                'input_uom_id': self.ctn.pk,
            }],
        }]
        resp = client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Detail',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        purchase = PurchaseHeader.objects.get(deskripsi='Test UOM Detail')
        pi = PurchaseItem.objects.get(item=self.item, purchase_eb__purchase_header=purchase)
        return purchase, pi

    def test_purchase_detail_shows_qty_with_stock_uom(self):
        """The Qty column on the purchase detail page must show the item's
        stock unit next to the quantity — the stored quantity is already base
        (pcs), so showing a bare number is ambiguous."""
        from django.template.defaultfilters import floatformat
        from django.contrib.humanize.templatetags.humanize import intcomma

        role = Role.objects.create(kode='admin', nama='Admin UOM Detail')
        user = User.objects.create_user(email='uom-detail@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        purchase, pi = self._create_purchase_via_view(client)
        resp = client.get(reverse('purchase:detail', args=[purchase.pk]))
        self.assertEqual(resp.status_code, 200)
        expected_qty = intcomma(floatformat(pi.quantity, 0))
        self.assertContains(resp, f'{expected_qty} pcs')

    def test_purchase_detail_item_name_links_to_inventory_detail(self):
        """The item name on the purchase detail page must link to the
        InventoryRecord created for that purchase line, so a user can jump
        straight from the transaction to the persediaan record it produced."""
        from apps.inventory.models import InventoryRecord

        role = Role.objects.create(kode='admin', nama='Admin UOM Detail Link')
        user = User.objects.create_user(email='uom-detail-link@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        purchase, pi = self._create_purchase_via_view(client)
        record = InventoryRecord.objects.get(purchase_item=pi)

        resp = client.get(reverse('purchase:detail', args=[purchase.pk]))
        self.assertEqual(resp.status_code, 200)
        expected_url = reverse('inventory:detail', args=[record.pk])
        self.assertContains(resp, f'href="{expected_url}"')

    def test_purchase_create_post_converts_carton_to_base(self):
        """POSTing an item with input_uom_id in cartons should be converted to base
        units (pcs) before being saved to PurchaseItem, exercising the real view path."""
        role = Role.objects.create(kode='admin', nama='Admin UOM')
        user = User.objects.create_user(email='uom@test.com', password='pass1234', role=role)
        client = Client()
        client.login(email='uom@test.com', password='pass1234')

        tipe = TipeEntitas.objects.create(nama='FnB UOM')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        stt = SubTransactionType.objects.create(
            nama='Stok Awal UOM', direction='inflow', default_offset_account=akun_modal,
        )

        groups = [{
            'entitas_bisnis_id': eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'coa_account_id': akun_persediaan.pk,
                'offset_coa_account_id': akun_modal.pk,
                'quantity': '10',
                'unit_price': '24000',
                'input_uom_id': self.ctn.pk,
            }],
        }]
        resp = client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        pi = PurchaseItem.objects.get(item=self.item)
        self.assertEqual(pi.quantity, Decimal('240'))
        self.assertEqual(pi.unit_price, Decimal('1000'))
        self.assertEqual(pi.input_uom, self.ctn)
        self.assertEqual(pi.input_qty, Decimal('10'))

    def test_item_uoms_data_default_is_always_stock_uom(self):
        """The transaction UOM selector must default to the item's stock unit,
        never a legacy purchase_uom/sales_uom value — registration no longer
        sets those, and they must not resurface as a stale default."""
        from apps.uom.models import UnitOfMeasure
        from apps.purchase.views import _get_item_uoms_data
        carton_default = UnitOfMeasure.objects.create(
            kode='ctn-legacy', nama='Legacy Carton', dimension='count', factor_to_base=None)
        self.item.purchase_uom = carton_default  # stale/legacy data, no ItemUOM defined
        self.item.save(update_fields=['purchase_uom'])

        data = _get_item_uoms_data()[self.item.pk]
        self.assertEqual(data['default_id'], self.pcs.pk)
        kodes = {o['kode'] for o in data['options']}
        self.assertNotIn('ctn-legacy', kodes)

    def test_item_uoms_data_includes_all_same_dimension_physical_units(self):
        """User must be able to pick any unit in the same dimension as the
        stock unit (e.g. kg stock -> g, ton also selectable), not just an
        explicitly configured default — physical conversion is universal."""
        from apps.uom.models import UnitOfMeasure
        from apps.purchase.views import _get_item_uoms_data
        kg = UnitOfMeasure.objects.get(kode='kg')
        item_kg = ItemMasterPurchase.objects.create(
            nama='Tepung', tipe_item='ITM', stock_uom=kg)

        data = _get_item_uoms_data()[item_kg.pk]
        kodes = {o['kode'] for o in data['options']}
        self.assertIn('kg', kodes)
        self.assertIn('g', kodes)
        self.assertIn('ton', kodes)
        self.assertEqual(data['default_id'], kg.pk)

    def test_item_uoms_data_includes_itemuom_packaging(self):
        """A packaging unit explicitly defined via ItemUOM for this item must
        still be offered."""
        from apps.purchase.views import _get_item_uoms_data
        data = _get_item_uoms_data()[self.item.pk]
        kodes = {o['kode'] for o in data['options']}
        self.assertIn('ctn-p', kodes)

    def test_item_uoms_data_excludes_undefined_packaging_same_dimension(self):
        """A same-dimension packaging unit (e.g. box) with no ItemUOM defined
        for this item must not be offered — 'same dimension' only guarantees
        automatic conversion for physical units; packaging needs a per-item
        factor, so offering it here would let a user pick a unit the backend
        guard later rejects."""
        from apps.purchase.views import _get_item_uoms_data
        data = _get_item_uoms_data()[self.item.pk]
        kodes = {o['kode'] for o in data['options']}
        self.assertNotIn('box', kodes)

    def test_purchase_create_rejects_unresolvable_input_uom(self):
        """An input_uom with no conversion path for the item (different
        dimension, no ItemUOM) must be rejected with a form error instead of
        blowing up mid-transaction or silently mis-converting."""
        from apps.uom.models import UnitOfMeasure
        kg = UnitOfMeasure.objects.get(kode='kg')  # weight; item stock is pcs (count)
        role = Role.objects.create(kode='admin', nama='Admin UOM Bad')
        user = User.objects.create_user(email='uom-bad@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Bad')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Bad', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        stt = SubTransactionType.objects.create(
            nama='Stok Awal UOM Bad', direction='inflow', default_offset_account=akun_modal,
        )

        groups = [{
            'entitas_bisnis_id': eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'coa_account_id': akun_persediaan.pk,
                'offset_coa_account_id': akun_modal.pk,
                'quantity': '10',
                'unit_price': '24000',
                'input_uom_id': kg.pk,
            }],
        }]
        resp = client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Bad',
            'eb_groups_data': json.dumps(groups),
        })
        # Form re-rendered (not redirect), nothing persisted.
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PurchaseItem.objects.filter(item=self.item).exists())

    def test_purchase_edit_prefill_and_resave_does_not_compound_uom(self):
        """Regression test: opening the edit form must prefill the original
        input-unit qty/price (not the already-converted base values), and
        resubmitting the form unchanged must NOT re-apply the UOM conversion
        on top of the already-converted base values."""
        role = Role.objects.create(kode='admin', nama='Admin UOM2')
        user = User.objects.create_user(email='uom2@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM2')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM2', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        stt = SubTransactionType.objects.create(
            nama='Stok Awal UOM2', direction='inflow', default_offset_account=akun_modal,
        )

        groups = [{
            'entitas_bisnis_id': eb.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'coa_account_id': akun_persediaan.pk,
                'offset_coa_account_id': akun_modal.pk,
                'quantity': '10',
                'unit_price': '24000',
                'input_uom_id': self.ctn.pk,
            }],
        }]
        resp = client.post(reverse('purchase:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Edit',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        purchase = PurchaseHeader.objects.get(deskripsi='Test UOM Edit')
        pi = PurchaseItem.objects.get(item=self.item, purchase_eb__purchase_header=purchase)
        self.assertEqual(pi.quantity, Decimal('240'))
        self.assertEqual(pi.unit_price, Decimal('1000'))

        # 1. GET the edit view and inspect the prefill data.
        edit_resp = client.get(reverse('purchase:update', args=[purchase.pk]))
        self.assertEqual(edit_resp.status_code, 200)
        eb_groups_data = json.loads(edit_resp.context['eb_groups_json'])
        prefill_item = eb_groups_data[0]['items'][0]
        self.assertEqual(Decimal(prefill_item['quantity']), Decimal('10'))
        self.assertEqual(Decimal(prefill_item['unit_price']), Decimal('24000'))
        self.assertEqual(str(prefill_item['input_uom_id']), str(self.ctn.pk))

        # 2. Resave the update view using exactly the prefilled values
        # unchanged (simulating a no-op resave), and verify the stored base
        # quantity/price are stable — not compounded (e.g. 5760 instead of 240).
        resave_groups = [{
            'entitas_bisnis_id': eb_groups_data[0]['entitas_bisnis_id'],
            'items': [{
                'item_id': prefill_item['item_id'],
                'sub_transaction_type_id': prefill_item['sub_transaction_type_id'],
                'coa_account_id': prefill_item['coa_account_id'],
                'offset_coa_account_id': prefill_item['offset_coa_account_id'],
                'quantity': prefill_item['quantity'],
                'unit_price': prefill_item['unit_price'],
                'input_uom_id': prefill_item['input_uom_id'],
            }],
        }]
        resave_resp = client.post(reverse('purchase:update', args=[purchase.pk]), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Edit',
            'eb_groups_data': json.dumps(resave_groups),
        })
        self.assertEqual(resave_resp.status_code, 302)
        pi = PurchaseItem.objects.get(item=self.item, purchase_eb__purchase_header=purchase)
        self.assertEqual(pi.quantity, Decimal('240'))
        self.assertEqual(pi.unit_price, Decimal('1000'))

        # 3. A second resave cycle must remain stable too (no progressive
        # compounding across multiple saves).
        edit_resp2 = client.get(reverse('purchase:update', args=[purchase.pk]))
        eb_groups_data2 = json.loads(edit_resp2.context['eb_groups_json'])
        prefill_item2 = eb_groups_data2[0]['items'][0]
        self.assertEqual(Decimal(prefill_item2['quantity']), Decimal('10'))
        self.assertEqual(Decimal(prefill_item2['unit_price']), Decimal('24000'))
        resave_groups2 = [{
            'entitas_bisnis_id': eb_groups_data2[0]['entitas_bisnis_id'],
            'items': [{
                'item_id': prefill_item2['item_id'],
                'sub_transaction_type_id': prefill_item2['sub_transaction_type_id'],
                'coa_account_id': prefill_item2['coa_account_id'],
                'offset_coa_account_id': prefill_item2['offset_coa_account_id'],
                'quantity': prefill_item2['quantity'],
                'unit_price': prefill_item2['unit_price'],
                'input_uom_id': prefill_item2['input_uom_id'],
            }],
        }]
        resave_resp2 = client.post(reverse('purchase:update', args=[purchase.pk]), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Edit',
            'eb_groups_data': json.dumps(resave_groups2),
        })
        self.assertEqual(resave_resp2.status_code, 302)
        pi = PurchaseItem.objects.get(item=self.item, purchase_eb__purchase_header=purchase)
        self.assertEqual(pi.quantity, Decimal('240'))
        self.assertEqual(pi.unit_price, Decimal('1000'))


class PurchaseCreateUomModalGroupingTests(TestCase):
    def setUp(self):
        role = Role.objects.create(kode='admin-puom', nama='Admin PUOM')
        self.user = User.objects.create_user(email='puom@test.com', password='pass1234', role=role)
        self.client.force_login(self.user)

    def test_purchase_create_get_includes_dimension_labels_for_modal_uom_js(self):
        resp = self.client.get(reverse('purchase:create'))
        content = resp.content.decode()
        self.assertEqual(resp.status_code, 200)
        # dimension_label must be present in the JSON fed to UOM_LIST so the
        # populateModalUomSelects() JS can build <optgroup> boundaries.
        self.assertIn('dimension_label', content)
        self.assertIn('Count / Jumlah', content)
