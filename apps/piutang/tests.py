from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun

from .models import PiutangHeader, PiutangDetail, PiutangAuditLog
from .services import create_manual_piutang, create_piutang_payment


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


from .services import get_piutang_aging


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
