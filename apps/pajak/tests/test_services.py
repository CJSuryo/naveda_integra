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


class SeedDataTest(TestCase):
    """These tests run after data migration — relies on test runner applying all migrations."""
    fixtures = []  # no fixtures; seed comes from data migration

    def test_tarif_ppn_umum_exists(self):
        from apps.pajak.models import TarifPajak
        from decimal import Decimal
        t = TarifPajak.objects.get(jenis_pajak='ppn_umum', berlaku_sampai__isnull=True)
        self.assertEqual(t.tarif_persen, Decimal('12.0000'))
        self.assertAlmostEqual(float(t.faktor_dpp), 11/12, places=4)

    def test_tarif_pph_23_jasa_exists(self):
        from apps.pajak.models import TarifPajak
        t = TarifPajak.objects.get(jenis_pajak='pph_23_jasa', berlaku_sampai__isnull=True)
        self.assertEqual(t.tarif_persen, Decimal('2.0000'))
        self.assertEqual(t.faktor_dpp, Decimal('1.000000'))

    def test_bracket_ppn_op_five_layers(self):
        from apps.pajak.models import BracketPPhOP
        self.assertEqual(BracketPPhOP.objects.count(), 5)

    def test_bracket_top_layer_null_atas(self):
        from apps.pajak.models import BracketPPhOP
        top = BracketPPhOP.objects.order_by('-batas_bawah').first()
        self.assertIsNone(top.batas_atas)
        self.assertEqual(top.tarif_persen, Decimal('35.00'))


class GetTarifRecordTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa',
            nama='PPh 23 Jasa',
            tarif_persen=Decimal('2.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa',
            nama='PPh 23 Jasa (lama)',
            tarif_persen=Decimal('2.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2020, 1, 1),
            berlaku_sampai=date(2024, 12, 31),
        )

    def test_get_tarif_returns_active_record(self):
        from apps.pajak.services import get_tarif_record
        t = get_tarif_record('pph_23_jasa', date(2026, 1, 1))
        self.assertEqual(t.berlaku_mulai, date(2025, 1, 1))

    def test_get_tarif_raises_if_not_found(self):
        from apps.pajak.services import get_tarif_record
        from apps.pajak.exceptions import TarifPajakTidakDitemukan
        with self.assertRaises(TarifPajakTidakDitemukan):
            get_tarif_record('ppn_bm', date(2019, 1, 1))

    def test_get_tarif_historical_date(self):
        from apps.pajak.services import get_tarif_record
        t = get_tarif_record('pph_23_jasa', date(2023, 6, 1))
        self.assertEqual(t.berlaku_mulai, date(2020, 1, 1))


class ComputePajakPPNTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='ppn_umum',
            nama='PPN Umum',
            tarif_persen=Decimal('12.0000'),
            faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='ppn_ekspor',
            nama='PPN Ekspor',
            tarif_persen=Decimal('0.0000'),
            faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )

    def test_ppn_umum_effective_11_percent(self):
        from apps.pajak.services import compute_pajak
        result = compute_pajak('ppn_umum', Decimal('10000000'), date(2026, 1, 1))
        self.assertIn('jumlah_pajak', result)
        self.assertIn('dpp_efektif', result)
        self.assertIn('tarif_persen', result)
        self.assertAlmostEqual(float(result['jumlah_pajak']), 10_000_000 * 11 / 12 * 0.12, places=0)

    def test_ppn_ekspor_zero(self):
        from apps.pajak.services import compute_pajak
        result = compute_pajak('ppn_ekspor', Decimal('5000000'), date(2026, 1, 1))
        self.assertEqual(result['jumlah_pajak'], Decimal('0'))


class ComputePajakPPhTest(TestCase):
    def setUp(self):
        from apps.pajak.models import TarifPajak, BracketPPhOP
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa', nama='PPh 23 Jasa',
            tarif_persen=Decimal('2.0000'), faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        TarifPajak.objects.create(
            jenis_pajak='pph_21_bukan_pegawai', nama='PPh 21 Bukan Pegawai',
            tarif_persen=Decimal('0.0000'), faktor_dpp=Decimal('1.000000'),
            berlaku_mulai=date(2025, 1, 1),
        )
        # Use berlaku_mulai later than the seed migration (2022-01-01) so that
        # hitung_progresif picks only these brackets, not the seeded ones.
        BracketPPhOP.objects.bulk_create([
            BracketPPhOP(batas_bawah=Decimal('0'),          batas_atas=Decimal('60000000'),   tarif_persen=Decimal('5.00'),  berlaku_mulai=date(2026, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('60000001'),   batas_atas=Decimal('250000000'),  tarif_persen=Decimal('15.00'), berlaku_mulai=date(2026, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('250000001'),  batas_atas=Decimal('500000000'),  tarif_persen=Decimal('25.00'), berlaku_mulai=date(2026, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('500000001'),  batas_atas=Decimal('5000000000'), tarif_persen=Decimal('30.00'), berlaku_mulai=date(2026, 1, 1)),
            BracketPPhOP(batas_bawah=Decimal('5000000001'), batas_atas=None,                  tarif_persen=Decimal('35.00'), berlaku_mulai=date(2026, 1, 1)),
        ])

    def test_pph_23_jasa_flat_rate(self):
        from apps.pajak.services import compute_pajak
        result = compute_pajak('pph_23_jasa', Decimal('5000000'), date(2026, 1, 1))
        self.assertAlmostEqual(float(result['jumlah_pajak']), 100000.0, places=2)

    def test_pph_21_bukan_pegawai_single_bracket(self):
        from apps.pajak.services import compute_pajak
        # bruto=10_000_000 → PKP=5_000_000 → entirely in 5% bracket → tax=250_000
        result = compute_pajak('pph_21_bukan_pegawai', Decimal('10000000'), date(2026, 1, 1))
        self.assertAlmostEqual(float(result['jumlah_pajak']), 250000.0, places=2)

    def test_pph_21_bukan_pegawai_two_brackets(self):
        from apps.pajak.services import compute_pajak
        # bruto=300_000_000 → PKP=150_000_000
        # Layer 1 (0..60_000_000): ~60_000_001 × 5% ≈ 3_000_000
        # Layer 2 (60_000_001..): ~89_999_999 × 15% ≈ 13_499_999.85
        # Total ≈ 16_500_000
        result = compute_pajak('pph_21_bukan_pegawai', Decimal('300000000'), date(2026, 1, 1))
        self.assertAlmostEqual(float(result['jumlah_pajak']), 16_500_000.0, places=0)
