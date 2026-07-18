"""Tests: eb_hierarki dropdown + auto-fill akun untuk retur pelanggan & supplier."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import (
    TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
)
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import Warehouse
from apps.inventory.forms import ReturCustomerForm, ReturSupplierForm


class ReturEbHierarkiResolveTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(nama='Divisi A', entitas_bisnis=self.eb)
        self.lv3 = EntitasBisnisLv3.objects.create(nama='Sub A1', parent_lv2=self.lv2)
        self.wh = Warehouse.objects.create(entitas_bisnis=self.eb, nama='G1')
        self.lawan = Akun.objects.create(kode_akun='2.1.1', nama='Hutang Usaha')

    def _customer_data(self, eb_hierarki):
        return {
            'tanggal': '2026-07-18', 'eb_hierarki': eb_hierarki,
            'warehouse': self.wh.pk, 'keterangan': '',
        }

    def _supplier_data(self, eb_hierarki):
        return {
            'tanggal': '2026-07-18', 'eb_hierarki': eb_hierarki,
            'warehouse': self.wh.pk, 'akun_lawan': self.lawan.pk, 'keterangan': '',
        }

    def test_customer_lv3_resolves_all_three_fks(self):
        form = ReturCustomerForm(data=self._customer_data(f'lv3:{self.lv3.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv2'], self.lv2)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv3'], self.lv3)

    def test_customer_lv1_resolves_only_lv1(self):
        form = ReturCustomerForm(data=self._customer_data(f'lv1:{self.eb.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv2'])

    def test_supplier_lv2_resolves_lv1_and_lv2(self):
        form = ReturSupplierForm(data=self._supplier_data(f'lv2:{self.lv2.pk}'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['entitas_bisnis'], self.eb)
        self.assertEqual(form.cleaned_data['entitas_bisnis_lv2'], self.lv2)
        self.assertIsNone(form.cleaned_data['entitas_bisnis_lv3'])

    def test_customer_default_tanggal_is_today(self):
        from django.utils import timezone
        form = ReturCustomerForm()
        self.assertEqual(form.fields['tanggal'].initial, timezone.localdate())

    def test_supplier_default_tanggal_is_today(self):
        from django.utils import timezone
        form = ReturSupplierForm()
        self.assertEqual(form.fields['tanggal'].initial, timezone.localdate())


class ReturCustomerAkunPreviewTests(TestCase):
    """retur_ppn_preview harus ikut mengembalikan akun (pendapatan/piutang/HPP)
    dari sales_item agar UI bisa menampilkan akun mana yang dipakai per baris."""

    def setUp(self):
        from django.utils import timezone
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        from apps.purchase.models import SubTransactionType

        User = get_user_model()
        self.user = User.objects.create_user(email='rc@test.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.pendapatan = Akun.objects.create(kode_akun='4.1.1', nama='Pendapatan')
        self.piutang = Akun.objects.create(kode_akun='1.1.3', nama='Piutang')
        self.hpp = Akun.objects.create(kode_akun='5.1.1', nama='HPP')

        sh = SalesHeader.objects.create(transaction_id='SO-001', tanggal=timezone.now().date())
        seb = SalesEntitasBisnis.objects.create(sales_header=sh, entitas_bisnis=self.eb)
        stt, _ = SubTransactionType.objects.get_or_create(
            nama='Penjualan',
            defaults={'module': 'sales', 'direction': 'out',
                      'default_offset_account': self.hpp})
        self.si = SalesItem.objects.create(
            sales_eb=seb, item=self.item, sub_transaction_type=stt,
            quantity=Decimal('4'), selling_price=Decimal('10'),
            offset_coa_account=self.hpp, revenue_account=self.pendapatan,
            payment_account=self.piutang, cogs_amount=Decimal('20'))

    def test_preview_returns_row_accounts(self):
        resp = self.client.get('/inventory/api/retur-ppn-preview/',
                               {'sales_item': self.si.pk, 'qty': '2'})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['akun_pendapatan']['pk'], self.pendapatan.pk)
        self.assertIn('4.1.1', data['akun_pendapatan']['label'])
        self.assertEqual(data['akun_piutang']['pk'], self.piutang.pk)
        self.assertEqual(data['akun_hpp']['pk'], self.hpp.pk)


class ReturSupplierAkunPreviewTests(TestCase):
    """Endpoint auto-fill akun_lawan dari offset_coa_account faktur pembelian asal."""

    def setUp(self):
        from django.utils import timezone
        from apps.purchase.models import (
            PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, SubTransactionType,
        )

        User = get_user_model()
        self.user = User.objects.create_user(email='rs@test.com', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Kopi', tipe_item='RM')
        self.persediaan = Akun.objects.create(kode_akun='1.1.4', nama='Persediaan')
        self.hutang = Akun.objects.create(kode_akun='2.1.1', nama='Hutang Usaha')
        self.hutang_b = Akun.objects.create(kode_akun='2.1.2', nama='Hutang Lain')

        self.ph = PurchaseHeader.objects.create(
            transaction_id='PO-001', tanggal=timezone.now().date())
        peb = PurchaseEntitasBisnis.objects.create(
            purchase_header=self.ph, entitas_bisnis=self.eb)
        self.stt, _ = SubTransactionType.objects.get_or_create(
            nama='Pembelian',
            defaults={'module': 'purchase', 'direction': 'in',
                      'default_offset_account': self.hutang})
        self.peb = peb

    def _pitem(self, offset):
        from apps.purchase.models import PurchaseItem
        return PurchaseItem.objects.create(
            purchase_eb=self.peb, item=self.item, sub_transaction_type=self.stt,
            coa_account=self.persediaan, offset_coa_account=offset,
            quantity=Decimal('5'), unit_price=Decimal('10'))

    def test_uniform_offset_returns_akun_lawan(self):
        self._pitem(self.hutang)
        self._pitem(self.hutang)
        resp = self.client.get('/inventory/api/retur-supplier-akun/',
                               {'purchase_header': self.ph.pk})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['akun_lawan']['pk'], self.hutang.pk)
        self.assertIn('2.1.1', data['akun_lawan']['label'])

    def test_mixed_offset_returns_null(self):
        self._pitem(self.hutang)
        self._pitem(self.hutang_b)
        resp = self.client.get('/inventory/api/retur-supplier-akun/',
                               {'purchase_header': self.ph.pk})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertIsNone(data['akun_lawan'])
