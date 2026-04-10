"""Unit tests for the jurnal app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
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

class JurnalHeaderViewTests(TestCase):
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

    def test_index(self):
        response = self.client.get(reverse('jurnal:index'))
        self.assertEqual(response.status_code, 200)

    def test_header_list(self):
        response = self.client.get(reverse('jurnal:header_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TRX-INV-001')

    def test_header_create_get(self):
        response = self.client.get(reverse('jurnal:header_create'))
        self.assertEqual(response.status_code, 200)

    def test_header_create_post(self):
        data = {
            'tanggal': '2024-02-01',
            'nomor_transaksi': 'TRX-INV-099',
            'uraian_transaksi': 'New Header',
            'item': self.item.pk,
            'transaction_prefix': self.prefix.pk,
        }
        response = self.client.post(reverse('jurnal:header_create'), data)
        self.assertRedirects(response, reverse('jurnal:header_list'))
        self.assertTrue(JurnalHeader.objects.filter(nomor_transaksi='TRX-INV-099').exists())

    def test_header_update(self):
        data = {
            'tanggal': '2024-01-01',
            'nomor_transaksi': 'TRX-INV-001',
            'uraian_transaksi': 'Updated Header',
            'item': self.item.pk,
            'transaction_prefix': self.prefix.pk,
        }
        response = self.client.post(reverse('jurnal:header_update', args=[self.header.pk]), data)
        self.assertRedirects(response, reverse('jurnal:header_list'))
        self.header.refresh_from_db()
        self.assertEqual(self.header.uraian_transaksi, 'Updated Header')

    def test_header_delete(self):
        response = self.client.post(reverse('jurnal:header_delete', args=[self.header.pk]))
        self.assertRedirects(response, reverse('jurnal:header_list'))
        self.assertFalse(JurnalHeader.objects.filter(pk=self.header.pk).exists())

    def test_header_detail(self):
        response = self.client.get(reverse('jurnal:header_detail', args=[self.header.pk]))
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('jurnal:header_list'))
        self.assertEqual(response.status_code, 302)


class JurnalDetailViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.item = Item.objects.create(kode='A', nama='Persediaan')
        self.prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')
        self.header = JurnalHeader.objects.create(
            tanggal='2024-01-01',
            nomor_transaksi='TRX-INV-001',
            uraian_transaksi='Test',
            item=self.item,
        )
        self.akun = Akun.objects.create(kategori_id='aset', kategori_akun=1, nama='Test Akun')
        self.detail = JurnalDetail.objects.create(
            jurnal_header=self.header, akun=self.akun, debit=10000, kredit=0
        )

    def test_detail_create_get(self):
        response = self.client.get(reverse('jurnal:detail_create', args=[self.header.pk]))
        self.assertEqual(response.status_code, 200)

    def test_detail_create_post(self):
        data = {'akun': self.akun.pk, 'debit': '50000', 'kredit': '0'}
        response = self.client.post(reverse('jurnal:detail_create', args=[self.header.pk]), data)
        self.assertRedirects(response, reverse('jurnal:header_detail', args=[self.header.pk]))

    def test_detail_update(self):
        data = {'akun': self.akun.pk, 'debit': '20000', 'kredit': '0'}
        response = self.client.post(
            reverse('jurnal:detail_update', args=[self.header.pk, self.detail.pk]), data
        )
        self.assertRedirects(response, reverse('jurnal:header_detail', args=[self.header.pk]))
        self.detail.refresh_from_db()
        self.assertEqual(self.detail.debit, 20000)

    def test_detail_delete(self):
        response = self.client.post(
            reverse('jurnal:detail_delete', args=[self.header.pk, self.detail.pk])
        )
        self.assertRedirects(response, reverse('jurnal:header_detail', args=[self.header.pk]))
        self.assertFalse(JurnalDetail.objects.filter(pk=self.detail.pk).exists())


class ItemViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.item = Item.objects.create(kode='A', nama='Persediaan')

    def test_list(self):
        response = self.client.get(reverse('jurnal:item_list'))
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {'kode': 'B', 'nama': 'Barang Baru'}
        response = self.client.post(reverse('jurnal:item_create'), data)
        self.assertRedirects(response, reverse('jurnal:item_list'))

    def test_update(self):
        data = {'kode': 'A', 'nama': 'Updated'}
        response = self.client.post(reverse('jurnal:item_update', args=[self.item.pk]), data)
        self.assertRedirects(response, reverse('jurnal:item_list'))

    def test_delete(self):
        i = Item.objects.create(kode='DEL', nama='To Delete')
        response = self.client.post(reverse('jurnal:item_delete', args=[i.pk]))
        self.assertRedirects(response, reverse('jurnal:item_list'))


class TransactionPrefixViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_user()
        self.client.force_login(self.user)
        self.prefix = TransactionPrefix.objects.create(kode='TRX-INV', nama='Inventory')

    def test_list(self):
        response = self.client.get(reverse('jurnal:prefix_list'))
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {'kode': 'TRX-NEW', 'nama': 'New Prefix'}
        response = self.client.post(reverse('jurnal:prefix_create'), data)
        self.assertRedirects(response, reverse('jurnal:prefix_list'))

    def test_update(self):
        data = {'kode': 'TRX-INV', 'nama': 'Updated'}
        response = self.client.post(reverse('jurnal:prefix_update', args=[self.prefix.pk]), data)
        self.assertRedirects(response, reverse('jurnal:prefix_list'))


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
