"""Unit tests for the jurnal app."""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import TipeTransaksi, Akun, Bukti
from apps.sales.models import ItemMaster
from .models import JurnalHeader, JurnalDetail

User = get_user_model()


class JurnalModelTests(TestCase):
    def setUp(self):
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas='pelanggan')
        self.tipe = TipeTransaksi.objects.create(kode_transaksi='T01', nama='Pembelian')
        self.item = ItemMaster.objects.create(kode='ITM001', nama='Barang A', satuan='pcs')
        self.akun = Akun.objects.create(kategori_id='aset', kategori_akun=1)

    def test_jurnal_header_str(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            uraian_transaksi='Pembelian Barang',
            tipe_transaksi=self.tipe,
            item=self.item,
        )
        self.assertIn('2024-01-01', str(h))
        self.assertIn('Pembelian Barang', str(h))

    def test_jurnal_detail_str(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            uraian_transaksi='Pembelian Barang',
            tipe_transaksi=self.tipe,
            item=self.item,
        )
        d = JurnalDetail.objects.create(jurnal_header=h, akun=self.akun, debit=100000, kredit=0)
        self.assertIn(str(h.id), str(d))

    def test_jurnal_detail_defaults(self):
        h = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            uraian_transaksi='Test',
            tipe_transaksi=self.tipe,
            item=self.item,
        )
        d = JurnalDetail.objects.create(jurnal_header=h, akun=self.akun)
        self.assertEqual(d.debit, 0)
        self.assertEqual(d.kredit, 0)
