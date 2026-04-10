"""Unit tests for the sales app."""
from decimal import Decimal
from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from .models import ItemMaster, SalesHeader, SalesDetail


class ItemMasterTests(TestCase):
    def test_str(self):
        item = ItemMaster.objects.create(kode='ITM001', nama='Barang A')
        self.assertIn('ITM001', str(item))

    def test_unique_kode(self):
        ItemMaster.objects.create(kode='ITM001', nama='Barang A')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ItemMaster.objects.create(kode='ITM001', nama='Duplicate')


class SalesHeaderTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Pelanggan', tipe_entitas=self.tipe)

    def test_str(self):
        h = SalesHeader.objects.create(
            nomor_invoice='INV001',
            entitas_bisnis=self.entitas,
            tanggal_transaksi='2024-01-01',
            total_nilai=Decimal('1000000'),
        )
        self.assertEqual(str(h), 'INV001')

    def test_unique_nomor_invoice(self):
        SalesHeader.objects.create(
            nomor_invoice='INV001',
            entitas_bisnis=self.entitas,
            tanggal_transaksi='2024-01-01',
            total_nilai=Decimal('1000000'),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            SalesHeader.objects.create(
                nomor_invoice='INV001',
                entitas_bisnis=self.entitas,
                tanggal_transaksi='2024-01-02',
                total_nilai=Decimal('500000'),
            )


class SalesDetailTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMaster.objects.create(kode='ITM001', nama='Barang A')
        self.header = SalesHeader.objects.create(
            nomor_invoice='INV001',
            entitas_bisnis=self.entitas,
            tanggal_transaksi='2024-01-01',
            total_nilai=Decimal('1000000'),
        )

    def test_subtotal_calculated_on_save(self):
        detail = SalesDetail.objects.create(
            sales_header=self.header,
            item_master=self.item,
            kuantitas=Decimal('10'),
            harga_satuan=Decimal('100000'),
            diskon_persen=Decimal('10'),
        )
        expected = Decimal('10') * Decimal('100000') * (1 - Decimal('10') / 100)
        self.assertEqual(detail.subtotal, expected)

    def test_str(self):
        detail = SalesDetail.objects.create(
            sales_header=self.header,
            item_master=self.item,
            kuantitas=Decimal('1'),
            harga_satuan=Decimal('100000'),
        )
        self.assertIn('INV001', str(detail))
