from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.pajak.exceptions import TarifPajakTidakDitemukan, MasaPajakTerkunciError, PajakStatusError


class ExceptionSmokeTest(TestCase):
    def test_exceptions_importable(self):
        self.assertTrue(issubclass(TarifPajakTidakDitemukan, Exception))
        self.assertTrue(issubclass(MasaPajakTerkunciError, Exception))
        self.assertTrue(issubclass(PajakStatusError, Exception))


class TarifPajakModelTest(TestCase):
    def test_create_tarif_pajak(self):
        from apps.pajak.models import TarifPajak
        t = TarifPajak.objects.create(
            jenis_pajak='ppn_umum',
            nama='PPN Umum',
            tarif_persen=Decimal('12.0000'),
            faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )
        self.assertEqual(t.jenis_pajak, 'ppn_umum')
        self.assertIsNone(t.berlaku_sampai)

    def test_create_masa_pajak_unique(self):
        from apps.pajak.models import MasaPajak
        mp, created = MasaPajak.objects.get_or_create(tahun=2026, bulan=6)
        self.assertTrue(created)
        mp2, created2 = MasaPajak.objects.get_or_create(tahun=2026, bulan=6)
        self.assertFalse(created2)
        self.assertEqual(mp.pk, mp2.pk)

    def test_create_pajak_transaksi(self):
        from apps.pajak.models import TarifPajak, MasaPajak, PajakTransaksi
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp',
            source_id=1,
            masa_pajak=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            dpp=Decimal('10000000.0000'),
            tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000.0000'),
            sifat_pajak='potong_pungut',
            status='draft',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
        )
        self.assertEqual(pt.status, 'draft')
        self.assertFalse(pt.is_overridden)
        self.assertIsNone(pt.jurnal_header)
