"""Unit tests for the sales app."""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun, AsetLv1, AsetLv2, EkuitasLv1, EkuitasLv2, PendapatanLv1, PendapatanLv2
from apps.purchase.models import ItemMasterPurchase, SubTransactionType, FIFOBatch
from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesEventLog, SalesTaxLine
from .services import get_available_stock, consume_fifo


class SalesHeaderModelTests(TestCase):
    def test_str(self):
        h = SalesHeader.objects.create()
        self.assertTrue(h.transaction_id.startswith('TRX-SAL-'))
        self.assertEqual(str(h), h.transaction_id)

    def test_auto_transaction_id(self):
        h1 = SalesHeader.objects.create()
        h2 = SalesHeader.objects.create()
        self.assertEqual(h1.transaction_id, 'TRX-SAL-001')
        self.assertEqual(h2.transaction_id, 'TRX-SAL-002')


class SalesEntitasBisnisModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun = Akun.objects.create(kategori_id='aset', nama='Kas')
        self.header = SalesHeader.objects.create()

    def test_str(self):
        eb = SalesEntitasBisnis.objects.create(
            sales_header=self.header,
            entitas_bisnis=self.entitas,
            payment_account=self.akun,
        )
        self.assertIn('PT Test', str(eb))
        self.assertIn(self.header.transaction_id, str(eb))

    def test_cascade_delete(self):
        SalesEntitasBisnis.objects.create(
            sales_header=self.header,
            entitas_bisnis=self.entitas,
            payment_account=self.akun,
        )
        self.header.delete()
        self.assertEqual(SalesEntitasBisnis.objects.count(), 0)


class SalesItemModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas')
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP')
        self.akun_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Beras', tipe_item='RM', coa_account=self.akun_kas,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan FnB', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )
        self.header = SalesHeader.objects.create()
        self.eb_group = SalesEntitasBisnis.objects.create(
            sales_header=self.header,
            entitas_bisnis=self.entitas,
            payment_account=self.akun_kas,
        )

    def test_total_sales_computed(self):
        si = SalesItem.objects.create(
            sales_eb=self.eb_group,
            item=self.item,
            sub_transaction_type=self.stt,
            quantity=Decimal('10'),
            selling_price=Decimal('50000'),
            offset_coa_account=self.akun_hpp,
            revenue_account=self.akun_pendapatan,
        )
        self.assertEqual(si.total_sales, Decimal('500000'))

    def test_str(self):
        si = SalesItem.objects.create(
            sales_eb=self.eb_group,
            item=self.item,
            sub_transaction_type=self.stt,
            quantity=Decimal('5'),
            selling_price=Decimal('10000'),
            offset_coa_account=self.akun_hpp,
            revenue_account=self.akun_pendapatan,
        )
        self.assertIn('×', str(si))

    def test_cascade_delete(self):
        SalesItem.objects.create(
            sales_eb=self.eb_group,
            item=self.item,
            sub_transaction_type=self.stt,
            quantity=Decimal('1'),
            selling_price=Decimal('10000'),
            offset_coa_account=self.akun_hpp,
            revenue_account=self.akun_pendapatan,
        )
        self.header.delete()
        self.assertEqual(SalesItem.objects.count(), 0)


class StockAndFIFOTests(TestCase):
    def setUp(self):
        self.akun = Akun.objects.create(kategori_id='aset', nama='Persediaan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Beras', tipe_item='RM', coa_account=self.akun,
        )
        # Create FIFO batches
        FIFOBatch.objects.create(
            item=self.item, tanggal='2024-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )
        FIFOBatch.objects.create(
            item=self.item, tanggal='2024-02-01',
            quantity_in=Decimal('50'), unit_price=Decimal('12000'),
            remaining_qty=Decimal('50'),
        )

    def test_get_available_stock(self):
        stock = get_available_stock(self.item.pk)
        self.assertEqual(stock, Decimal('150'))

    def test_consume_fifo(self):
        cogs, consumed = consume_fifo(self.item.pk, Decimal('120'))
        expected_cogs = Decimal('100') * Decimal('10000') + Decimal('20') * Decimal('12000')
        self.assertEqual(cogs, expected_cogs)
        self.assertEqual(len(consumed), 2)
        self.assertEqual(get_available_stock(self.item.pk), Decimal('30'))

    def test_consume_fifo_insufficient_stock(self):
        with self.assertRaises(ValueError):
            consume_fifo(self.item.pk, Decimal('200'))


class SalesViewTests(TestCase):
    """View-level tests that cover the POST paths which failed in production."""

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

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        self.akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='3', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item = ItemMasterPurchase.objects.create(
            nama='Kopi', tipe_item='RM', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan Tunai', module='sales', direction='outflow',
            default_offset_account=self.akun_persediaan,
        )
        # Create FIFO stock so sales can proceed
        FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )

    def _eb_groups_payload(self, quantity='5', selling_price='20000'):
        """Return valid eb_groups_data JSON for a single group / single item."""
        groups = [{
            'eb_selection': f'lv1:{self.eb.pk}',
            'payment_account_id': self.akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'quantity': quantity,
                'selling_price': selling_price,
                'offset_coa_account_id': self.akun_persediaan.pk,
                'revenue_account_id': self.akun_pendapatan.pk,
                'payment_account_id': self.akun_modal.pk,
            }],
        }]
        return json.dumps(groups)

    def test_sales_list_get(self):
        resp = self.client.get(reverse('sales:list'))
        self.assertEqual(resp.status_code, 200)

    def test_sales_list_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('sales:list'))
        self.assertEqual(resp.status_code, 302)

    def test_sales_create_get(self):
        resp = self.client.get(reverse('sales:create'))
        self.assertEqual(resp.status_code, 200)

    def test_sales_create_post_creates_header_without_entitas_bisnis_on_header(self):
        """Bug 1 regression: SalesHeader must NOT have entitas_bisnis_id.
        The EB lives in SalesEntitasBisnis; the header itself has no such FK.
        """
        resp = self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test penjualan',
            'eb_groups_data': self._eb_groups_payload(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SalesHeader.objects.count(), 1)
        header = SalesHeader.objects.first()
        # Header must NOT have entitas_bisnis as a model field
        field_names = [f.name for f in header._meta.get_fields()]
        self.assertNotIn('entitas_bisnis', field_names)
        # EB group must be linked via SalesEntitasBisnis
        self.assertEqual(header.entitas_groups.count(), 1)
        eb_group = header.entitas_groups.first()
        self.assertEqual(eb_group.entitas_bisnis, self.eb)
        # Item must be linked via EB group
        self.assertEqual(eb_group.items.count(), 1)
        self.assertEqual(eb_group.items.first().item, self.item)

    def test_sales_create_post_missing_eb_returns_form(self):
        """Submitting without an EB group should re-render form with errors."""
        resp = self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test',
            'eb_groups_data': json.dumps([]),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SalesHeader.objects.count(), 0)

    def test_sales_detail_get(self):
        header = SalesHeader.objects.create()
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_sales_delete_post(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Hapus test',
            'eb_groups_data': self._eb_groups_payload(),
        })
        header = SalesHeader.objects.first()
        resp = self.client.post(reverse('sales:delete', args=[header.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SalesHeader.objects.exists())

    def test_sales_delete_locked_blocked(self):
        header = SalesHeader.objects.create(is_locked=True)
        resp = self.client.post(reverse('sales:delete', args=[header.pk]))
        # Should redirect but NOT delete
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SalesHeader.objects.filter(pk=header.pk).exists())


class SalesEventLogTests(TestCase):
    def setUp(self):
        self.header = SalesHeader.objects.create()

    def test_log_creation(self):
        log = SalesEventLog.objects.create(
            sales_header=self.header,
            event_type='CREATED',
            description='Test',
        )
        self.assertEqual(log.sales_header, self.header)
        self.assertEqual(log.event_type, 'CREATED')
        self.assertIsNone(log.actor)

    def test_logs_ordered_by_timestamp(self):
        SalesEventLog.objects.create(sales_header=self.header, event_type='CREATED')
        SalesEventLog.objects.create(sales_header=self.header, event_type='EDITED')
        logs = list(SalesEventLog.objects.filter(sales_header=self.header))
        self.assertEqual(logs[0].event_type, 'CREATED')
        self.assertEqual(logs[1].event_type, 'EDITED')

    def test_cascade_delete(self):
        SalesEventLog.objects.create(sales_header=self.header, event_type='CREATED')
        self.header.delete()
        self.assertEqual(SalesEventLog.objects.count(), 0)


class SalesHeaderCreatedByTests(TestCase):
    def test_created_by_nullable(self):
        h = SalesHeader.objects.create()
        self.assertIsNone(h.created_by)


from apps.piutang.models import PiutangHeader


class CreditSalesCreatesPiutangTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
        from apps.master_data.models import Akun
        from apps.purchase.models import ItemMasterPurchase, SubTransactionType

        tipe = TipeEntitas.objects.create(nama='Pelanggan')
        self.eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
        self.coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang', kode_akun='1.2.1')
        self.coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        self.coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        self.item = ItemMasterPurchase.objects.create(item_id='FG-001', nama='Produk A', tipe_item='FG')
        self.stt = SubTransactionType.objects.create(
            nama='Kredit', module='sales', direction='outflow',
            default_offset_account=self.coa_revenue,
        )

    def _make_credit_sales_header(self):
        from apps.sales.models import SalesHeader, SalesEntitasBisnis, SalesItem
        header = SalesHeader.objects.create(payment_type='credit')
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
            payment_account=self.coa_piutang,
        )
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('500000'),
            offset_coa_account=self.coa_kas, revenue_account=self.coa_revenue,
            payment_account=self.coa_piutang,
        )
        return header

    def test_creates_piutang_header(self):
        from apps.piutang.services import create_piutang_from_sales
        header = self._make_credit_sales_header()
        piutang = create_piutang_from_sales(header)
        self.assertIsNotNone(piutang.pk)
        self.assertEqual(piutang.source_type, 'from_sales')
        self.assertEqual(piutang.source_sales, header)
        self.assertEqual(piutang.status, 'open')

    def test_jumlah_pokok_equals_total_credit_items(self):
        from apps.piutang.services import create_piutang_from_sales
        header = self._make_credit_sales_header()
        piutang = create_piutang_from_sales(header)
        self.assertEqual(piutang.jumlah_pokok, Decimal('500000'))


class SalesTaxLineModelTests(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='Retail')
        eb = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=tipe)
        akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP', kode_akun='5.1.1')
        akun_rev = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4')
        item = ItemMasterPurchase.objects.create(nama='Barang A', tipe_item='FG', coa_account=akun_kas)
        stt = SubTransactionType.objects.create(
            nama='Penjualan', module='sales', direction='outflow',
            default_offset_account=akun_hpp,
        )
        header = SalesHeader.objects.create()
        eb_group = SalesEntitasBisnis.objects.create(sales_header=header, entitas_bisnis=eb)
        self.si = SalesItem.objects.create(
            sales_eb=eb_group, item=item, sub_transaction_type=stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=akun_hpp, revenue_account=akun_rev,
        )
        self.akun_ppn = akun_ppn
        self.akun_lawan = akun_lawan

    def test_salestaxline_creation(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertEqual(tl.sales_item, self.si)
        self.assertEqual(tl.tax_type, 'ppn_keluaran')
        self.assertFalse(tl.is_manual)
        self.assertIsNone(tl.tax)

    def test_salestaxline_str(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='pph_23',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertIn('pph_23', str(tl))

    def test_salestaxline_cascade_delete(self):
        SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.si.delete()
        self.assertEqual(SalesTaxLine.objects.count(), 0)

    def test_salestaxline_is_manual(self):
        tl = SalesTaxLine.objects.create(
            sales_item=self.si,
            tax_type='ppn_keluaran',
            tax=Decimal('11000'),
            is_manual=True,
            tax_account=self.akun_ppn,
            tax_payment_account=self.akun_lawan,
        )
        self.assertTrue(tl.is_manual)
        self.assertEqual(tl.tax, Decimal('11000'))
