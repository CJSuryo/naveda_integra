"""Tests Fase 7 — fixed asset lifecycle."""
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import (
    TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
)
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from apps.master_data.models import Akun
from apps.aset_tetap.models import AsetTetapRecord, LokasiAset
from apps.aset_tetap.services import calculate_depreciation


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
