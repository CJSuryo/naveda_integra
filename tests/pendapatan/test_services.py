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
