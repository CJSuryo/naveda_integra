"""Tests Fase 8 — asset register."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import (
    TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3,
)
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from apps.aset_tetap.models import AsetTetapRecord, LokasiAset
from apps.aset_tetap import reports


class AssetRegisterTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.kat = KategoriItem.objects.create(nama='Kendaraan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Truk', tipe_item='ATP', kategori=self.kat)

    def _mk(self, harga, akum, status='aktif', **extra):
        kwargs = dict(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('1'),
            harga_perolehan=Decimal(harga), akumulasi_penyusutan=Decimal(akum),
            tanggal_perolehan=date(2026, 1, 1), status=status)
        kwargs.update(extra)
        return AsetTetapRecord.objects.create(**kwargs)

    def test_register_rows_and_subtotal(self):
        self._mk('100000000', '20000000')
        self._mk('50000000', '10000000')
        result = reports.asset_register({self.eb.pk}, group_by='kategori')
        self.assertEqual(len(result['rows']), 2)
        sub = result['subtotals']['Kendaraan']
        self.assertEqual(sub['harga_perolehan'], Decimal('150000000'))
        self.assertEqual(sub['nilai_buku'], Decimal('120000000'))
        self.assertEqual(result['grand_total']['nilai_buku'], Decimal('120000000'))

    def test_register_filters_status(self):
        self._mk('100000000', '0', status='aktif')
        self._mk('50000000', '0', status='dilepas')
        result = reports.asset_register({self.eb.pk}, status='aktif')
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['harga_perolehan'], Decimal('100000000'))

    def test_register_group_by_lokasi_null_fallback(self):
        lokasi = LokasiAset.objects.create(kode='LOK-01', nama='Gudang Utama')
        self._mk('100000000', '20000000', lokasi_aset=lokasi)
        self._mk('50000000', '10000000')  # lokasi_aset kosong -> fallback label
        result = reports.asset_register({self.eb.pk}, group_by='lokasi')
        self.assertEqual(set(result['subtotals'].keys()), {'Gudang Utama', '(Tanpa Lokasi)'})
        self.assertEqual(
            result['subtotals']['Gudang Utama']['harga_perolehan'], Decimal('100000000'))
        self.assertEqual(
            result['subtotals']['(Tanpa Lokasi)']['harga_perolehan'], Decimal('50000000'))

    def test_register_group_by_departemen_null_fallback(self):
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Divisi Ops')
        lv3 = EntitasBisnisLv3.objects.create(parent_lv2=lv2, nama='Departemen IT')
        self._mk('100000000', '20000000', departemen=lv3)
        self._mk('50000000', '10000000')  # departemen kosong -> fallback label
        result = reports.asset_register({self.eb.pk}, group_by='departemen')
        self.assertEqual(
            set(result['subtotals'].keys()), {'Departemen IT', '(Tanpa Departemen)'})
        self.assertEqual(
            result['subtotals']['Departemen IT']['harga_perolehan'], Decimal('100000000'))
        self.assertEqual(
            result['subtotals']['(Tanpa Departemen)']['harga_perolehan'], Decimal('50000000'))

    def test_register_filters_kategori_id(self):
        kat2 = KategoriItem.objects.create(nama='Elektronik')
        item2 = ItemMasterPurchase.objects.create(
            nama='Laptop', tipe_item='ATP', kategori=kat2)
        self._mk('100000000', '0')  # kategori self.kat (Kendaraan)
        AsetTetapRecord.objects.create(
            item=item2, entitas_bisnis=self.eb, quantity=Decimal('1'),
            harga_perolehan=Decimal('20000000'), akumulasi_penyusutan=Decimal('0'),
            tanggal_perolehan=date(2026, 1, 1), status='aktif')
        result = reports.asset_register({self.eb.pk}, kategori_id=kat2.pk)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['harga_perolehan'], Decimal('20000000'))
        self.assertEqual(result['rows'][0]['kategori'], 'Elektronik')

    def test_register_filters_lokasi_id(self):
        lokasi = LokasiAset.objects.create(kode='LOK-02', nama='Kantor Pusat')
        self._mk('100000000', '0', lokasi_aset=lokasi)
        self._mk('50000000', '0')  # tanpa lokasi
        result = reports.asset_register({self.eb.pk}, lokasi_id=lokasi.pk)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['harga_perolehan'], Decimal('100000000'))

    def test_register_filters_departemen_id(self):
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Divisi Keuangan')
        lv3 = EntitasBisnisLv3.objects.create(parent_lv2=lv2, nama='Departemen Finance')
        self._mk('100000000', '0', departemen=lv3)
        self._mk('50000000', '0')  # tanpa departemen
        result = reports.asset_register({self.eb.pk}, departemen_id=lv3.pk)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['harga_perolehan'], Decimal('100000000'))

    def test_register_filters_pic_icontains(self):
        self._mk('100000000', '0', pic='Budi Santoso')
        self._mk('50000000', '0', pic='Ani')
        result = reports.asset_register({self.eb.pk}, pic='Budi')
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['pic'], 'Budi Santoso')
