"""Unit tests for the master_data app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2, EkuitasLv1, EkuitasLv2, TipeTransaksi, Bukti, Akun

User = get_user_model()


def create_user():
    return User.objects.create_user(email='md@test.com', password='pass', name='MD User')


# ── Model Tests ───────────────────────────────────────────────────────────────

class AsetModelTests(TestCase):
    def test_aset_lv1_str(self):
        a = AsetLv1.objects.create(kode='1.1', nama='Kas')
        self.assertIn('1.1', str(a))

    def test_aset_lv2_str(self):
        parent = AsetLv1.objects.create(kode='1.1', nama='Kas')
        child = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=parent)
        self.assertIn('1.1.1', str(child))

    def test_aset_lv2_fk(self):
        parent = AsetLv1.objects.create(kode='1.2', nama='Bank')
        child = AsetLv2.objects.create(kode='1.2.1', nama='BCA', aset=parent)
        self.assertEqual(child.aset, parent)
        self.assertIn(child, parent.children.all())

    def test_unique_kode(self):
        AsetLv1.objects.create(kode='1.1', nama='Kas')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            AsetLv1.objects.create(kode='1.1', nama='Duplicate')


class KewajibanModelTests(TestCase):
    def test_kewajiban_lv1_str(self):
        k = KewajibanLv1.objects.create(kode='2.1', nama='Utang Usaha')
        self.assertIn('2.1', str(k))

    def test_kewajiban_lv2_fk(self):
        parent = KewajibanLv1.objects.create(kode='2.1', nama='Utang Usaha')
        child = KewajibanLv2.objects.create(kode='2.1.1', nama='Utang ke Supplier A', kewajiban=parent)
        self.assertEqual(child.kewajiban, parent)


class EkuitasModelTests(TestCase):
    def test_ekuitas_lv1_str(self):
        e = EkuitasLv1.objects.create(kode='3.1', nama='Modal')
        self.assertIn('3.1', str(e))

    def test_ekuitas_lv2_fk(self):
        parent = EkuitasLv1.objects.create(kode='3.1', nama='Modal')
        child = EkuitasLv2.objects.create(kode='3.1.1', nama='Modal Disetor', ekuitas=parent)
        self.assertEqual(child.ekuitas, parent)


class TipeTransaksiModelTests(TestCase):
    def test_str(self):
        tt = TipeTransaksi.objects.create(kode_transaksi='TRX001', nama='Pembelian')
        self.assertIn('TRX001', str(tt))

    def test_unique_kode(self):
        TipeTransaksi.objects.create(kode_transaksi='TRX001', nama='Pembelian')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            TipeTransaksi.objects.create(kode_transaksi='TRX001', nama='Duplicate')


class AkunModelTests(TestCase):
    def test_create_akun(self):
        a = Akun.objects.create(kategori_id='aset', kategori_akun=1)
        self.assertEqual(a.kategori_id, 'aset')


class BuktiModelTests(TestCase):
    def test_str(self):
        b = Bukti.objects.create(referensi_eksternal='REF001', tipe_dokumen='invoice', filepath='/tmp/doc.pdf', file_hash='abc123')
        self.assertIn('REF001', str(b))


# ── View Tests ────────────────────────────────────────────────────────────────

class AsetViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = AsetLv1.objects.create(kode='1.1', nama='Kas')
        self.lv2 = AsetLv2.objects.create(kode='1.1.1', nama='Kas Kecil', aset=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:aset_lv1_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kas')

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:aset_lv1_detail', args=[self.lv1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kas Kecil')

    def test_lv1_create(self):
        data = {'kode': '1.2', 'nama': 'Bank'}
        response = self.client.post(reverse('master_data:aset_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:aset_lv1_list'))
        self.assertTrue(AsetLv1.objects.filter(kode='1.2').exists())

    def test_lv1_update(self):
        data = {'kode': '1.1', 'nama': 'Kas Updated'}
        response = self.client.post(reverse('master_data:aset_lv1_update', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:aset_lv1_list'))
        self.lv1.refresh_from_db()
        self.assertEqual(self.lv1.nama, 'Kas Updated')

    def test_lv1_delete(self):
        lv1_new = AsetLv1.objects.create(kode='9.9', nama='To Delete')
        response = self.client.post(reverse('master_data:aset_lv1_delete', args=[lv1_new.pk]))
        self.assertRedirects(response, reverse('master_data:aset_lv1_list'))
        self.assertFalse(AsetLv1.objects.filter(pk=lv1_new.pk).exists())

    def test_lv2_create(self):
        data = {'kode': '1.1.2', 'nama': 'Kas Besar'}
        response = self.client.post(reverse('master_data:aset_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:aset_lv1_detail', args=[self.lv1.pk]))
        self.assertTrue(AsetLv2.objects.filter(kode='1.1.2').exists())

    def test_lv2_update(self):
        data = {'kode': '1.1.1', 'nama': 'Kas Kecil Updated'}
        response = self.client.post(reverse('master_data:aset_lv2_update', args=[self.lv1.pk, self.lv2.pk]), data)
        self.assertRedirects(response, reverse('master_data:aset_lv1_detail', args=[self.lv1.pk]))
        self.lv2.refresh_from_db()
        self.assertEqual(self.lv2.nama, 'Kas Kecil Updated')

    def test_lv2_delete(self):
        lv2_new = AsetLv2.objects.create(kode='1.1.9', nama='To Delete', aset=self.lv1)
        response = self.client.post(reverse('master_data:aset_lv2_delete', args=[self.lv1.pk, lv2_new.pk]))
        self.assertRedirects(response, reverse('master_data:aset_lv1_detail', args=[self.lv1.pk]))
        self.assertFalse(AsetLv2.objects.filter(pk=lv2_new.pk).exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('master_data:aset_lv1_list'))
        self.assertEqual(response.status_code, 302)


class KewajibanViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = KewajibanLv1.objects.create(kode='2.1', nama='Utang Usaha')
        self.lv2 = KewajibanLv2.objects.create(kode='2.1.1', nama='Utang Supplier A', kewajiban=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:kewajiban_lv1_list'))
        self.assertEqual(response.status_code, 200)

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:kewajiban_lv1_detail', args=[self.lv1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Utang Supplier A')

    def test_lv1_create(self):
        data = {'kode': '2.2', 'nama': 'Utang Bank'}
        response = self.client.post(reverse('master_data:kewajiban_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:kewajiban_lv1_list'))

    def test_lv2_create(self):
        data = {'kode': '2.1.2', 'nama': 'Utang Supplier B'}
        response = self.client.post(reverse('master_data:kewajiban_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:kewajiban_lv1_detail', args=[self.lv1.pk]))


class EkuitasViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = EkuitasLv1.objects.create(kode='3.1', nama='Modal')
        self.lv2 = EkuitasLv2.objects.create(kode='3.1.1', nama='Modal Disetor', ekuitas=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:ekuitas_lv1_list'))
        self.assertEqual(response.status_code, 200)

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:ekuitas_lv1_detail', args=[self.lv1.pk]))
        self.assertEqual(response.status_code, 200)

    def test_lv2_create(self):
        data = {'kode': '3.1.2', 'nama': 'Laba Ditahan'}
        response = self.client.post(reverse('master_data:ekuitas_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:ekuitas_lv1_detail', args=[self.lv1.pk]))


class TipeTransaksiViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.tt = TipeTransaksi.objects.create(kode_transaksi='TRX001', nama='Pembelian')

    def test_list(self):
        response = self.client.get(reverse('master_data:tipe_transaksi_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pembelian')

    def test_create(self):
        data = {'kode_transaksi': 'TRX002', 'nama': 'Penjualan'}
        response = self.client.post(reverse('master_data:tipe_transaksi_create'), data)
        self.assertRedirects(response, reverse('master_data:tipe_transaksi_list'))
        self.assertTrue(TipeTransaksi.objects.filter(kode_transaksi='TRX002').exists())

    def test_update(self):
        data = {'kode_transaksi': 'TRX001', 'nama': 'Pembelian Updated'}
        response = self.client.post(reverse('master_data:tipe_transaksi_update', args=[self.tt.pk]), data)
        self.assertRedirects(response, reverse('master_data:tipe_transaksi_list'))
        self.tt.refresh_from_db()
        self.assertEqual(self.tt.nama, 'Pembelian Updated')

    def test_delete(self):
        tt2 = TipeTransaksi.objects.create(kode_transaksi='DEL001', nama='To Delete')
        response = self.client.post(reverse('master_data:tipe_transaksi_delete', args=[tt2.pk]))
        self.assertRedirects(response, reverse('master_data:tipe_transaksi_list'))
        self.assertFalse(TipeTransaksi.objects.filter(pk=tt2.pk).exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('master_data:tipe_transaksi_list'))
        self.assertEqual(response.status_code, 302)
