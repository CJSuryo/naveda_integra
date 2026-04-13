"""Unit tests for the master_data app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import (
    AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2, EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2, BebanLv1, BebanLv2,
    TipeTransaksi, Bukti, Akun, _compute_kode_akun, KATEGORI_PREFIX,
)

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


class ComputeKodeAkunTests(TestCase):
    def test_aset_kode(self):
        lv1 = AsetLv1.objects.create(kode='1', nama='Aset Lancar')
        lv2 = AsetLv2.objects.create(kode='101', nama='Kas', aset=lv1)
        kode = _compute_kode_akun('aset', lv2.pk)
        self.assertEqual(kode, f'{KATEGORI_PREFIX["aset"]}.{lv1.kode}.{lv2.kode}')

    def test_kewajiban_kode(self):
        lv1 = KewajibanLv1.objects.create(kode='2', nama='Utang Jk Pendek')
        lv2 = KewajibanLv2.objects.create(kode='201', nama='Utang Usaha', kewajiban=lv1)
        kode = _compute_kode_akun('kewajiban', lv2.pk)
        self.assertEqual(kode, f'{KATEGORI_PREFIX["kewajiban"]}.{lv1.kode}.{lv2.kode}')

    def test_ekuitas_kode(self):
        lv1 = EkuitasLv1.objects.create(kode='3', nama='Modal')
        lv2 = EkuitasLv2.objects.create(kode='301', nama='Modal Disetor', ekuitas=lv1)
        kode = _compute_kode_akun('ekuitas', lv2.pk)
        self.assertEqual(kode, f'{KATEGORI_PREFIX["ekuitas"]}.{lv1.kode}.{lv2.kode}')

    def test_no_kategori_akun(self):
        kode = _compute_kode_akun('aset', None)
        self.assertEqual(kode, f'{KATEGORI_PREFIX["aset"]}.?.?')

    def test_lv2_without_lv1(self):
        lv2 = AsetLv2.objects.create(kode='102', nama='Kas Tanpa Parent', aset=None)
        kode = _compute_kode_akun('aset', lv2.pk)
        self.assertEqual(kode, f'{KATEGORI_PREFIX["aset"]}.?.{lv2.kode}')


class AkunSignalTests(TestCase):
    def test_aset_lv2_save_creates_akun_with_kode(self):
        lv1 = AsetLv1.objects.create(kode='1', nama='Aset Lancar')
        lv2 = AsetLv2.objects.create(kode='101', nama='Kas', aset=lv1)
        akun = Akun.objects.filter(kategori_id='aset', kategori_akun=lv2.pk).first()
        self.assertIsNotNone(akun)
        self.assertEqual(akun.kode_akun, f'{KATEGORI_PREFIX["aset"]}.{lv1.kode}.{lv2.kode}')

    def test_kewajiban_lv2_save_creates_akun_with_kode(self):
        lv1 = KewajibanLv1.objects.create(kode='2', nama='Utang')
        lv2 = KewajibanLv2.objects.create(kode='201', nama='Utang Usaha', kewajiban=lv1)
        akun = Akun.objects.filter(kategori_id='kewajiban', kategori_akun=lv2.pk).first()
        self.assertIsNotNone(akun)
        self.assertEqual(akun.kode_akun, f'{KATEGORI_PREFIX["kewajiban"]}.{lv1.kode}.{lv2.kode}')

    def test_ekuitas_lv2_save_creates_akun_with_kode(self):
        lv1 = EkuitasLv1.objects.create(kode='3', nama='Modal')
        lv2 = EkuitasLv2.objects.create(kode='301', nama='Modal Disetor', ekuitas=lv1)
        akun = Akun.objects.filter(kategori_id='ekuitas', kategori_akun=lv2.pk).first()
        self.assertIsNotNone(akun)
        self.assertEqual(akun.kode_akun, f'{KATEGORI_PREFIX["ekuitas"]}.{lv1.kode}.{lv2.kode}')

    def test_aset_lv2_delete_removes_akun(self):
        lv1 = AsetLv1.objects.create(kode='1', nama='Aset Lancar')
        lv2 = AsetLv2.objects.create(kode='101', nama='Kas', aset=lv1)
        lv2_pk = lv2.pk
        lv2.delete()
        self.assertFalse(Akun.objects.filter(kategori_id='aset', kategori_akun=lv2_pk).exists())


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
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kas')

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kas Kecil')

    def test_lv1_create(self):
        data = {'kode': '1.2', 'nama': 'Bank'}
        response = self.client.post(reverse('master_data:aset_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.assertTrue(AsetLv1.objects.filter(kode='1.2').exists())

    def test_lv1_update(self):
        data = {'kode': '1.1', 'nama': 'Kas Updated'}
        response = self.client.post(reverse('master_data:aset_lv1_update', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.lv1.refresh_from_db()
        self.assertEqual(self.lv1.nama, 'Kas Updated')

    def test_lv1_delete(self):
        lv1_new = AsetLv1.objects.create(kode='9.9', nama='To Delete')
        response = self.client.post(reverse('master_data:aset_lv1_delete', args=[lv1_new.pk]))
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.assertFalse(AsetLv1.objects.filter(pk=lv1_new.pk).exists())

    def test_lv2_create(self):
        data = {'kode': '1.1.2', 'nama': 'Kas Besar'}
        response = self.client.post(reverse('master_data:aset_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.assertTrue(AsetLv2.objects.filter(kode='1.1.2').exists())

    def test_lv2_update(self):
        data = {'kode': '1.1.1', 'nama': 'Kas Kecil Updated'}
        response = self.client.post(reverse('master_data:aset_lv2_update', args=[self.lv1.pk, self.lv2.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.lv2.refresh_from_db()
        self.assertEqual(self.lv2.nama, 'Kas Kecil Updated')

    def test_lv2_delete(self):
        lv2_new = AsetLv2.objects.create(kode='1.1.9', nama='To Delete', aset=self.lv1)
        response = self.client.post(reverse('master_data:aset_lv2_delete', args=[self.lv1.pk, lv2_new.pk]))
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))
        self.assertFalse(AsetLv2.objects.filter(pk=lv2_new.pk).exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 302)


class KewajibanViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = KewajibanLv1.objects.create(kode='2.1', nama='Utang Usaha')
        self.lv2 = KewajibanLv2.objects.create(kode='2.1.1', nama='Utang Supplier A', kewajiban=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Utang Supplier A')

    def test_lv1_create(self):
        data = {'kode': '2.2', 'nama': 'Utang Bank'}
        response = self.client.post(reverse('master_data:kewajiban_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))

    def test_lv2_create(self):
        data = {'kode': '2.1.2', 'nama': 'Utang Supplier B'}
        response = self.client.post(reverse('master_data:kewajiban_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))


class EkuitasViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = EkuitasLv1.objects.create(kode='3.1', nama='Modal')
        self.lv2 = EkuitasLv2.objects.create(kode='3.1.1', nama='Modal Disetor', ekuitas=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)

    def test_lv2_create(self):
        data = {'kode': '3.1.2', 'nama': 'Laba Ditahan'}
        response = self.client.post(reverse('master_data:ekuitas_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))


class TipeTransaksiViewTests(TestCase):
    """TipeTransaksi is now read-only."""
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.tt = TipeTransaksi.objects.create(kode_transaksi='TRX001', nama='Pembelian')

    def test_list(self):
        response = self.client.get(reverse('master_data:tipe_transaksi_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pembelian')

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('master_data:tipe_transaksi_list'))
        self.assertEqual(response.status_code, 302)


# ── Pendapatan Model Tests ───────────────────────────────────────────────────

class PendapatanModelTests(TestCase):
    def test_pendapatan_lv1_str(self):
        p = PendapatanLv1.objects.create(kode='4.1', nama='Pendapatan Usaha')
        self.assertIn('4.1', str(p))

    def test_pendapatan_lv2_fk(self):
        parent = PendapatanLv1.objects.create(kode='4.1', nama='Pendapatan Usaha')
        child = PendapatanLv2.objects.create(kode='4.1.1', nama='Penjualan', pendapatan=parent)
        self.assertEqual(child.pendapatan, parent)
        self.assertIn(child, parent.children.all())


class BebanModelTests(TestCase):
    def test_beban_lv1_str(self):
        b = BebanLv1.objects.create(kode='5.1', nama='Beban Operasional')
        self.assertIn('5.1', str(b))

    def test_beban_lv2_fk(self):
        parent = BebanLv1.objects.create(kode='5.1', nama='Beban Operasional')
        child = BebanLv2.objects.create(kode='5.1.1', nama='Beban Gaji', beban=parent)
        self.assertEqual(child.beban, parent)
        self.assertIn(child, parent.children.all())


# ── Pendapatan/Beban Signal Tests ────────────────────────────────────────────

class PendapatanBebanSignalTests(TestCase):
    def test_pendapatan_lv2_creates_akun(self):
        lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        lv2 = PendapatanLv2.objects.create(kode='401', nama='Penjualan', pendapatan=lv1)
        akun = Akun.objects.filter(kategori_id='pendapatan', kategori_akun=lv2.pk).first()
        self.assertIsNotNone(akun)
        self.assertEqual(akun.nama, 'Penjualan')
        self.assertEqual(akun.kode_akun, f'{KATEGORI_PREFIX["pendapatan"]}.{lv1.kode}.{lv2.kode}')

    def test_beban_lv2_creates_akun(self):
        lv1 = BebanLv1.objects.create(kode='5', nama='Beban')
        lv2 = BebanLv2.objects.create(kode='501', nama='Beban Gaji', beban=lv1)
        akun = Akun.objects.filter(kategori_id='beban', kategori_akun=lv2.pk).first()
        self.assertIsNotNone(akun)
        self.assertEqual(akun.nama, 'Beban Gaji')
        self.assertEqual(akun.kode_akun, f'{KATEGORI_PREFIX["beban"]}.{lv1.kode}.{lv2.kode}')

    def test_pendapatan_lv2_delete_removes_akun(self):
        lv1 = PendapatanLv1.objects.create(kode='4', nama='Pendapatan')
        lv2 = PendapatanLv2.objects.create(kode='401', nama='Penjualan', pendapatan=lv1)
        lv2_pk = lv2.pk
        lv2.delete()
        self.assertFalse(Akun.objects.filter(kategori_id='pendapatan', kategori_akun=lv2_pk).exists())

    def test_beban_lv2_delete_removes_akun(self):
        lv1 = BebanLv1.objects.create(kode='5', nama='Beban')
        lv2 = BebanLv2.objects.create(kode='501', nama='Beban Gaji', beban=lv1)
        lv2_pk = lv2.pk
        lv2.delete()
        self.assertFalse(Akun.objects.filter(kategori_id='beban', kategori_akun=lv2_pk).exists())


# ── Pendapatan/Beban View Tests ──────────────────────────────────────────────

class PendapatanViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = PendapatanLv1.objects.create(kode='4.1', nama='Pendapatan Usaha')
        self.lv2 = PendapatanLv2.objects.create(kode='4.1.1', nama='Penjualan', pendapatan=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pendapatan Usaha')

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Penjualan')

    def test_lv1_create(self):
        data = {'kode': '4.2', 'nama': 'Pendapatan Lain'}
        response = self.client.post(reverse('master_data:pendapatan_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))

    def test_lv2_create(self):
        data = {'kode': '4.1.2', 'nama': 'Pendapatan Jasa'}
        response = self.client.post(reverse('master_data:pendapatan_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))


class BebanViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        self.lv1 = BebanLv1.objects.create(kode='5.1', nama='Beban Operasional')
        self.lv2 = BebanLv2.objects.create(kode='5.1.1', nama='Beban Gaji', beban=self.lv1)

    def test_lv1_list(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beban Operasional')

    def test_lv1_detail(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beban Gaji')

    def test_lv1_create(self):
        data = {'kode': '5.2', 'nama': 'Beban Lain'}
        response = self.client.post(reverse('master_data:beban_lv1_create'), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))

    def test_lv2_create(self):
        data = {'kode': '5.1.2', 'nama': 'Beban Listrik'}
        response = self.client.post(reverse('master_data:beban_lv2_create', args=[self.lv1.pk]), data)
        self.assertRedirects(response, reverse('master_data:chart_of_accounts'))


# ── Chart of Accounts View Tests ─────────────────────────────────────────────

class ChartOfAccountsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_user()
        self.client.force_login(self.user)
        AsetLv1.objects.create(kode='1.1', nama='Kas')
        KewajibanLv1.objects.create(kode='2.1', nama='Utang Usaha')
        EkuitasLv1.objects.create(kode='3.1', nama='Modal')
        PendapatanLv1.objects.create(kode='4.1', nama='Pendapatan Usaha')
        BebanLv1.objects.create(kode='5.1', nama='Beban Operasional')

    def test_coa_page(self):
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chart of Accounts')
        self.assertContains(response, 'Aset')
        self.assertContains(response, 'Kewajiban')
        self.assertContains(response, 'Ekuitas')
        self.assertContains(response, 'Pendapatan')
        self.assertContains(response, 'Beban')

    def test_coa_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('master_data:chart_of_accounts'))
        self.assertEqual(response.status_code, 302)
