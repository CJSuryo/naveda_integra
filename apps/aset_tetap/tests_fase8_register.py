"""Tests Fase 8 — asset register."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from apps.aset_tetap.models import AsetTetapRecord
from apps.aset_tetap import reports


class AssetRegisterTests(TestCase):
    def setUp(self):
        self.tipe = TipeEntitas.objects.create(nama='PT')
        self.eb = EntitasBisnis.objects.create(nama='PT A', tipe_entitas=self.tipe)
        self.kat = KategoriItem.objects.create(nama='Kendaraan')
        self.item = ItemMasterPurchase.objects.create(
            nama='Truk', tipe_item='ATP', kategori=self.kat)

    def _mk(self, harga, akum, status='aktif'):
        return AsetTetapRecord.objects.create(
            item=self.item, entitas_bisnis=self.eb, quantity=Decimal('1'),
            harga_perolehan=Decimal(harga), akumulasi_penyusutan=Decimal(akum),
            tanggal_perolehan=date(2026, 1, 1), status=status)

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
