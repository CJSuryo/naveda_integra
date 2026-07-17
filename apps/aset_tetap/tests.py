"""Unit tests for the aset_tetap app."""
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.master_data.models import Akun
from .models import AsetTetapRecord, AssetDisposal
from .services import process_asset_disposal, reverse_asset_disposal

User = get_user_model()


class AsetTetapRecordModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Mesin Produksi', tipe_item='ATP')

    def test_auto_aset_number(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=50_000_000,
        )
        self.assertTrue(rec.aset_number.startswith('ATP-'))
        self.assertEqual(rec.total_value, 50_000_000)

    def test_sequential_numbering(self):
        r1 = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
        )
        r2 = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=20_000_000,
        )
        self.assertNotEqual(r1.aset_number, r2.aset_number)

    def test_nilai_buku_property(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
            akumulasi_penyusutan=2_000_000,
        )
        self.assertEqual(rec.nilai_buku, 8_000_000)

    def test_str(self):
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=5_000_000,
        )
        self.assertEqual(str(rec), rec.aset_number)

    def test_cascade_entitas_protect(self):
        AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=5_000_000,
        )
        from django.db import IntegrityError
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            self.entitas.delete()


class AsetTetapViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='test@test.com', password='pass')
        self.client.force_login(self.user)
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP')
        self.record = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=1, harga_perolehan=10_000_000,
        )

    def test_list_view(self):
        res = self.client.get(reverse('aset_tetap:list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.record.aset_number)

    def test_detail_view(self):
        res = self.client.get(reverse('aset_tetap:detail', args=[self.record.pk]))
        self.assertEqual(res.status_code, 200)

    def test_create_get(self):
        res = self.client.get(reverse('aset_tetap:create'))
        self.assertEqual(res.status_code, 200)

    def test_create_post(self):
        res = self.client.post(reverse('aset_tetap:create'), {
            'item': self.item.pk,
            'entitas_bisnis': self.entitas.pk,
            'quantity': '1',
            'harga_perolehan': '5000000',
            'tanggal_perolehan': '2025-01-01',
            'akumulasi_penyusutan': '0',
            'kondisi': 'baik',
        })
        self.assertEqual(AsetTetapRecord.objects.count(), 2)

    def test_update_get(self):
        res = self.client.get(reverse('aset_tetap:update', args=[self.record.pk]))
        self.assertEqual(res.status_code, 200)

    def test_update_post(self):
        res = self.client.post(reverse('aset_tetap:update', args=[self.record.pk]), {
            'item': self.item.pk,
            'entitas_bisnis': self.entitas.pk,
            'quantity': '2',
            'harga_perolehan': '10000000',
            'tanggal_perolehan': '2025-01-01',
            'akumulasi_penyusutan': '1000000',
            'kondisi': 'baik',
        })
        self.record.refresh_from_db()
        from decimal import Decimal
        self.assertEqual(self.record.quantity, Decimal('2'))

    def test_delete_get(self):
        res = self.client.get(reverse('aset_tetap:delete', args=[self.record.pk]))
        self.assertEqual(res.status_code, 302)

    def test_delete_post(self):
        res = self.client.post(reverse('aset_tetap:delete', args=[self.record.pk]))
        self.assertEqual(AsetTetapRecord.objects.count(), 0)

    def test_login_required(self):
        self.client.logout()
        res = self.client.get(reverse('aset_tetap:list'))
        self.assertNotEqual(res.status_code, 200)


class AssetDisposalModelTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        self.record = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=10, harga_perolehan=1_000_000,
        )
        self.akun_akum = Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_kas = Akun.objects.create(kategori_id='aset', kode_akun='1.1.1.01', nama='Kas')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan Aset')

    def test_status_default_aktif(self):
        self.assertEqual(self.record.status, 'aktif')

    def test_disposal_number_auto(self):
        d = AssetDisposal.objects.create(
            aset=self.record, jenis='jual', quantity=1,
            akun_laba_rugi=self.akun_lr,
        )
        self.assertTrue(d.disposal_number.startswith('DSP-'))


class ProcessDisposalTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        self.akun_akum = Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_kas = Akun.objects.create(kategori_id='aset', kode_akun='1.1.1.01', nama='Kas')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan')

    def _make_record(self, qty='1', harga='1000000', akum='0', residu='0'):
        return AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal(qty), harga_perolehan=Decimal(harga),
            akumulasi_penyusutan=Decimal(akum), nilai_residu=Decimal(residu),
        )

    def _sum_debit_kredit(self, header):
        from apps.jurnal.models import JurnalDetail
        d = sum(x.debit for x in JurnalDetail.objects.filter(jurnal_header=header))
        k = sum(x.kredit for x in JurnalDetail.objects.filter(jurnal_header=header))
        return d, k

    def test_jual_laba(self):
        # perolehan 1jt, akum 600rb -> nilai buku 400rb; jual 500rb -> laba 100rb
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('500000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.kredit, Decimal('100000.0000'))  # laba di kredit
        self.assertEqual(lr.debit, Decimal('0'))
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'dilepas')
        self.assertEqual(rec.quantity, Decimal('0.0000'))

    def test_jual_rugi(self):
        # nilai buku 400rb; jual 300rb -> rugi 100rb (debit)
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('300000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.debit, Decimal('100000.0000'))
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)

    def test_jual_impas(self):
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='jual', quantity=Decimal('1'),
                          harga_jual=Decimal('400000'), akun_kas=self.akun_kas,
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        self.assertFalse(JurnalDetail.objects.filter(jurnal_header=header, akun=self.akun_lr).exists())
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)

    def test_non_jual_full_loss(self):
        # hibah: tidak ada kas, seluruh nilai buku jadi rugi
        rec = self._make_record(qty='1', harga='1000000', akum='600000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          harga_jual=Decimal('999'), akun_kas=self.akun_kas,  # harus diabaikan
                          akun_laba_rugi=self.akun_lr)
        header = process_asset_disposal(d)
        from apps.jurnal.models import JurnalDetail
        self.assertFalse(JurnalDetail.objects.filter(jurnal_header=header, akun=self.akun_kas).exists())
        lr = JurnalDetail.objects.get(jurnal_header=header, akun=self.akun_lr)
        self.assertEqual(lr.debit, Decimal('400000.0000'))  # seluruh nilai buku = rugi
        deb, kre = self._sum_debit_kredit(header)
        self.assertEqual(deb, kre)

    def test_partial_prorata(self):
        # qty 10, harga 1jt/unit -> total 10jt, akum 2jt, residu 1jt; lepas 3
        rec = self._make_record(qty='10', harga='1000000', akum='2000000', residu='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('3'),
                          akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d)
        d.refresh_from_db()
        self.assertEqual(d.perolehan_dilepas, Decimal('3000000.0000'))
        self.assertEqual(d.akumulasi_dilepas, Decimal('600000.0000'))   # 2jt * 0.3
        self.assertEqual(d.residu_dilepas, Decimal('300000.0000'))      # 1jt * 0.3
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('7.0000'))
        self.assertEqual(rec.status, 'aktif')
        self.assertEqual(rec.total_value, Decimal('7000000.0000'))
        self.assertEqual(rec.akumulasi_penyusutan, Decimal('1400000.0000'))
        self.assertEqual(rec.nilai_residu, Decimal('700000.0000'))

    def test_validasi_qty_melebihi(self):
        rec = self._make_record(qty='2', harga='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('5'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)

    def test_validasi_akun_aset_kosong(self):
        item2 = ItemMasterPurchase.objects.create(nama='Tanpa COA', tipe_item='ATP')  # coa_account None
        rec = AsetTetapRecord.objects.create(
            item=item2, entitas_bisnis=self.entitas, quantity=1, harga_perolehan=1000000,
        )
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)

    def test_validasi_akumulasi_akun_hilang(self):
        self.akun_akum.delete()
        rec = self._make_record(qty='1', harga='1000000')
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'),
                          akun_laba_rugi=self.akun_lr)
        with self.assertRaises(ValueError):
            process_asset_disposal(d)


class ReverseDisposalTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=self.tipe)
        self.akun_aset = Akun.objects.create(kategori_id='aset', kode_akun='1.2.1.01', nama='Mesin')
        self.item = ItemMasterPurchase.objects.create(nama='Mesin X', tipe_item='ATP', coa_account=self.akun_aset)
        Akun.objects.create(kategori_id='aset', kode_akun='1.2.7.01', nama='Akumulasi Penyusutan')
        self.akun_lr = Akun.objects.create(kategori_id='pendapatan', kode_akun='8.1.01', nama='Laba/Rugi Pelepasan')

    def test_reversal_restores_state(self):
        from apps.jurnal.models import JurnalHeader
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal('10'), harga_perolehan=Decimal('1000000'),
            akumulasi_penyusutan=Decimal('2000000'), nilai_residu=Decimal('1000000'),
        )
        # dua pelepasan
        d1 = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('3'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d1)
        rec.refresh_from_db()
        d2 = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('2'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d2)
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('5.0000'))

        # reversal d1 (yang pertama — bebas kapan saja)
        header_pk = d1.jurnal_header_id
        reverse_asset_disposal(d1)
        rec.refresh_from_db()
        self.assertEqual(rec.quantity, Decimal('8.0000'))              # 5 + 3
        self.assertEqual(rec.status, 'aktif')
        self.assertFalse(JurnalHeader.objects.filter(pk=header_pk).exists())
        self.assertFalse(AssetDisposal.objects.filter(pk=d1.pk).exists())

    def test_reversal_logs_deletion(self):
        from apps.jurnal.models import JurnalTerhapus
        rec = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.entitas,
            quantity=Decimal('1'), harga_perolehan=Decimal('1000000'),
        )
        d = AssetDisposal(aset=rec, jenis='hibah', quantity=Decimal('1'), akun_laba_rugi=self.akun_lr)
        process_asset_disposal(d)
        reverse_asset_disposal(d)
        self.assertTrue(JurnalTerhapus.objects.exists())
