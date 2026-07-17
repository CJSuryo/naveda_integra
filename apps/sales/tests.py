"""Unit tests for the sales app."""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun, AsetLv1, AsetLv2, EkuitasLv1, EkuitasLv2, PendapatanLv1, PendapatanLv2
from apps.purchase.models import ItemMasterPurchase, SubTransactionType, FIFOBatch
from apps.uom.conversion import convert_input_to_base
from apps.uom.models import UnitOfMeasure, ItemUOM
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


from datetime import date as dt_date
from apps.pajak.models import PajakTransaksi, TarifPajak
from .services import create_sales_automated_journals, _cancel_sales_pajak


def _seed_tarif(jenis_pajak, tarif_persen, faktor_dpp='1.000000'):
    TarifPajak.objects.get_or_create(
        jenis_pajak=jenis_pajak,
        berlaku_mulai=dt_date(2025, 1, 1),
        defaults={
            'nama': jenis_pajak,
            'tarif_persen': Decimal(str(tarif_persen)),
            'faktor_dpp': Decimal(faktor_dpp),
        },
    )


class SalesTaxLineServiceTests(TestCase):
    def setUp(self):
        _seed_tarif('ppn_umum', '12.0000', '0.916667')
        _seed_tarif('pph_23_jasa', '2.0000')

        tipe = TipeEntitas.objects.create(nama='Retail')
        self.eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe)
        self.akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP', kode_akun='5.1.1')
        self.akun_rev = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan', kode_akun='4.1.1')
        self.akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3')
        self.akun_pph = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4')
        self.item = ItemMasterPurchase.objects.create(
            nama='Barang A', tipe_item='FG', coa_account=self.akun_kas,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )

    def _make_sales_with_tax_line(self, tax_type='ppn_keluaran', tax=None, is_manual=False):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type=tax_type, tax=tax, is_manual=is_manual,
            tax_account=self.akun_ppn, tax_payment_account=self.akun_pph,
        )
        return header, si

    def test_pajak_transaksi_created_on_journal(self):
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.filter(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pt.count(), 1)
        self.assertEqual(pt.first().jenis_pajak, 'ppn_umum')
        self.assertEqual(pt.first().sifat_pajak, 'potong_pungut')
        self.assertEqual(pt.first().status, 'final')

    def test_no_inline_tax_in_main_journal(self):
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        created = create_sales_automated_journals(header)
        main_journal = created[0]
        self.assertFalse(main_journal.nomor_transaksi.startswith('TRX-PAJ'))
        detail_akun_ids = set(main_journal.details.values_list('akun_id', flat=True))
        self.assertNotIn(self.akun_ppn.pk, detail_akun_ids)

    def test_multiple_tax_lines_create_multiple_pajak_transaksi(self):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type='ppn_keluaran',
            tax_account=self.akun_ppn, tax_payment_account=self.akun_pph,
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type='pph_23',
            tax_account=self.akun_pph, tax_payment_account=self.akun_kas,
        )
        create_sales_automated_journals(header)
        pts = PajakTransaksi.objects.filter(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pts.count(), 2)
        jenis = set(pts.values_list('jenis_pajak', flat=True))
        self.assertIn('ppn_umum', jenis)
        self.assertIn('pph_23_jasa', jenis)

    def test_is_manual_override(self):
        header, si = self._make_sales_with_tax_line(
            tax_type='ppn_keluaran', tax=Decimal('5000'), is_manual=True,
        )
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.get(source_type='sales_item', source_id=si.pk)
        self.assertTrue(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('5000'))

    def test_cancel_sales_pajak_sets_dibatalkan(self):
        header, si = self._make_sales_with_tax_line(tax_type='ppn_keluaran')
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.get(source_type='sales_item', source_id=si.pk)
        self.assertEqual(pt.status, 'final')

        _cancel_sales_pajak(header)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')

    def test_sales_item_without_tax_lines_no_pajak_transaksi(self):
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
        )
        create_sales_automated_journals(header)
        self.assertEqual(PajakTransaksi.objects.count(), 0)

    def test_non_manual_tax_line_ignores_si_tax_field(self):
        """Deprecated si.tax must not override tarif computation when is_manual=False."""
        header = SalesHeader.objects.create(tanggal=dt_date(2026, 1, 15))
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
        )
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('1'), selling_price=Decimal('100000'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            payment_account=self.akun_kas,
            tax=Decimal('99999'),  # stale inline tax — must be ignored
        )
        SalesTaxLine.objects.create(
            sales_item=si, tax_type='ppn_keluaran', is_manual=False,
            tax_account=self.akun_ppn, tax_payment_account=self.akun_pph,
        )
        create_sales_automated_journals(header)
        pt = PajakTransaksi.objects.get(source_type='sales_item', source_id=si.pk)
        # Must NOT be overridden — should be computed from TarifPajak, not si.tax
        self.assertFalse(pt.is_overridden)
        self.assertNotEqual(pt.jumlah_pajak, Decimal('99999'))


class SalesTaxLineViewTests(TestCase):
    def setUp(self):
        _seed_tarif('ppn_umum', '12.0000', '0.916667')

        self.role = Role.objects.create(kode='admin', nama='Admin')
        self.user = User.objects.create_user(email='view@test.com', password='pass1234', role=self.role)
        self.client = Client()
        self.client.force_login(self.user)

        tipe = TipeEntitas.objects.create(nama='FnB2')
        self.eb = EntitasBisnis.objects.create(nama='Cafe XYZ', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1a', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1a', nama='Persediaan')
        self.akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4a', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1a', nama='Pendapatan Usaha')
        self.akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='3a', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1a', nama='Modal')
        self.akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.akun_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.3.v')
        self.akun_lawan = Akun.objects.create(kategori_id='aset', nama='Uang Muka PPh', kode_akun='1.1.4.v')

        self.item = ItemMasterPurchase.objects.create(
            nama='Produk X', tipe_item='FG', coa_account=self.akun_persediaan,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan View', module='sales', direction='outflow',
            default_offset_account=self.akun_persediaan,
        )
        FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )
        # Also seed the authoritative stock ledger (apps.inventory.ledger) —
        # process_sales_fifo consumes via StockMovement layers, not the
        # legacy FIFOBatch directly, since commit c646c61.
        from apps.inventory.ledger import record_inflow
        record_inflow(self.item, self.eb, None, None, Decimal('100'),
                      Decimal('10000'), '2026-01-01', 'purchase_in')

    def _payload_with_tax_lines(self, tax_type='ppn_keluaran'):
        groups = [{
            'eb_selection': f'lv1:{self.eb.pk}',
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': self.stt.pk,
                'quantity': '5',
                'selling_price': '20000',
                'offset_coa_account_id': self.akun_persediaan.pk,
                'revenue_account_id': self.akun_pendapatan.pk,
                'payment_account_id': self.akun_modal.pk,
                'tax_lines': [{
                    'tax_type': tax_type,
                    'tax': '',
                    'is_manual': False,
                    'tax_account_id': self.akun_ppn.pk,
                    'tax_payment_account_id': self.akun_lawan.pk,
                }],
            }],
        }]
        return json.dumps(groups)

    def test_create_sales_with_tax_lines_creates_salestaxline(self):
        resp = self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(SalesTaxLine.objects.count(), 1)
        tl = SalesTaxLine.objects.first()
        self.assertEqual(tl.tax_type, 'ppn_keluaran')
        self.assertFalse(tl.is_manual)

    def test_create_sales_with_tax_lines_creates_pajak_transaksi(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        pts = PajakTransaksi.objects.filter(source_type='sales_item')
        self.assertEqual(pts.count(), 1)
        self.assertEqual(pts.first().status, 'final')

    def test_delete_sales_cancels_pajak_transaksi(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Penjualan dengan pajak',
            'eb_groups_data': self._payload_with_tax_lines(),
        })
        header = SalesHeader.objects.first()
        pt = PajakTransaksi.objects.filter(source_type='sales_item').first()
        self.assertEqual(pt.status, 'final')

        self.client.post(reverse('sales:delete', args=[header.pk]))
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')


class SalesFormItemRowLayoutTests(TestCase):
    """The per-line Satuan selector must sit next to Qty, matching the
    purchase form layout — not off at the far end of the row where it's
    easy to miss."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='layout@test.com', password='pass1234', name='Layout User')
        self.client.force_login(self.user)

    def test_satuan_column_sits_between_qty_and_harga_jual(self):
        resp = self.client.get(reverse('sales:create'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()

        qty_th = body.index('>Qty<')
        satuan_th = body.index('>Satuan<')
        harga_th = body.index('>Harga Jual<')
        self.assertTrue(qty_th < satuan_th < harga_th)

        qty_td = body.index('data-label="Qty"')
        satuan_td = body.index('data-label="Satuan"')
        harga_td = body.index('data-label="Harga Jual"')
        self.assertTrue(qty_td < satuan_td < harga_td)


class SalesInvoicePaymentLabelTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='inv@test.com', password='pass', name='Invoice User')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_kas = Akun.objects.create(kategori_id='aset', nama='Kas', is_kas_setara=True)
        self.akun_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang', is_kas_setara=False)
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP')
        self.akun_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Beras', tipe_item='RM', coa_account=self.akun_kas,
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan FnB', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )
        self.header = SalesHeader.objects.create(payment_type='cash')
        self.eb_group = SalesEntitasBisnis.objects.create(
            sales_header=self.header,
            entitas_bisnis=self.entitas,
        )

    def _make_item(self, payment_account):
        return SalesItem.objects.create(
            sales_eb=self.eb_group,
            item=self.item,
            sub_transaction_type=self.stt,
            quantity=Decimal('10'),
            selling_price=Decimal('50000'),
            offset_coa_account=self.akun_hpp,
            revenue_account=self.akun_pendapatan,
            payment_account=payment_account,
        )

    def test_all_cash_items_label_kas(self):
        self._make_item(self.akun_kas)
        self._make_item(self.akun_kas)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Kas')
        self.assertNotContains(resp, 'Kas dan Kredit')

    def test_mixed_items_label_kas_dan_kredit(self):
        self._make_item(self.akun_kas)
        self._make_item(self.akun_piutang)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Kas dan Kredit')

    def test_cash_header_shows_lunas(self):
        self._make_item(self.akun_kas)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')

    def test_credit_header_without_piutang_shows_belum_lunas(self):
        self.header.payment_type = 'credit'
        self.header.save()
        self._make_item(self.akun_piutang)
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Belum Lunas')

    def test_credit_header_with_paid_piutang_shows_lunas(self):
        from apps.piutang.models import PiutangHeader
        self.header.payment_type = 'credit'
        self.header.save()
        self._make_item(self.akun_piutang)
        PiutangHeader.objects.create(
            nomor_piutang='PTG-TEST-001',
            source_type='from_sales',
            source_sales=self.header,
            coa_piutang_account=self.akun_piutang,
            jumlah_pokok=Decimal('500000'),
            jumlah_terbayar=Decimal('500000'),
            status='paid',
        )
        resp = self.client.get(reverse('sales:invoice', args=[self.header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')


class SalesDetailJournalHistoryTests(TestCase):
    def setUp(self):
        # kode must be 'admin' (Role.ADMIN) — User.is_admin checks
        # role.kode == Role.ADMIN, which _resolve_eb_selection relies on to
        # grant unrestricted entitas-bisnis access. A non-admin role with no
        # UserEntitasBisnis link makes eb resolution fail and sales:create
        # silently no-op (form re-render with validation errors).
        self.role = Role.objects.create(kode='admin', nama='Admin2')
        self.user = User.objects.create_user(email='jrn@test.com', password='pass1234', role=self.role)
        self.client = Client()
        self.client.force_login(self.user)

        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Cafe Jurnal', tipe_entitas=self.tipe)

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
        FIFOBatch.objects.create(
            item=self.item, tanggal='2026-01-01',
            quantity_in=Decimal('100'), unit_price=Decimal('10000'),
            remaining_qty=Decimal('100'),
        )
        # Also seed the authoritative stock ledger (apps.inventory.ledger) —
        # process_sales_fifo consumes via StockMovement layers, not the
        # legacy FIFOBatch directly, since commit c646c61.
        from apps.inventory.ledger import record_inflow
        record_inflow(self.item, self.eb, None, None, Decimal('100'),
                      Decimal('10000'), '2026-01-01', 'purchase_in')

    def _eb_groups_payload(self, quantity='5', selling_price='20000'):
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

    def test_detail_page_shows_created_journal(self):
        from apps.jurnal.models import JurnalHeader
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test jurnal di detail',
            'eb_groups_data': self._eb_groups_payload(),
        })
        header = SalesHeader.objects.first()
        journal = JurnalHeader.objects.get(
            uraian_transaksi__startswith=f'Penjualan {header.transaction_id} —',
        )
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(journal, resp.context['journals'])
        self.assertContains(resp, journal.nomor_transaksi)

    def test_detail_page_journal_shows_debit_credit_lines(self):
        self.client.post(reverse('sales:create'), {
            'tanggal': '2026-04-16',
            'deskripsi': 'Test debit kredit',
            'eb_groups_data': self._eb_groups_payload(),
        })
        header = SalesHeader.objects.first()
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertContains(resp, self.akun_pendapatan.nama)

    def test_detail_page_with_no_journals_shows_empty_state(self):
        header = SalesHeader.objects.create()
        resp = self.client.get(reverse('sales:detail', args=[header.pk]))
        self.assertEqual(resp.context['journals'], [])
        self.assertContains(resp, 'Belum ada jurnal')


class SalesEBIsolationTests(TestCase):
    def setUp(self):
        from apps.entitas_bisnis.models import (
            TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
        )
        from apps.purchase.models import ItemMasterPurchase, SubTransactionType
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Div')
        self.lv3a = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet A')
        self.lv3b = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Outlet B')
        self.akun_hpp = Akun.objects.create(kategori_id='beban', nama='HPP EB')
        self.akun_rev = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan EB')
        self.item = ItemMasterPurchase.objects.create(
            nama='Gula', tipe_item='RM', coa_account=None)
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan EB Isolasi', module='sales', direction='outflow',
            default_offset_account=self.akun_hpp,
        )

    def _sales_with_item(self, lv2, lv3, qty):
        header = SalesHeader.objects.create(tanggal='2026-01-03')
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
            entitas_bisnis_lv2=lv2, entitas_bisnis_lv3=lv3)
        SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal(qty), selling_price=Decimal('10'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev)
        return header

    def test_sale_does_not_consume_sibling_stock(self):
        from apps.inventory.ledger import record_inflow, get_available_stock
        from apps.sales.services import process_sales_fifo
        # stok hanya di Outlet B
        record_inflow(self.item, self.eb, self.lv2, self.lv3b, Decimal('10'),
                      Decimal('5'), '2026-01-01', 'purchase_in')
        header = self._sales_with_item(self.lv2, self.lv3a, '1')
        with self.assertRaises(Exception):
            process_sales_fifo(header)
        self.assertEqual(
            get_available_stock(self.item, self.eb, self.lv2, self.lv3b),
            Decimal('10'))

    def test_happy_path_multi_batch_fifo_consumption(self):
        """Same-EB sale spanning two inflow batches computes correct FIFO cogs
        and rebuilds SalesItemFIFOAllocation rows."""
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import InventoryRecord
        from apps.sales.services import process_sales_fifo

        # Two inflow batches at the same EB (lv1/lv2/lv3a), different unit costs.
        # Each is linked to a legacy InventoryRecord so allocations get built.
        rec1 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, entitas_bisnis_lv2=self.lv2,
            entitas_bisnis_lv3=self.lv3a, quantity=Decimal('10'),
            unit_price=Decimal('5'), tanggal='2026-01-01')
        record_inflow(self.item, self.eb, self.lv2, self.lv3a, Decimal('10'),
                      Decimal('5'), '2026-01-01', 'purchase_in',
                      legacy_inventory_record=rec1)
        rec2 = InventoryRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, entitas_bisnis_lv2=self.lv2,
            entitas_bisnis_lv3=self.lv3a, quantity=Decimal('10'),
            unit_price=Decimal('8'), tanggal='2026-01-02')
        record_inflow(self.item, self.eb, self.lv2, self.lv3a, Decimal('10'),
                      Decimal('8'), '2026-01-02', 'purchase_in',
                      legacy_inventory_record=rec2)

        header = self._sales_with_item(self.lv2, self.lv3a, '12')
        reports = process_sales_fifo(header)

        self.assertEqual(len(reports), 1)
        self.assertFalse(reports[0].used_fallback)

        si = header.entitas_groups.get().items.get()
        # 10 units @5 + 2 units @8 = 66
        self.assertEqual(si.cogs_amount, Decimal('66'))

        allocations = list(si.fifo_allocations.all())
        self.assertEqual(len(allocations), 2)
        total_qty = sum(a.quantity_consumed for a in allocations)
        total_cogs = sum(a.cogs_amount for a in allocations)
        self.assertEqual(total_qty, Decimal('12'))
        self.assertEqual(total_cogs, Decimal('66'))

    def test_sale_consumes_only_selected_warehouse(self):
        """When a SalesItem specifies a warehouse, process_sales_fifo must lock
        consumption to that warehouse's layers only, even if a cheaper/older
        layer sits in a sibling warehouse of the same EB."""
        from apps.inventory.models import Warehouse, StockMovement
        from apps.inventory.ledger import record_inflow
        from apps.sales.services import process_sales_fifo

        wh_a = Warehouse.objects.create(entitas_bisnis=self.eb, kode='SA', nama='SGudang A')
        wh_b = Warehouse.objects.create(entitas_bisnis=self.eb, kode='SB', nama='SGudang B')
        record_inflow(self.item, self.eb, self.lv2, self.lv3a, Decimal('10'), Decimal('100'),
                      '2026-01-01', 'purchase_in', warehouse=wh_a)
        record_inflow(self.item, self.eb, self.lv2, self.lv3a, Decimal('10'), Decimal('999'),
                      '2026-01-01', 'purchase_in', warehouse=wh_b)

        header = SalesHeader.objects.create(tanggal='2026-01-03')
        eb_group = SalesEntitasBisnis.objects.create(
            sales_header=header, entitas_bisnis=self.eb,
            entitas_bisnis_lv2=self.lv2, entitas_bisnis_lv3=self.lv3a)
        si = SalesItem.objects.create(
            sales_eb=eb_group, item=self.item, sub_transaction_type=self.stt,
            quantity=Decimal('6'), selling_price=Decimal('10'),
            offset_coa_account=self.akun_hpp, revenue_account=self.akun_rev,
            warehouse=wh_a)

        process_sales_fifo(header)
        si.refresh_from_db()
        # Must only draw from wh_a's layer (unit cost 100), never touching wh_b.
        self.assertEqual(si.cogs_amount, Decimal('600'))

        out = StockMovement.objects.get(
            source_object_id=si.pk, source_content_type__model='salesitem')
        self.assertEqual(out.warehouse_id, wh_a.pk)


class SalesUomConversionTests(TestCase):
    """Konversi UOM diterapkan lewat helper; FIFO/ledger tetap dalam base."""

    def setUp(self):
        self.pcs = UnitOfMeasure.objects.get(kode='pcs')
        self.item = ItemMasterPurchase.objects.create(
            nama='Jual', tipe_item='FG', stock_uom=self.pcs)
        self.box = UnitOfMeasure.objects.create(
            kode='box-s', nama='Box', dimension='count', factor_to_base=None)
        ItemUOM.objects.create(item=self.item, uom=self.box, qty_in_stock_uom=Decimal('12'))

    def test_helper_box_sale(self):
        qty, price = convert_input_to_base(self.item, self.box, Decimal('3'), Decimal('120000'))
        self.assertEqual(qty, Decimal('36'))     # 3 * 12
        self.assertEqual(price, Decimal('10000'))  # 360.000 / 36

    def test_sales_create_post_converts_box_to_base(self):
        """POSTing a non-bulk item with input_uom_id in boxes must be converted
        to base units (pcs) — and selling_price re-based per pcs — before
        being saved to SalesItem, exercising the real create view path."""
        role = Role.objects.create(kode='admin', nama='Admin UOM Sales')
        user = User.objects.create_user(email='uom-sales@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item.coa_account = akun_persediaan
        self.item.save()

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        # Stock in base units (pcs) on the ledger — enough to cover 3 boxes * 12 = 36 pcs.
        from apps.inventory.ledger import record_inflow
        record_inflow(
            self.item, eb, None, None, Decimal('100'), Decimal('5000'),
            '2026-01-01', 'purchase_in',
        )

        groups = [{
            'eb_selection': f'lv1:{eb.pk}',
            'payment_account_id': akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'quantity': '3',
                'selling_price': '120000',
                'offset_coa_account_id': akun_persediaan.pk,
                'revenue_account_id': akun_pendapatan.pk,
                'payment_account_id': akun_modal.pk,
                'input_uom_id': self.box.pk,
            }],
        }]
        resp = client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        si = SalesItem.objects.get(item=self.item)
        self.assertEqual(si.quantity, Decimal('36'))
        self.assertEqual(si.selling_price, Decimal('10000'))
        self.assertEqual(si.input_uom, self.box)
        self.assertEqual(si.input_qty, Decimal('3'))

    def test_sales_create_rejects_unresolvable_input_uom(self):
        """An input_uom with no conversion path for the item (different
        dimension, no ItemUOM) must be rejected with a form error, not raise an
        uncaught ConversionError mid-transaction."""
        kg = UnitOfMeasure.objects.get(kode='kg')  # weight; item stock is pcs (count)
        role = Role.objects.create(kode='admin', nama='Admin UOM Sales Bad2')
        user = User.objects.create_user(email='uom-sales-bad2@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales Bad2')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales Bad2', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item.coa_account = akun_persediaan
        self.item.save()

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM Bad2', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        from apps.inventory.ledger import record_inflow
        record_inflow(
            self.item, eb, None, None, Decimal('100'), Decimal('5000'),
            '2026-01-01', 'purchase_in',
        )

        groups = [{
            'eb_selection': f'lv1:{eb.pk}',
            'payment_account_id': akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'quantity': '3',
                'selling_price': '120000',
                'offset_coa_account_id': akun_persediaan.pk,
                'revenue_account_id': akun_pendapatan.pk,
                'payment_account_id': akun_modal.pk,
                'input_uom_id': kg.pk,
            }],
        }]
        resp = client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Bad2',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SalesItem.objects.filter(item=self.item).exists())

    def test_sales_edit_prefill_and_resave_does_not_compound_uom(self):
        """Regression test: opening the edit form must prefill the original
        input-unit qty/price (not the already-converted base values), and
        resubmitting the form unchanged must NOT re-apply the UOM conversion
        on top of the already-converted base values."""
        role = Role.objects.create(kode='admin', nama='Admin UOM Sales Edit')
        user = User.objects.create_user(email='uom-sales-edit@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales Edit')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales Edit', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item.coa_account = akun_persediaan
        self.item.save()

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM Edit', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        # Stock in base units (pcs) on the ledger — enough to cover 3 boxes * 12 = 36 pcs,
        # plus headroom for the resave cycles (FIFO allocation happens on every resave
        # since items are deleted and recreated).
        from apps.inventory.ledger import record_inflow
        record_inflow(
            self.item, eb, None, None, Decimal('1000'), Decimal('5000'),
            '2026-01-01', 'purchase_in',
        )

        def make_groups(qty, price, input_uom_id):
            return [{
                'eb_selection': f'lv1:{eb.pk}',
                'payment_account_id': akun_modal.pk,
                'items': [{
                    'item_id': self.item.pk,
                    'sub_transaction_type_id': stt.pk,
                    'quantity': qty,
                    'selling_price': price,
                    'offset_coa_account_id': akun_persediaan.pk,
                    'revenue_account_id': akun_pendapatan.pk,
                    'payment_account_id': akun_modal.pk,
                    'input_uom_id': input_uom_id,
                }],
            }]

        resp = client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Edit',
            'eb_groups_data': json.dumps(make_groups('3', '120000', self.box.pk)),
        })
        self.assertEqual(resp.status_code, 302)
        sales = SalesHeader.objects.get(deskripsi='Test UOM Sales Edit')
        si = SalesItem.objects.get(item=self.item, sales_eb__sales_header=sales)
        self.assertEqual(si.quantity, Decimal('36'))
        self.assertEqual(si.selling_price, Decimal('10000'))

        # 1. GET the edit view and inspect the prefill data.
        edit_resp = client.get(reverse('sales:update', args=[sales.pk]))
        self.assertEqual(edit_resp.status_code, 200)
        eb_groups_data = json.loads(edit_resp.context['eb_groups_json'])
        prefill_item = eb_groups_data[0]['items'][0]
        self.assertEqual(Decimal(prefill_item['quantity']), Decimal('3'))
        self.assertEqual(Decimal(prefill_item['selling_price']), Decimal('120000'))
        self.assertEqual(str(prefill_item['input_uom_id']), str(self.box.pk))

        # 2. Resave using exactly the prefilled values unchanged (no-op resave) —
        # verify the stored base quantity/price are stable, not compounded
        # (e.g. 432 instead of 36).
        resave_resp = client.post(reverse('sales:update', args=[sales.pk]), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Edit',
            'eb_groups_data': json.dumps(make_groups(
                prefill_item['quantity'], prefill_item['selling_price'], prefill_item['input_uom_id'],
            )),
        })
        self.assertEqual(resave_resp.status_code, 302)
        si = SalesItem.objects.get(item=self.item, sales_eb__sales_header=sales)
        self.assertEqual(si.quantity, Decimal('36'))
        self.assertEqual(si.selling_price, Decimal('10000'))

        # 3. A second resave cycle must remain stable too (no progressive
        # compounding across multiple saves).
        edit_resp2 = client.get(reverse('sales:update', args=[sales.pk]))
        eb_groups_data2 = json.loads(edit_resp2.context['eb_groups_json'])
        prefill_item2 = eb_groups_data2[0]['items'][0]
        self.assertEqual(Decimal(prefill_item2['quantity']), Decimal('3'))
        self.assertEqual(Decimal(prefill_item2['selling_price']), Decimal('120000'))
        resave_resp2 = client.post(reverse('sales:update', args=[sales.pk]), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Edit',
            'eb_groups_data': json.dumps(make_groups(
                prefill_item2['quantity'], prefill_item2['selling_price'], prefill_item2['input_uom_id'],
            )),
        })
        self.assertEqual(resave_resp2.status_code, 302)
        si = SalesItem.objects.get(item=self.item, sales_eb__sales_header=sales)
        self.assertEqual(si.quantity, Decimal('36'))
        self.assertEqual(si.selling_price, Decimal('10000'))

    def test_sales_create_post_invalid_input_uom_id_rejected(self):
        """A truthy-but-nonexistent input_uom_id must not silently fall through
        to unconverted passthrough treatment — it must be rejected."""
        role = Role.objects.create(kode='admin', nama='Admin UOM Sales Bad')
        user = User.objects.create_user(email='uom-sales-bad@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales Bad')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales Bad', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item.coa_account = akun_persediaan
        self.item.save()

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM Bad', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        from apps.inventory.ledger import record_inflow
        record_inflow(
            self.item, eb, None, None, Decimal('100'), Decimal('5000'),
            '2026-01-01', 'purchase_in',
        )

        groups = [{
            'eb_selection': f'lv1:{eb.pk}',
            'payment_account_id': akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'quantity': '3',
                'selling_price': '120000',
                'offset_coa_account_id': akun_persediaan.pk,
                'revenue_account_id': akun_pendapatan.pk,
                'payment_account_id': akun_modal.pk,
                'input_uom_id': 999999,
            }],
        }]
        with self.assertRaises(ValueError):
            client.post(reverse('sales:create'), {
                'tanggal': '2026-01-15',
                'deskripsi': 'Test UOM Sales Bad',
                'eb_groups_data': json.dumps(groups),
            })
        self.assertFalse(SalesItem.objects.filter(item=self.item).exists())

    def test_sales_create_post_bulk_item_ignores_submitted_input_uom(self):
        """Bulk items (value-based tracking) must never persist input_uom,
        even if a client submits one alongside is_bulk='1' — the backend
        must null it out regardless of what was posted."""
        from apps.inventory.ledger import record_inflow
        from apps.inventory.models import InventoryRecord

        role = Role.objects.create(kode='admin', nama='Admin UOM Sales Bulk')
        user = User.objects.create_user(email='uom-sales-bulk@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales Bulk')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales Bulk', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        bulk_item = ItemMasterPurchase.objects.create(
            nama='Jual Bulk', tipe_item='FGB', coa_account=akun_persediaan)

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM Bulk', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        # Bulk stock is value-based: qty=1, unit_cost=total_value on the ledger
        # (consumed by process_sales_fifo), plus a legacy InventoryRecord (used
        # by the pre-transaction bulk-value validation in _handle_sales_save).
        record_inflow(
            bulk_item, eb, None, None, Decimal('1'), Decimal('500000'),
            '2026-01-01', 'purchase_in',
        )
        InventoryRecord.objects.create(
            item=bulk_item, entitas_bisnis=eb, quantity=Decimal('1'),
            unit_price=Decimal('500000'), tanggal='2026-01-01')

        groups = [{
            'eb_selection': f'lv1:{eb.pk}',
            'payment_account_id': akun_modal.pk,
            'items': [{
                'item_id': bulk_item.pk,
                'sub_transaction_type_id': stt.pk,
                'is_bulk': '1',
                'hpp_terpakai': '100000',
                'selling_price': '150000',
                'offset_coa_account_id': akun_persediaan.pk,
                'revenue_account_id': akun_pendapatan.pk,
                'payment_account_id': akun_modal.pk,
                # A buggy/malicious client still sends a real input_uom_id
                # even though this row is bulk — the backend must ignore it.
                'input_uom_id': self.box.pk,
            }],
        }]
        resp = client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Bulk',
            'eb_groups_data': json.dumps(groups),
        })
        self.assertEqual(resp.status_code, 302)
        si = SalesItem.objects.get(item=bulk_item)
        self.assertIsNone(si.input_uom)
        self.assertIsNone(si.input_qty)
        self.assertEqual(si.quantity, Decimal('0'))

    def test_sales_create_post_stock_prevalidation_uses_converted_qty(self):
        """The pre-transaction stock-demand validation loop must convert the
        input-unit qty to base units before comparing against available
        stock — otherwise it under-counts demand for any UOM-converted row.

        3 boxes * 12 pcs/box = 36 pcs demand. Available stock is 20 pcs:
        more than the raw (unconverted) "demand" of 3, but less than the
        true converted demand of 36. Only a unit-aware check catches this.
        """
        role = Role.objects.create(kode='admin', nama='Admin UOM Sales Prevalid')
        user = User.objects.create_user(email='uom-sales-prevalid@test.com', password='pass1234', role=role)
        client = Client()
        client.force_login(user)

        tipe = TipeEntitas.objects.create(nama='FnB UOM Sales Prevalid')
        eb = EntitasBisnis.objects.create(nama='Cafe UOM Sales Prevalid', tipe_entitas=tipe)

        aset_lv1 = AsetLv1.objects.create(kode='1', nama='Aset')
        aset_lv2 = AsetLv2.objects.create(aset=aset_lv1, kode='1', nama='Persediaan')
        akun_persediaan = Akun.objects.get(kategori_id='aset', kategori_akun=aset_lv2.pk)

        pendapatan_lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        pendapatan_lv2 = PendapatanLv2.objects.create(pendapatan=pendapatan_lv1, kode='1', nama='Pendapatan Usaha')
        akun_pendapatan = Akun.objects.get(kategori_id='pendapatan', kategori_akun=pendapatan_lv2.pk)

        ekuitas_lv1 = EkuitasLv1.objects.create(kode='1', nama='Ekuitas')
        ekuitas_lv2 = EkuitasLv2.objects.create(ekuitas=ekuitas_lv1, kode='1', nama='Modal')
        akun_modal = Akun.objects.get(kategori_id='ekuitas', kategori_akun=ekuitas_lv2.pk)

        self.item.coa_account = akun_persediaan
        self.item.save()

        stt = SubTransactionType.objects.create(
            nama='Penjualan UOM Prevalid', module='sales', direction='outflow',
            default_offset_account=akun_persediaan,
        )
        from apps.inventory.ledger import record_inflow
        # Only 20 pcs available — enough for 3 raw units, not enough for the
        # true converted demand of 36 pcs (3 boxes * 12 pcs/box).
        record_inflow(
            self.item, eb, None, None, Decimal('20'), Decimal('5000'),
            '2026-01-01', 'purchase_in',
        )

        groups = [{
            'eb_selection': f'lv1:{eb.pk}',
            'payment_account_id': akun_modal.pk,
            'items': [{
                'item_id': self.item.pk,
                'sub_transaction_type_id': stt.pk,
                'quantity': '3',
                'selling_price': '120000',
                'offset_coa_account_id': akun_persediaan.pk,
                'revenue_account_id': akun_pendapatan.pk,
                'payment_account_id': akun_modal.pk,
                'input_uom_id': self.box.pk,
            }],
        }]
        resp = client.post(reverse('sales:create'), {
            'tanggal': '2026-01-15',
            'deskripsi': 'Test UOM Sales Prevalid',
            'eb_groups_data': json.dumps(groups),
        })
        # Pre-validation must reject: re-renders the form with errors (200),
        # not a redirect (302), and no SalesItem gets created.
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SalesItem.objects.filter(item=self.item).exists())
        errors = resp.context['errors']
        self.assertTrue(
            any(k.startswith('item_stock_') for k in errors),
            f'Expected an item_stock_* validation error, got: {errors}')
