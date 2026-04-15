"""Unit tests for the sales app."""
from decimal import Decimal
from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase, SubTransactionType, FIFOBatch
from .models import SalesHeader, SalesItem
from .services import get_available_stock, consume_fifo


class SalesHeaderModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun = Akun.objects.create(kategori_id='aset', nama='Kas')

    def test_str(self):
        h = SalesHeader.objects.create(
            entitas_bisnis=self.entitas,
            payment_account=self.akun,
        )
        self.assertTrue(h.transaction_id.startswith('TRX-SAL-'))
        self.assertEqual(str(h), h.transaction_id)

    def test_auto_transaction_id(self):
        h1 = SalesHeader.objects.create(entitas_bisnis=self.entitas, payment_account=self.akun)
        h2 = SalesHeader.objects.create(entitas_bisnis=self.entitas, payment_account=self.akun)
        self.assertEqual(h1.transaction_id, 'TRX-SAL-001')
        self.assertEqual(h2.transaction_id, 'TRX-SAL-002')


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
        self.header = SalesHeader.objects.create(
            entitas_bisnis=self.entitas,
            payment_account=self.akun_kas,
        )

    def test_total_sales_computed(self):
        si = SalesItem.objects.create(
            sales_header=self.header,
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
            sales_header=self.header,
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
            sales_header=self.header,
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
        # 100 × 10000 + 20 × 12000 = 1,240,000
        expected_cogs = Decimal('100') * Decimal('10000') + Decimal('20') * Decimal('12000')
        self.assertEqual(cogs, expected_cogs)
        self.assertEqual(len(consumed), 2)
        # Remaining stock should be 30
        self.assertEqual(get_available_stock(self.item.pk), Decimal('30'))

    def test_consume_fifo_insufficient_stock(self):
        with self.assertRaises(ValueError):
            consume_fifo(self.item.pk, Decimal('200'))
