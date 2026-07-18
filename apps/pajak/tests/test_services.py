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


class SyncPajakTest(TestCase):
    def _make_accounts(self):
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
        return akun_pajak, akun_lawan

    def _make_tarif(self):
        from apps.pajak.models import TarifPajak
        TarifPajak.objects.create(
            jenis_pajak='ppn_umum', nama='PPN Umum',
            tarif_persen=Decimal('12.0000'), faktor_dpp=Decimal('0.916667'),
            berlaku_mulai=date(2025, 1, 1),
        )

    def test_sync_pajak_creates_draft_record(self):
        from apps.pajak.services import sync_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()

        class FakeKP:
            pk = 42
            tax = None
            entitas_bisnis = None

        pt = sync_pajak(
            source_type='pendapatan_kp',
            source_obj=FakeKP(),
            dpp=Decimal('10000000'),
            tanggal=date(2026, 6, 15),
            jenis_pajak='ppn_umum',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
            sifat_pajak='potong_pungut',
        )
        self.assertEqual(pt.status, 'draft')
        self.assertEqual(pt.source_type, 'pendapatan_kp')
        self.assertEqual(pt.source_id, 42)
        self.assertEqual(pt.masa_pajak, date(2026, 6, 1))
        self.assertFalse(pt.is_overridden)
        self.assertTrue(MasaPajak.objects.filter(tahun=2026, bulan=6).exists())

    def test_sync_pajak_locked_masa_raises(self):
        from apps.pajak.services import sync_pajak
        from apps.pajak.models import MasaPajak
        from apps.pajak.exceptions import MasaPajakTerkunciError
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()
        MasaPajak.objects.create(tahun=2026, bulan=6, status='locked')

        class FakeKP:
            pk = 1
            tax = None
            entitas_bisnis = None

        with self.assertRaises(MasaPajakTerkunciError):
            sync_pajak(
                source_type='pendapatan_kp',
                source_obj=FakeKP(),
                dpp=Decimal('10000000'),
                tanggal=date(2026, 6, 1),
                jenis_pajak='ppn_umum',
                akun_pajak=akun_pajak,
                akun_lawan=akun_lawan,
                sifat_pajak='potong_pungut',
            )

    def test_sync_pajak_manual_tax_sets_overridden(self):
        from apps.pajak.services import sync_pajak
        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()

        class FakeKP:
            pk = 7
            tax = Decimal('500000')
            entitas_bisnis = None

        pt = sync_pajak(
            source_type='pendapatan_kp',
            source_obj=FakeKP(),
            dpp=Decimal('5000000'),
            tanggal=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
            sifat_pajak='potong_pungut',
        )
        self.assertTrue(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('500000'))

    def test_sync_pajak_override_amount_takes_priority(self):
        """override_amount param bypasses compute_pajak and source_obj.tax."""
        from apps.pajak.services import sync_pajak

        self._make_tarif()
        akun_pajak, akun_lawan = self._make_accounts()

        class FakeKP:
            pk = 99999
            tax = Decimal('99')        # would be used if override_amount not present
            entitas_bisnis = None

        result = sync_pajak(
            source_type='test_override',
            source_obj=FakeKP(),
            dpp=Decimal('500000'),
            tanggal=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            akun_pajak=akun_pajak,
            akun_lawan=akun_lawan,
            sifat_pajak='potong_pungut',
            override_amount=Decimal('50000'),
        )
        self.assertEqual(result.jumlah_pajak, Decimal('50000'))
        self.assertTrue(result.is_overridden)
        # Override menyimpan tarif efektif (50.000 / 500.000 = 10%), bukan 0.
        self.assertEqual(result.tarif_persen, Decimal('10.0000'))


class PostJurnalPajakTest(TestCase):
    def _make_pt(self, sifat_pajak, jumlah=Decimal('1100000')):
        from apps.pajak.models import PajakTransaksi
        from apps.master_data.models import Akun
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
        return PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1),
            jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=jumlah,
            sifat_pajak=sifat_pajak,
            status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )

    def test_post_jurnal_potong_pungut_direction(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        pt = self._make_pt('potong_pungut')
        jh = post_jurnal_pajak(pt)
        details = list(JurnalDetail.objects.filter(jurnal_header=jh))
        self.assertEqual(len(details), 2)
        debit_detail  = next(d for d in details if d.debit  > 0)
        kredit_detail = next(d for d in details if d.kredit > 0)
        self.assertEqual(debit_detail.akun,  pt.akun_lawan)
        self.assertEqual(kredit_detail.akun, pt.akun_pajak)

    def test_post_jurnal_prepaid_direction(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        pt = self._make_pt('prepaid')
        jh = post_jurnal_pajak(pt)
        details = list(JurnalDetail.objects.filter(jurnal_header=jh))
        debit_detail  = next(d for d in details if d.debit  > 0)
        kredit_detail = next(d for d in details if d.kredit > 0)
        self.assertEqual(debit_detail.akun,  pt.akun_pajak)
        self.assertEqual(kredit_detail.akun, pt.akun_lawan)

    def test_post_jurnal_rounding_two_decimal_places(self):
        from apps.pajak.services import post_jurnal_pajak
        from apps.jurnal.models import JurnalDetail
        pt = self._make_pt('potong_pungut', jumlah=Decimal('1100000.5678'))
        jh = post_jurnal_pajak(pt)
        debit = JurnalDetail.objects.filter(jurnal_header=jh, debit__gt=0).first()
        self.assertEqual(debit.debit, Decimal('1100000.57'))

    def test_post_jurnal_nomor_starts_with_trx_paj(self):
        from apps.pajak.services import post_jurnal_pajak
        pt = self._make_pt('potong_pungut')
        jh = post_jurnal_pajak(pt)
        self.assertTrue(jh.nomor_transaksi.startswith('TRX-PAJ'))

    def test_confirm_pajak_sets_final_and_links_jurnal(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import MasaPajak
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        pt = self._make_pt('potong_pungut')
        jh = confirm_pajak(pt)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'final')
        self.assertEqual(pt.jurnal_header, jh)

    def test_confirm_pajak_locked_masa_raises(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import MasaPajak
        from apps.pajak.exceptions import MasaPajakTerkunciError
        MasaPajak.objects.create(tahun=2026, bulan=6, status='locked')
        pt = self._make_pt('potong_pungut')
        with self.assertRaises(MasaPajakTerkunciError):
            confirm_pajak(pt)


class BatalPajakTest(TestCase):
    def _make_confirmed_pt(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        from apps.master_data.models import Akun
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1), jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000'),
            sifat_pajak='potong_pungut', status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )
        confirm_pajak(pt)
        pt.refresh_from_db()
        return pt

    def test_batal_pajak_sets_dibatalkan(self):
        from apps.pajak.services import batal_pajak
        pt = self._make_confirmed_pt()
        batal_pajak(pt)
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'dibatalkan')

    def test_batal_pajak_creates_reversal_journal(self):
        from apps.pajak.services import batal_pajak
        from apps.jurnal.models import JurnalHeader, JurnalDetail
        pt = self._make_confirmed_pt()
        original_jh = pt.jurnal_header
        original_debit = JurnalDetail.objects.filter(jurnal_header=original_jh, debit__gt=0).first()
        batal_pajak(pt)
        reversal_jh = JurnalHeader.objects.filter(
            nomor_transaksi__startswith='TRX-PAJ'
        ).exclude(pk=original_jh.pk).first()
        self.assertIsNotNone(reversal_jh)
        reversal_kredit = JurnalDetail.objects.filter(
            jurnal_header=reversal_jh, kredit__gt=0, akun=original_debit.akun
        ).first()
        self.assertIsNotNone(reversal_kredit)
        self.assertEqual(reversal_kredit.kredit, original_debit.debit)


class OverridePajakTest(TestCase):
    def _make_confirmed_pt(self):
        from apps.pajak.services import confirm_pajak
        from apps.pajak.models import PajakTransaksi, MasaPajak
        from apps.master_data.models import Akun
        MasaPajak.objects.create(tahun=2026, bulan=6, status='open')
        akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
        akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
        pt = PajakTransaksi.objects.create(
            source_type='pendapatan_kp', source_id=1,
            masa_pajak=date(2026, 6, 1), jenis_pajak='ppn_umum',
            dpp=Decimal('10000000'), tarif_persen=Decimal('12.0000'),
            jumlah_pajak=Decimal('1100000'),
            sifat_pajak='potong_pungut', status='draft',
            akun_pajak=akun_pajak, akun_lawan=akun_lawan,
        )
        confirm_pajak(pt)
        pt.refresh_from_db()
        return pt

    def test_override_updates_amount_and_posts_new_journal(self):
        from apps.pajak.services import override_pajak
        from apps.jurnal.models import JurnalHeader
        pt = self._make_confirmed_pt()
        original_jh_pk = pt.jurnal_header.pk
        pt2 = override_pajak(pt, Decimal('900000'), modified_by=None)
        pt2.refresh_from_db()
        self.assertEqual(pt2.jumlah_pajak, Decimal('900000'))
        self.assertTrue(pt2.is_overridden)
        self.assertEqual(pt2.status, 'final')
        self.assertNotEqual(pt2.jurnal_header.pk, original_jh_pk)


class ConfirmPajakReverseTest(TestCase):
    """confirm_pajak(reverse=True) membalik arah jurnal — untuk nota retur."""

    def _trx(self):
        from datetime import date
        from decimal import Decimal
        from apps.pajak.models import PajakTransaksi
        from apps.master_data.models import Akun
        self.akun_pajak = Akun.objects.create(kategori_id='kewajiban', nama='PPN Keluaran', kode_akun='2.1.4')
        self.akun_lawan = Akun.objects.create(kategori_id='aset', nama='Piutang PPN', kode_akun='1.2.4')
        return PajakTransaksi.objects.create(
            source_type='retur_customer_item', source_id=1,
            masa_pajak=date(2026, 6, 1), jenis_pajak='ppn_umum',
            dpp=Decimal('1000000'), tarif_persen=Decimal('11'),
            jumlah_pajak=Decimal('110000'), sifat_pajak='potong_pungut',
            status='draft', akun_pajak=self.akun_pajak, akun_lawan=self.akun_lawan)

    def test_reverse_swaps_debit_kredit(self):
        from apps.pajak.services import confirm_pajak
        from decimal import Decimal
        pt = self._trx()
        jh = confirm_pajak(pt, reverse=True)
        details = list(jh.details.all())
        # normal potong_pungut = Dr akun_lawan / Cr akun_pajak; reversed = Dr akun_pajak / Cr akun_lawan
        debited = next(d for d in details if d.debit > 0)
        credited = next(d for d in details if d.kredit > 0)
        self.assertEqual(debited.akun_id, self.akun_pajak.pk)   # PPN Keluaran didebit (berkurang)
        self.assertEqual(credited.akun_id, self.akun_lawan.pk)
        self.assertEqual(debited.debit, Decimal('110000.00'))
        pt.refresh_from_db()
        self.assertEqual(pt.status, 'final')

    def test_default_direction_unchanged(self):
        from apps.pajak.services import confirm_pajak
        pt = self._trx()
        jh = confirm_pajak(pt)  # reverse default False
        details = list(jh.details.all())
        debited = next(d for d in details if d.debit > 0)
        self.assertEqual(debited.akun_id, self.akun_lawan.pk)   # arah asli tak berubah
