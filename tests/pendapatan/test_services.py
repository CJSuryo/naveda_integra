from decimal import Decimal
from django.test import TestCase

from tests.pendapatan.factories import make_user, make_header, make_pendapatan_eb, make_kp
from apps.pendapatan.services import compute_alokasi_harga


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
