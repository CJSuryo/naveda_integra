"""Tests Fase 7 — fixed asset lifecycle."""
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import (
    TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
)
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from apps.master_data.models import Akun
from apps.aset_tetap.models import AsetTetapRecord, LokasiAset, AssetMaintenance, AssetTransfer, AssetRevaluation
from apps.aset_tetap.services import calculate_depreciation
from apps.jurnal.models import JurnalHeader


def base_setup(self):
    self.tipe = TipeEntitas.objects.create(nama='PT')
    self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
    self.eb2 = EntitasBisnis.objects.create(nama='PT B', tipe_entitas=self.tipe)
    self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Cabang 1')
    self.dept = EntitasBisnisLv3.objects.create(parent_lv2=self.lv2, nama='Produksi')
    self.item = ItemMasterPurchase.objects.create(nama='Mesin', tipe_item='ATP')
    self.aset = AsetTetapRecord.objects.create(
        item=self.item, entitas_bisnis=self.eb,
        quantity=1, harga_perolehan=Decimal('100000000'),
        akumulasi_penyusutan=Decimal('20000000'),
    )


class FondasiDataTests(TestCase):
    def setUp(self):
        base_setup(self)

    def test_lokasi_aset_create(self):
        lok = LokasiAset.objects.create(kode='GDG-1', nama='Gudang Pusat', entitas_bisnis=self.eb)
        self.assertTrue(lok.is_active)
        self.assertEqual(str(lok), 'GDG-1 - Gudang Pusat')

    def test_aset_new_fields(self):
        lok = LokasiAset.objects.create(kode='GDG-1', nama='Gudang Pusat')
        self.aset.lokasi_aset = lok
        self.aset.departemen = self.dept
        self.aset.pic = 'Budi'
        self.aset.save()
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.lokasi_aset, lok)
        self.assertEqual(self.aset.departemen, self.dept)
        self.assertEqual(self.aset.pic, 'Budi')


class KategoriDefaultTests(TestCase):
    def setUp(self):
        base_setup(self)

    def test_kategori_default_fields(self):
        kat = KategoriItem.objects.create(
            nama='Kendaraan', tipe_item='ATP',
            masa_manfaat_default=8, metode_penyusutan_default='straight_line',
        )
        self.assertEqual(kat.masa_manfaat_default, 8)

    def test_depreciation_inherits_kategori_default(self):
        kat = KategoriItem.objects.create(
            nama='Kendaraan', tipe_item='ATP',
            masa_manfaat_default=10, metode_penyusutan_default='straight_line',
        )
        item = ItemMasterPurchase.objects.create(nama='Truk', tipe_item='ATP', kategori=kat)
        aset = AsetTetapRecord.objects.create(
            item=item, entitas_bisnis=self.eb, quantity=1,
            harga_perolehan=Decimal('36500000'), nilai_residu=Decimal('0'),
        )
        # 36.500.000 / (10*365) = 10.000/hari; 30 hari = 300.000
        amount = calculate_depreciation(aset, days=30)
        self.assertEqual(amount, Decimal('300000'))

    def test_fallback_priority_record_beats_item_beats_kategori(self):
        """masa_manfaat/metode_penyusutan resolution must prefer:
        record-level override > item master > kategori default.
        """
        kat = KategoriItem.objects.create(
            nama='Kendaraan', tipe_item='ATP',
            masa_manfaat_default=10, metode_penyusutan_default='straight_line',
        )
        item = ItemMasterPurchase.objects.create(
            nama='Truk', tipe_item='ATP', kategori=kat,
            masa_manfaat=5, metode_penyusutan='straight_line',
        )
        aset = AsetTetapRecord.objects.create(
            item=item, entitas_bisnis=self.eb, quantity=1,
            harga_perolehan=Decimal('36500000'), nilai_residu=Decimal('0'),
        )

        # No record-level override: item master (5 tahun) must beat kategori default (10 tahun).
        # 36.500.000 / (5*365) = 20.000/hari; 30 hari = 600.000
        amount = calculate_depreciation(aset, days=30)
        self.assertEqual(amount, Decimal('600000'))

        # Record-level override (2 tahun) must beat item master (5 tahun).
        aset.masa_manfaat = 2
        aset.metode_penyusutan = 'straight_line'
        aset.save()
        # 36.500.000 / (2*365) = 50.000/hari; 30 hari = 1.500.000
        amount = calculate_depreciation(aset, days=30)
        self.assertEqual(amount, Decimal('1500000'))


class MaintenanceTests(TestCase):
    def setUp(self):
        base_setup(self)
        self.akun_beban = Akun.objects.create(kode_akun='5.2.1', nama='Beban Pemeliharaan')
        self.akun_kas = Akun.objects.create(kode_akun='1.1.1', nama='Kas')

    def test_process_maintenance_creates_journal(self):
        from apps.aset_tetap.services import process_asset_maintenance
        mtn = AssetMaintenance.objects.create(
            aset=self.aset, jenis='servis', biaya=Decimal('500000'),
            akun_beban=self.akun_beban, akun_kas_utang=self.akun_kas,
            kondisi_setelah='baik',
        )
        header = process_asset_maintenance(mtn)
        self.assertTrue(mtn.maintenance_number.startswith('MTN-'))
        self.assertTrue(header.nomor_transaksi.startswith('TRX-MTN-'))
        details = list(header.details.all())
        self.assertEqual(sum(d.debit for d in details), Decimal('500000'))
        self.assertEqual(sum(d.kredit for d in details), Decimal('500000'))
        beban = header.details.get(akun=self.akun_beban)
        self.assertEqual(beban.debit, Decimal('500000'))

    def test_maintenance_updates_kondisi(self):
        from apps.aset_tetap.services import process_asset_maintenance
        self.aset.kondisi = 'rusak_ringan'
        self.aset.save()
        mtn = AssetMaintenance.objects.create(
            aset=self.aset, jenis='perbaikan', biaya=Decimal('1000000'),
            akun_beban=self.akun_beban, akun_kas_utang=self.akun_kas,
            kondisi_setelah='baik',
        )
        process_asset_maintenance(mtn)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.kondisi, 'baik')

    def test_maintenance_biaya_must_be_positive(self):
        from apps.aset_tetap.services import process_asset_maintenance
        mtn = AssetMaintenance.objects.create(
            aset=self.aset, jenis='rutin', biaya=Decimal('0'),
            akun_beban=self.akun_beban, akun_kas_utang=self.akun_kas,
        )
        with self.assertRaises(ValueError):
            process_asset_maintenance(mtn)

    def test_reverse_maintenance(self):
        from apps.aset_tetap.services import process_asset_maintenance, reverse_asset_maintenance
        self.aset.kondisi = 'rusak_ringan'
        self.aset.save()
        mtn = AssetMaintenance.objects.create(
            aset=self.aset, jenis='perbaikan', biaya=Decimal('1000000'),
            akun_beban=self.akun_beban, akun_kas_utang=self.akun_kas,
            kondisi_setelah='baik',
        )
        process_asset_maintenance(mtn)
        reverse_asset_maintenance(mtn)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.kondisi, 'rusak_ringan')
        self.assertEqual(JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-MTN-').count(), 0)


class TransferIntraEBTests(TestCase):
    def setUp(self):
        base_setup(self)
        self.lok1 = LokasiAset.objects.create(kode='L1', nama='Gudang 1')
        self.lok2 = LokasiAset.objects.create(kode='L2', nama='Gudang 2')

    def test_intra_eb_no_journal(self):
        from apps.aset_tetap.services import process_asset_transfer
        trf = AssetTransfer.objects.create(
            aset=self.aset, jenis='intra_eb',
            lokasi_tujuan=self.lok2, dept_tujuan=self.dept, pic_baru='Andi',
        )
        header = process_asset_transfer(trf)
        self.assertIsNone(header)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.lokasi_aset, self.lok2)
        self.assertEqual(self.aset.departemen, self.dept)
        self.assertEqual(self.aset.pic, 'Andi')
        self.assertEqual(JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-TRF-').count(), 0)

    def test_intra_eb_reverse(self):
        from apps.aset_tetap.services import process_asset_transfer, reverse_asset_transfer
        # Set an initial lokasi/dept/pic so the "restore" assertion is meaningful.
        self.aset.lokasi_aset = self.lok1
        self.aset.departemen = self.dept
        self.aset.pic = 'Budi'
        self.aset.save()

        trf = AssetTransfer.objects.create(
            aset=self.aset, jenis='intra_eb',
            lokasi_tujuan=self.lok2, dept_tujuan=None, pic_baru='Andi',
        )
        process_asset_transfer(trf)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.lokasi_aset, self.lok2)
        self.assertEqual(self.aset.pic, 'Andi')

        reverse_asset_transfer(trf)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.lokasi_aset, self.lok1)
        self.assertEqual(self.aset.departemen, self.dept)
        self.assertEqual(self.aset.pic, 'Budi')


class TransferAntarEBTests(TestCase):
    def setUp(self):
        base_setup(self)
        # akun aset harus dapat di-resolve (item.coa_account)
        self.akun_aset = Akun.objects.create(kode_akun='1.2.1', nama='Mesin')
        self.akun_akum = Akun.objects.create(kode_akun='1.2.7.1', nama='Akum Penyusutan Mesin')
        self.akun_antar = Akun.objects.create(kode_akun='1.1.9', nama='RK Antar Entitas')
        self.item.coa_account = self.akun_aset
        self.item.save()

    def test_antar_eb_dual_journal_balanced(self):
        from apps.aset_tetap.services import process_asset_transfer
        # aset: HP 100jt, akumulasi 20jt, nilai buku 80jt
        trf = AssetTransfer.objects.create(
            aset=self.aset, jenis='antar_eb',
            eb_tujuan=self.eb2, akun_antar_entitas=self.akun_antar,
            akun_akumulasi=self.akun_akum,
        )
        process_asset_transfer(trf)
        h_asal = trf.jurnal_header_asal
        h_tujuan = trf.jurnal_header_tujuan
        # tiap jurnal balance
        for h in (h_asal, h_tujuan):
            d = sum(x.debit for x in h.details.all())
            k = sum(x.kredit for x in h.details.all())
            self.assertEqual(d, k)
        # EB berbeda
        self.assertEqual(h_asal.entitas_bisnis, self.eb)
        self.assertEqual(h_tujuan.entitas_bisnis, self.eb2)
        # akun antar-entitas saling hapus: asal debit 80jt, tujuan kredit 80jt
        self.assertEqual(h_asal.details.get(akun=self.akun_antar).debit, Decimal('80000000'))
        self.assertEqual(h_tujuan.details.get(akun=self.akun_antar).kredit, Decimal('80000000'))
        # aset pindah EB
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.entitas_bisnis, self.eb2)

    def test_antar_eb_requires_akun_antar(self):
        from apps.aset_tetap.services import process_asset_transfer
        trf = AssetTransfer.objects.create(aset=self.aset, jenis='antar_eb', eb_tujuan=self.eb2, akun_akumulasi=self.akun_akum)
        with self.assertRaises(ValueError):
            process_asset_transfer(trf)

    def test_antar_eb_negative_nilai_buku_raises(self):
        from apps.aset_tetap.services import process_asset_transfer
        # akumulasi_penyusutan (150jt) > harga_perolehan * quantity (100jt) -> nilai_buku negatif
        self.aset.akumulasi_penyusutan = Decimal('150000000')
        self.aset.save()
        trf = AssetTransfer.objects.create(
            aset=self.aset, jenis='antar_eb', eb_tujuan=self.eb2,
            akun_antar_entitas=self.akun_antar, akun_akumulasi=self.akun_akum,
        )
        with self.assertRaises(ValueError):
            process_asset_transfer(trf)

    def test_antar_eb_reverse(self):
        from apps.aset_tetap.services import process_asset_transfer, reverse_asset_transfer
        trf = AssetTransfer.objects.create(
            aset=self.aset, jenis='antar_eb', eb_tujuan=self.eb2,
            akun_antar_entitas=self.akun_antar, akun_akumulasi=self.akun_akum,
        )
        process_asset_transfer(trf)
        reverse_asset_transfer(trf)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.entitas_bisnis, self.eb)
        self.assertEqual(JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-TRF-').count(), 0)


class RevaluationTests(TestCase):
    def setUp(self):
        base_setup(self)
        self.akun_aset = Akun.objects.create(kode_akun='1.2.1', nama='Mesin')
        self.akun_akum = Akun.objects.create(kode_akun='1.2.7.1', nama='Akum Penyusutan')
        self.akun_surplus = Akun.objects.create(kode_akun='3.2.1', nama='Surplus Revaluasi')
        self.akun_rugi = Akun.objects.create(kode_akun='5.9.9', nama='Rugi Revaluasi')
        self.item.coa_account = self.akun_aset
        self.item.save()

    def test_eliminasi_kenaikan_sets_nilai_buku(self):
        from apps.aset_tetap.services import process_asset_revaluation
        # nilai buku lama 80jt, nilai wajar 120jt -> selisih +40jt
        rev = AssetRevaluation.objects.create(
            aset=self.aset, nilai_wajar_baru=Decimal('120000000'),
            metode_revaluasi='eliminasi',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        header = process_asset_revaluation(rev)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.nilai_buku, Decimal('120000000'))
        self.assertEqual(self.aset.akumulasi_penyusutan, Decimal('0'))
        d = sum(x.debit for x in header.details.all())
        k = sum(x.kredit for x in header.details.all())
        self.assertEqual(d, k)
        self.assertEqual(header.details.get(akun=self.akun_surplus).kredit, Decimal('40000000'))

    def test_eliminasi_penurunan_uses_rugi(self):
        from apps.aset_tetap.services import process_asset_revaluation
        # nilai buku lama 80jt, nilai wajar 50jt -> selisih -30jt
        rev = AssetRevaluation.objects.create(
            aset=self.aset, nilai_wajar_baru=Decimal('50000000'),
            metode_revaluasi='eliminasi',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        header = process_asset_revaluation(rev)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.nilai_buku, Decimal('50000000'))
        self.assertEqual(header.details.get(akun=self.akun_rugi).debit, Decimal('30000000'))

    def test_default_metode_follows_sak_emkm_warning(self):
        from apps.aset_tetap.services import default_metode_revaluasi, revaluation_warning
        self.eb.standar_akuntansi = 'sak_emkm'
        self.eb.save()
        self.assertEqual(default_metode_revaluasi(self.eb), 'eliminasi')
        self.assertIn('EMKM', revaluation_warning(self.eb))

    def test_reverse_revaluation(self):
        from apps.aset_tetap.services import process_asset_revaluation, reverse_asset_revaluation
        rev = AssetRevaluation.objects.create(
            aset=self.aset, nilai_wajar_baru=Decimal('120000000'),
            metode_revaluasi='eliminasi',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        process_asset_revaluation(rev)
        reverse_asset_revaluation(rev)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.harga_perolehan, Decimal('100000000'))
        self.assertEqual(self.aset.akumulasi_penyusutan, Decimal('20000000'))
        self.assertEqual(JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-REV-').count(), 0)

    def test_proporsional_balanced(self):
        from apps.aset_tetap.services import process_asset_revaluation
        # nb lama 80jt, nilai wajar 100jt -> rasio 1.25; HP 100->125jt, akum 20->25jt, selisih +20jt
        rev = AssetRevaluation.objects.create(
            aset=self.aset, nilai_wajar_baru=Decimal('100000000'),
            metode_revaluasi='proporsional',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        header = process_asset_revaluation(rev)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.total_value, Decimal('125000000'))
        self.assertEqual(self.aset.akumulasi_penyusutan, Decimal('25000000'))
        self.assertEqual(self.aset.nilai_buku, Decimal('100000000'))
        self.assertEqual(sum(x.debit for x in header.details.all()),
                         sum(x.kredit for x in header.details.all()))

    def test_proporsional_penurunan(self):
        from apps.aset_tetap.services import process_asset_revaluation
        # nb lama 80jt, nilai wajar 40jt -> rasio 0.5; HP 100->50jt, akum 20->10jt, selisih -40jt
        rev = AssetRevaluation.objects.create(
            aset=self.aset, nilai_wajar_baru=Decimal('40000000'),
            metode_revaluasi='proporsional',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        header = process_asset_revaluation(rev)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.total_value, Decimal('50000000'))
        self.assertEqual(self.aset.akumulasi_penyusutan, Decimal('10000000'))
        self.assertEqual(self.aset.nilai_buku, Decimal('40000000'))
        self.assertEqual(sum(x.debit for x in header.details.all()),
                         sum(x.kredit for x in header.details.all()))
        self.assertEqual(header.details.get(akun=self.akun_rugi).debit, Decimal('40000000'))

    def test_no_change_raises_error(self):
        from apps.aset_tetap.services import process_asset_revaluation
        # Fresh asset, never depreciated: nilai_buku == harga_perolehan.
        aset_baru = AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb,
            quantity=1, harga_perolehan=Decimal('100000000'),
            akumulasi_penyusutan=Decimal('0'),
        )
        rev = AssetRevaluation.objects.create(
            aset=aset_baru, nilai_wajar_baru=aset_baru.nilai_buku,
            metode_revaluasi='eliminasi',
            akun_akumulasi=self.akun_akum, akun_surplus_revaluasi=self.akun_surplus,
            akun_rugi_revaluasi=self.akun_rugi,
        )
        with self.assertRaises(ValueError):
            process_asset_revaluation(rev)
