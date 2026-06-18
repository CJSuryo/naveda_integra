import datetime
from decimal import Decimal
from django.test import TestCase

from tests.pendapatan.factories import (
    make_user, make_header, make_pendapatan_eb, make_kp, make_akun
)
from apps.pendapatan.models import (
    JadwalPengakuan, EntriPengakuan, AsetKontrak, PendapatanHeader
)
from apps.pendapatan.services import compute_alokasi_harga, confirm_pendapatan


class ComputeAlokasiHargaTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.header = make_header(self.user)
        self.peb = make_pendapatan_eb(self.header)

    def test_single_kp_gets_full_amount(self):
        kp = make_kp(self.peb, '1000')
        result = compute_alokasi_harga(self.header)
        self.assertIn(kp.id, result)
        self.assertEqual(result[kp.id], Decimal('1000.0000'))

    def test_two_kps_proportional_allocation_sums_to_total(self):
        kp1 = make_kp(self.peb, '600')
        kp2 = make_kp(self.peb, '400')
        result = compute_alokasi_harga(self.header)
        total = sum(result.values())
        self.assertEqual(total, Decimal('1000.0000'))

    def test_rounding_no_penny_left_over(self):
        # 3 KPs of equal value — any rounding must sum to exact total
        make_kp(self.peb, '100')
        make_kp(self.peb, '100')
        make_kp(self.peb, '100')
        result = compute_alokasi_harga(self.header)
        self.assertEqual(sum(result.values()), Decimal('300.0000'))

    def test_empty_header_returns_empty_dict(self):
        result = compute_alokasi_harga(self.header)
        self.assertEqual(result, {})


class ConfirmPendapatanPointInTimeTest(TestCase):
    def setUp(self):
        self.user = make_user('confirmer')
        self.akun_kas = make_akun('1001-KAS', 'Kas')
        self.akun_pendapatan = make_akun('4001-PND', 'Pendapatan')
        self.header = make_header(self.user)  # default payment_type='cash'
        self.peb = make_pendapatan_eb(self.header, payment_account=self.akun_kas)

    def test_point_in_time_cash_creates_journal(self):
        from apps.jurnal.models import JurnalHeader
        make_kp(
            self.peb, '1000',
            recognition_type='point_in_time',
            revenue_account=self.akun_pendapatan,
        )
        confirm_pendapatan(self.header, self.user)
        self.header.refresh_from_db()
        self.assertEqual(self.header.status, 'confirmed')
        # A journal should have been created
        self.assertGreater(JurnalHeader.objects.count(), 0)

    def test_confirm_updates_harga_j(self):
        kp = make_kp(self.peb, '500', recognition_type='point_in_time',
                     revenue_account=self.akun_pendapatan)
        confirm_pendapatan(self.header, self.user)
        kp.refresh_from_db()
        self.assertEqual(kp.harga_j, Decimal('500.0000'))


class ConfirmPendapatanCreditOnePerHeaderTest(TestCase):
    """Multiple credit point_in_time KPs must produce exactly one piutang."""

    def setUp(self):
        self.user = make_user('credit_confirmer')
        self.akun_kas = make_akun('1001-CR', 'Kas Kredit')
        self.akun_pendapatan = make_akun('4001-CR', 'Pendapatan Kredit')

    def test_two_credit_pit_kps_create_exactly_one_piutang(self):
        from apps.piutang.models import PiutangHeader
        header = make_header(self.user, payment_type='credit')
        peb = make_pendapatan_eb(header, payment_account=self.akun_kas)
        make_kp(peb, '500', recognition_type='point_in_time',
                revenue_account=self.akun_pendapatan)
        make_kp(peb, '700', recognition_type='point_in_time',
                revenue_account=self.akun_pendapatan)
        confirm_pendapatan(header, self.user)
        piutang_count = PiutangHeader.objects.filter(source_pendapatan=header).count()
        self.assertEqual(piutang_count, 1)


class ConfirmPendapatanOverTimeTest(TestCase):
    def setUp(self):
        self.user = make_user('confirmer_ot')
        self.akun_kas = make_akun('1001-OT', 'Kas OT')
        self.akun_pendapatan = make_akun('4001-OT', 'Pendapatan OT')
        self.akun_liabilitas = make_akun('2101-OT', 'Liabilitas Kontrak')
        self.akun_aset_kontrak = make_akun('1201-OT', 'Aset Kontrak')

    def test_advance_payment_cash_creates_jadwal(self):
        header = make_header(self.user)
        peb = make_pendapatan_eb(header, payment_account=self.akun_kas)
        kp = make_kp(
            peb, '1200',
            recognition_type='over_time',
            revenue_account=self.akun_pendapatan,
            ot_tipe_aliran='advance_payment_cash',
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 3, 31),
            ot_liabilitas_kontrak_acct=self.akun_liabilitas,
        )
        confirm_pendapatan(header, self.user)
        self.assertTrue(JadwalPengakuan.objects.filter(kp=kp).exists())
        self.assertGreater(EntriPengakuan.objects.count(), 0)

    def test_periodic_billing_creates_jadwal_no_journal(self):
        from apps.jurnal.models import JurnalHeader
        header = make_header(self.user)
        peb = make_pendapatan_eb(header, payment_account=self.akun_kas)
        kp = make_kp(
            peb, '600',
            recognition_type='over_time',
            revenue_account=self.akun_pendapatan,
            ot_tipe_aliran='periodic_billing',
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 2, 28),
        )
        confirm_pendapatan(header, self.user)
        self.assertTrue(JadwalPengakuan.objects.filter(kp=kp).exists())
        self.assertEqual(JurnalHeader.objects.count(), 0)

    def test_performance_first_creates_aset_kontrak(self):
        header = make_header(self.user)
        peb = make_pendapatan_eb(header, payment_account=self.akun_kas)
        kp = make_kp(
            peb, '3000',
            recognition_type='over_time',
            revenue_account=self.akun_pendapatan,
            ot_tipe_aliran='performance_first',
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 6, 30),
            ot_aset_kontrak_acct=self.akun_aset_kontrak,
        )
        confirm_pendapatan(header, self.user)
        self.assertTrue(AsetKontrak.objects.filter(kp=kp).exists())


# ── Task 10: recognize_entry ──────────────────────────────────────────────────

class RecognizeEntryTest(TestCase):
    def _make_jadwal_with_entry(self, tipe_aliran, akun_liabilitas=None, akun_kas=None):
        """Helper: create a confirmed header with JadwalPengakuan + one EntriPengakuan."""
        user = make_user('recognizer_' + tipe_aliran[:4])
        akun_kas = akun_kas or make_akun('1001-RE-' + tipe_aliran[:4], 'Kas')
        akun_pendapatan = make_akun('4001-RE-' + tipe_aliran[:4], 'Pendapatan')
        akun_liabilitas = akun_liabilitas or make_akun('2101-RE-' + tipe_aliran[:4], 'Liabilitas')
        header = make_header(user)
        peb = make_pendapatan_eb(header, payment_account=akun_kas)
        kp = make_kp(
            peb, '600',
            recognition_type='over_time',
            revenue_account=akun_pendapatan,
            ot_tipe_aliran=tipe_aliran,
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 2, 28),
            ot_liabilitas_kontrak_acct=akun_liabilitas,
        )
        jadwal = JadwalPengakuan.objects.create(
            kp=kp,
            tipe_aliran=tipe_aliran,
            progress_method='straight_line',
            tanggal_mulai=datetime.date(2026, 1, 1),
            tanggal_selesai=datetime.date(2026, 2, 28),
            liabilitas_kontrak_acct=akun_liabilitas,
            nilai_total=Decimal('600'),
            nilai_diakui=Decimal('0'),
        )
        entri = EntriPengakuan.objects.create(
            jadwal=jadwal,
            tanggal_target=datetime.date(2026, 1, 31),
            nilai=Decimal('300'),
        )
        return entri, jadwal, header, user

    def test_advance_payment_marks_recognized(self):
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('advance_payment_cash')
        recognize_entry(entri.id, user)
        entri.refresh_from_db()
        self.assertEqual(entri.status, 'recognized')
        self.assertEqual(entri.nilai_diakui, Decimal('300'))

    def test_advance_payment_creates_journal(self):
        from apps.jurnal.models import JurnalHeader
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('advance_payment_cash')
        recognize_entry(entri.id, user)
        entri.refresh_from_db()
        self.assertIsNotNone(entri.jurnal_header)

    def test_recognize_updates_jadwal_nilai_diakui(self):
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('advance_payment_cash')
        recognize_entry(entri.id, user)
        jadwal.refresh_from_db()
        self.assertEqual(jadwal.nilai_diakui, Decimal('300'))

    def test_recognize_all_entries_completes_jadwal(self):
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('advance_payment_cash')
        # Set nilai_diakui close to total so this entry completes it
        jadwal.nilai_total = Decimal('300')
        jadwal.save()
        recognize_entry(entri.id, user)
        jadwal.refresh_from_db()
        self.assertEqual(jadwal.status, 'completed')

    def test_periodic_billing_marks_recognized(self):
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('periodic_billing')
        recognize_entry(entri.id, user)
        entri.refresh_from_db()
        self.assertEqual(entri.status, 'recognized')

    def test_performance_first_marks_recognized_no_journal(self):
        from apps.pendapatan.services import recognize_entry
        entri, jadwal, header, user = self._make_jadwal_with_entry('performance_first')
        recognize_entry(entri.id, user)
        entri.refresh_from_db()
        self.assertEqual(entri.status, 'recognized')
        self.assertIsNone(entri.jurnal_header)


# ── Task 11: konversi_aset_kontrak_ke_piutang ─────────────────────────────────

class KonversiAsetKontrakTest(TestCase):
    def setUp(self):
        self.user = make_user('konverter')
        self.akun_kas = make_akun('1001-KA', 'Kas Konversi')
        self.akun_pendapatan = make_akun('4001-KA', 'Pendapatan Konversi')
        self.akun_aset_kontrak = make_akun('1201-KA', 'Aset Kontrak')
        header = make_header(self.user)
        peb = make_pendapatan_eb(header, payment_account=self.akun_kas)
        kp = make_kp(
            peb, '2000',
            recognition_type='over_time',
            revenue_account=self.akun_pendapatan,
            ot_tipe_aliran='performance_first',
            ot_aset_kontrak_acct=self.akun_aset_kontrak,
        )
        self.aset = AsetKontrak.objects.create(
            kp=kp,
            tanggal=datetime.date(2026, 1, 1),
            nilai=Decimal('2000'),
            nilai_tersisa=Decimal('2000'),
        )

    def test_konversi_marks_converted(self):
        from apps.pendapatan.services import konversi_aset_kontrak_ke_piutang
        konversi_aset_kontrak_ke_piutang(self.aset.id, self.user)
        self.aset.refresh_from_db()
        self.assertEqual(self.aset.status, 'converted')
        self.assertEqual(self.aset.nilai_tersisa, Decimal('0'))

    def test_konversi_creates_swap_journal(self):
        from apps.jurnal.models import JurnalDetail
        from apps.pendapatan.services import konversi_aset_kontrak_ke_piutang
        konversi_aset_kontrak_ke_piutang(self.aset.id, self.user)
        self.aset.refresh_from_db()
        self.assertIsNotNone(self.aset.jurnal_header)
        details = JurnalDetail.objects.filter(jurnal_header=self.aset.jurnal_header)
        self.assertEqual(details.count(), 2)

    def test_konversi_creates_piutang_and_links_to_aset(self):
        from apps.piutang.models import PiutangHeader
        from apps.pendapatan.services import konversi_aset_kontrak_ke_piutang
        konversi_aset_kontrak_ke_piutang(self.aset.id, self.user)
        self.aset.refresh_from_db()
        self.assertIsNotNone(self.aset.piutang_id)
        piutang = PiutangHeader.objects.get(pk=self.aset.piutang_id)
        self.assertEqual(piutang.jumlah_pokok, Decimal('2000'))
        self.assertEqual(piutang.status, 'open')
        self.assertEqual(piutang.coa_piutang_account, self.akun_kas)


# ── Task 12: void_pendapatan cleanup ─────────────────────────────────────────

class VoidPendapatanTest(TestCase):
    def test_void_voids_jadwal_and_aset(self):
        from apps.pendapatan.services import void_pendapatan
        user = make_user('voider')
        akun_kas = make_akun('1001-VD', 'Kas Void')
        akun_pnd = make_akun('4001-VD', 'Pnd Void')
        akun_liabilitas = make_akun('2101-VD', 'Liabilitas Void')
        header = make_header(user)
        peb = make_pendapatan_eb(header, payment_account=akun_kas)
        kp = make_kp(
            peb, '1000',
            recognition_type='over_time',
            revenue_account=akun_pnd,
            ot_tipe_aliran='advance_payment_cash',
            ot_progress_method='straight_line',
            ot_tanggal_mulai=datetime.date(2026, 1, 1),
            ot_tanggal_selesai=datetime.date(2026, 3, 31),
            ot_liabilitas_kontrak_acct=akun_liabilitas,
        )
        jadwal = JadwalPengakuan.objects.create(
            kp=kp,
            tipe_aliran='advance_payment_cash',
            progress_method='straight_line',
            tanggal_mulai=datetime.date(2026, 1, 1),
            tanggal_selesai=datetime.date(2026, 3, 31),
            liabilitas_kontrak_acct=akun_liabilitas,
            nilai_total=Decimal('1000'),
            nilai_diakui=Decimal('0'),
            status='active',
        )
        header.status = 'confirmed'
        header.save()

        void_pendapatan(header, user)

        jadwal.refresh_from_db()
        header.refresh_from_db()
        self.assertEqual(jadwal.status, JadwalPengakuan.Status.VOIDED)
        self.assertEqual(header.status, 'voided')
