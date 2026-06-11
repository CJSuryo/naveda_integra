from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun

from .models import PiutangHeader, PiutangDetail, PiutangAuditLog
from .services import create_manual_piutang, create_piutang_payment
from apps.piutang.services import compute_penyisihan_for_piutang
from apps.piutang.models import PenyisihanRateConfig


def make_fixtures():
    tipe = TipeEntitas.objects.create(nama='Pelanggan')
    eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang', kode_akun='1.2.1')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Jasa', kode_akun='4.1.1')
    return {
        'tipe': tipe, 'eb': eb,
        'coa_piutang': coa_piutang, 'coa_kas': coa_kas, 'coa_pendapatan': coa_pendapatan,
    }


class CreateManualPiutangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_header_with_correct_fields(self):
        piutang = create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='PT Klien',
            deskripsi='Test piutang',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 7, 7),
            details=[{'deskripsi': 'Jasa konsultasi', 'jumlah': Decimal('1000000')}],
        )
        self.assertIsNotNone(piutang.pk)
        self.assertTrue(piutang.nomor_piutang.startswith('TRX-PIU-'))
        self.assertEqual(piutang.jumlah_pokok, Decimal('1000000'))
        self.assertEqual(piutang.status, 'draft')
        self.assertEqual(piutang.details.count(), 1)

    def test_creates_audit_log(self):
        create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='',
            deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=None,
            details=[{'deskripsi': 'Item', 'jumlah': Decimal('500000')}],
        )
        self.assertEqual(PiutangAuditLog.objects.filter(action='CREATED').count(), 1)

    def test_raises_if_no_details(self):
        with self.assertRaises(ValueError):
            create_manual_piutang(
                tanggal=date(2026, 6, 7), entitas_bisnis=self.f['eb'],
                debitur='', deskripsi='', coa_piutang_account=self.f['coa_piutang'],
                jatuh_tempo=None, details=[],
            )

    def test_auto_number_increments(self):
        p1 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='X',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'A', 'jumlah': Decimal('100')}],
        )
        p2 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='Y',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'B', 'jumlah': Decimal('200')}],
        )
        n1 = int(p1.nomor_piutang.rsplit('-', 1)[1])
        n2 = int(p2.nomor_piutang.rsplit('-', 1)[1])
        self.assertEqual(n2, n1 + 1)


class CreatePiutangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=self.f['eb'],
            debitur='PT Klien', deskripsi='', coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 7, 7),
            details=[{'deskripsi': 'Jasa', 'jumlah': Decimal('1000000')}],
        )
        self.piutang.status = 'open'
        self.piutang.save()

    def test_creates_penerimaan_record(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('400000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': 'TRF-001', 'catatan': ''},
        )
        self.assertEqual(self.piutang.penerimaan.count(), 1)

    def test_updates_jumlah_terbayar(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('400000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.jumlah_terbayar, Decimal('400000'))
        self.assertEqual(self.piutang.status, 'partial')

    def test_status_becomes_paid_when_fully_settled(self):
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('1000000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'tunai',
             'nomor_referensi': '', 'catatan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.status, 'paid')

    def test_raises_if_exceeds_sisa(self):
        with self.assertRaises(ValueError):
            create_piutang_payment(
                self.piutang,
                {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('2000000'),
                 'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
                 'nomor_referensi': '', 'catatan': ''},
            )

    def test_generates_journal(self):
        from apps.jurnal.models import JurnalHeader
        create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 10), 'jumlah_diterima': Decimal('500000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )
        penerimaan = self.piutang.penerimaan.first()
        self.assertIsNotNone(penerimaan.jurnal_header)
        details = penerimaan.jurnal_header.details.all()
        debits = [d for d in details if d.debit > 0]
        credits = [d for d in details if d.kredit > 0]
        self.assertEqual(len(debits), 1)
        self.assertEqual(len(credits), 1)
        self.assertEqual(debits[0].akun, self.f['coa_kas'])
        self.assertEqual(credits[0].akun, self.f['coa_piutang'])


from .services import compute_bagian_lancar, write_off_piutang, reverse_piutang_payment


class ComputeBagianLancarTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_full_amount_when_due_within_12_months(self):
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 6, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        bagian = compute_bagian_lancar(p)
        self.assertEqual(bagian, Decimal('500000'))

    def test_zero_when_due_beyond_12_months(self):
        p = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2028, 1, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        bagian = compute_bagian_lancar(p)
        self.assertEqual(bagian, Decimal('0'))


# ── Task 4: Aging bucket tests ────────────────────────────────────────────────

from apps.piutang.services import _classify_bucket, get_piutang_aging


class ClassifyBucketTest(TestCase):
    def test_future(self):
        future = date(date.today().year + 1, 1, 1)
        assert _classify_bucket(future, date.today()) == 'current'

    def test_today(self):
        assert _classify_bucket(date.today(), date.today()) == 'current'

    def test_1_day_overdue(self):
        assert _classify_bucket(date.today() - timedelta(days=1), date.today()) == '1_30'

    def test_31_days(self):
        assert _classify_bucket(date.today() - timedelta(days=31), date.today()) == '31_60'

    def test_over_365(self):
        assert _classify_bucket(date.today() - timedelta(days=400), date.today()) == 'over_365'

    def test_none_returns_current(self):
        assert _classify_bucket(None, date.today()) == 'current'


class GetPiutangAgingTest(TestCase):
    def test_returns_7_buckets(self):
        result = get_piutang_aging()
        expected_keys = {'current', '1_30', '31_60', '61_90', '91_180', '181_365', 'over_365'}
        assert set(result.keys()) == expected_keys

    def test_each_bucket_is_list(self):
        result = get_piutang_aging()
        for v in result.values():
            assert isinstance(v, list)


# ── Task 3: Schedule helpers ───────────────────────────────────────────────────

from apps.piutang.services import _add_months, compute_angsuran_schedule


class AddMonthsTest(TestCase):
    def test_simple(self):
        assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_year_rollover(self):
        assert _add_months(date(2025, 11, 30), 3) == date(2026, 2, 28)


class ComputeAngsuranScheduleTest(TestCase):
    def _make_piutang(self, jumlah_pokok, jenis_bunga='tanpa_bunga', suku_bunga=0,
                      periode='bulanan', tanggal=None, jatuh_tempo=None):
        from apps.master_data.models import Akun
        akun, _ = Akun.objects.get_or_create(
            kode_akun='1100', defaults={'nama': 'Piutang Usaha', 'kategori_id': 'aset'}
        )
        return PiutangHeader(
            nomor_piutang='TEST-001',
            tanggal=tanggal or date(2026, 1, 1),
            jatuh_tempo=jatuh_tempo or date(2026, 12, 31),
            jumlah_pokok=Decimal(str(jumlah_pokok)),
            jumlah_terbayar=Decimal('0'),
            jenis_jangka_waktu='long_term',
            jenis_bunga=jenis_bunga,
            suku_bunga=Decimal(str(suku_bunga)),
            periode_angsuran=periode,
            coa_piutang_account=akun,
            status='open',
        )

    def test_tanpa_bunga_12_bulan(self):
        p = self._make_piutang(12_000_000, tanggal=date(2026, 1, 1), jatuh_tempo=date(2026, 12, 31))
        rows = compute_angsuran_schedule(p)
        assert len(rows) == 11  # 11 monthly periods from Jan to Dec
        assert all(r['bunga'] == 0 for r in rows)
        total_pokok = sum(r['pokok'] for r in rows)
        assert total_pokok == Decimal('12000000')

    def test_no_schedule_without_jatuh_tempo(self):
        p = self._make_piutang(1_000_000, jatuh_tempo=None)
        p.jatuh_tempo = None
        assert compute_angsuran_schedule(p) == []

    def test_flat_interest(self):
        p = self._make_piutang(
            12_000_000, jenis_bunga='flat', suku_bunga=12,
            tanggal=date(2026, 1, 1), jatuh_tempo=date(2026, 12, 31),
        )
        rows = compute_angsuran_schedule(p)
        assert all(r['bunga'] > 0 for r in rows)

    def test_status_akan_datang(self):
        future = date.today().replace(year=date.today().year + 1)
        p = self._make_piutang(
            6_000_000, tanggal=date.today(), jatuh_tempo=future,
        )
        rows = compute_angsuran_schedule(p)
        assert all(r['status'] == 'akan_datang' for r in rows)

    def test_anuitas_last_row_zero_sisa_pokok(self):
        p = self._make_piutang(
            12_000_000, jenis_bunga='anuitas', suku_bunga=12,
            tanggal=date(2026, 1, 1), jatuh_tempo=date(2026, 12, 31),
        )
        rows = compute_angsuran_schedule(p)
        assert len(rows) == 11
        assert rows[-1]['sisa_pokok'] == Decimal('0')
        assert all(r['bunga'] > 0 for r in rows)


class WriteOffPiutangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.coa_beban = Akun.objects.create(
            kategori_id='beban', nama='Beban Piutang Tak Tertagih', kode_akun='6.1.1',
        )
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 1, 1), entitas_bisnis=self.f['eb'], debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=date(2026, 3, 1),
            details=[{'deskripsi': 'X', 'jumlah': Decimal('500000')}],
        )
        self.piutang.status = 'overdue'
        self.piutang.save()

    def test_creates_write_off_record(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': 'Tidak tertagih'},
        )
        self.assertTrue(hasattr(self.piutang, 'write_off'))

    def test_status_becomes_written_off(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': ''},
        )
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.status, 'written_off')

    def test_langsung_journal_dr_bad_debt_cr_piutang(self):
        write_off_piutang(
            self.piutang,
            {'tanggal': date(2026, 6, 7), 'metode': 'langsung',
             'bad_debt_account': self.coa_beban, 'alasan': ''},
        )
        wo = self.piutang.write_off
        details = wo.jurnal.details.all()
        dr = next(d for d in details if d.debit > 0)
        cr = next(d for d in details if d.kredit > 0)
        self.assertEqual(dr.akun, self.coa_beban)
        self.assertEqual(cr.akun, self.f['coa_piutang'])


class ReversePiutangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.piutang = create_manual_piutang(
            tanggal=date(2026, 6, 1), entitas_bisnis=None, debitur='X', deskripsi='',
            coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'X', 'jumlah': Decimal('1000000')}],
        )
        self.piutang.status = 'open'
        self.piutang.save()
        self.penerimaan = create_piutang_payment(
            self.piutang,
            {'tanggal_terima': date(2026, 6, 7), 'jumlah_diterima': Decimal('600000'),
             'payment_account': self.f['coa_kas'], 'metode_penerimaan': 'transfer',
             'nomor_referensi': '', 'catatan': ''},
        )

    def test_reversal_creates_counter_journal(self):
        from apps.jurnal.models import JurnalHeader
        initial_count = JurnalHeader.objects.count()
        reverse_piutang_payment(self.penerimaan)
        self.assertEqual(JurnalHeader.objects.count(), initial_count + 1)

    def test_jumlah_terbayar_reverts(self):
        reverse_piutang_payment(self.penerimaan)
        self.piutang.refresh_from_db()
        self.assertEqual(self.piutang.jumlah_terbayar, Decimal('0'))
        self.assertEqual(self.piutang.status, 'open')


# ── Task 5: compute_penyisihan_for_piutang ────────────────────────────────────

class ComputePenyisihanForPiutangTest(TestCase):
    def setUp(self):
        defaults = [
            ('current', 'Belum Jatuh Tempo', '0.00', 1),
            ('1_30', 'Lewat 1–30 Hari', '5.00', 2),
            ('31_60', 'Lewat 31–60 Hari', '15.00', 3),
            ('61_90', 'Lewat 61–90 Hari', '25.00', 4),
            ('91_180', 'Lewat 91–180 Hari', '50.00', 5),
            ('181_365', 'Lewat 181–365 Hari', '75.00', 6),
            ('over_365', 'Lewat > 365 Hari', '100.00', 7),
        ]
        for key, label, rate, urutan in defaults:
            PenyisihanRateConfig.objects.get_or_create(
                bucket_key=key, defaults={'label': label, 'rate_percent': rate, 'urutan': urutan}
            )

    def _make_piutang_db(self, jumlah_pokok, jatuh_tempo_delta_days):
        akun, _ = Akun.objects.get_or_create(
            kode_akun='1100', defaults={'nama': 'Piutang Usaha', 'kategori_id': 'aset'}
        )
        p = PiutangHeader.objects.create(
            tanggal=date.today(),
            jatuh_tempo=date.today() - timedelta(days=jatuh_tempo_delta_days),
            jumlah_pokok=Decimal(str(jumlah_pokok)),
            jumlah_terbayar=Decimal('0'),
            jenis_jangka_waktu='short_term',
            coa_piutang_account=akun,
            status='open',
        )
        return p

    def test_short_term_overdue_31_days(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=31)
        result = compute_penyisihan_for_piutang(p)
        assert result['total_penyisihan'] == Decimal('150000.00')  # 15% of 1_000_000

    def test_current_has_zero_penyisihan(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=-30)  # future
        result = compute_penyisihan_for_piutang(p)
        assert result['total_penyisihan'] == Decimal('0.00')

    def test_breakdown_has_7_entries(self):
        p = self._make_piutang_db(1_000_000, jatuh_tempo_delta_days=10)
        result = compute_penyisihan_for_piutang(p)
        assert len(result['breakdown']) == 7


# ── Task 7: compute_batch_penyisihan ─────────────────────────────────────────

from apps.piutang.services import compute_batch_penyisihan


class ComputeBatchPenyisihanTest(TestCase):
    def setUp(self):
        defaults = [
            ('current', 'Belum JT', '0.00', 1), ('1_30', '1-30', '5.00', 2),
            ('31_60', '31-60', '15.00', 3), ('61_90', '61-90', '25.00', 4),
            ('91_180', '91-180', '50.00', 5), ('181_365', '181-365', '75.00', 6),
            ('over_365', '>365', '100.00', 7),
        ]
        for key, label, rate, urutan in defaults:
            PenyisihanRateConfig.objects.get_or_create(
                bucket_key=key, defaults={'label': label, 'rate_percent': rate, 'urutan': urutan}
            )

    def test_returns_required_keys(self):
        akun, _ = Akun.objects.get_or_create(
            kode_akun='2200', defaults={'nama': 'Cad Kerugian Piutang', 'kategori_id': 'kewajiban'}
        )
        result = compute_batch_penyisihan(date.today(), akun)
        assert 'target_saldo' in result
        assert 'saldo_existing' in result
        assert 'delta' in result
        assert 'breakdown' in result
        assert 'piutang_count' in result

    def test_delta_equals_target_minus_existing(self):
        akun, _ = Akun.objects.get_or_create(
            kode_akun='2200', defaults={'nama': 'Cad Kerugian Piutang', 'kategori_id': 'kewajiban'}
        )
        result = compute_batch_penyisihan(date.today(), akun)
        assert result['delta'] == result['target_saldo'] - result['saldo_existing']


# ── Task 1: periode_label field ──────────────────────────────────────────────

from apps.piutang.models import PiutangPenyisihan
from apps.jurnal.models import JurnalHeader


class PiutangPenyisihanPeriodeLabelTest(TestCase):
    def test_periode_label_field_exists(self):
        self.assertTrue(hasattr(PiutangPenyisihan, 'periode_label'))

    def test_periode_label_blank_by_default(self):
        f = make_fixtures()
        coa_all = Akun.objects.create(kategori_id='kewajiban', nama='Cad Piutang', kode_akun='2.1.9')
        coa_exp = Akun.objects.create(kategori_id='beban', nama='Beban Penyisihan', kode_akun='6.1.9')
        jh = JurnalHeader.objects.create(
            tanggal=date(2026, 6, 1), nomor_transaksi='TEST-001',
            uraian_transaksi='Test', is_penyesuaian=True,
        )
        p = PiutangPenyisihan.objects.create(
            tanggal=date(2026, 6, 1), jenis='batch', jumlah=Decimal('100'),
            allowance_account=coa_all, expense_account=coa_exp,
            jurnal_header=jh,
        )
        self.assertEqual(p.periode_label, '')
