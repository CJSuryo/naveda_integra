from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from pos_config.models import MerchantPOSConfig
from apps.pos_crm.models import Member, MemberTierConfig, MemberPointLog


def _make_merchant():
    tipe = TipeEntitas.objects.create(nama='FnB CRM')
    eb = EntitasBisnis.objects.create(nama='Test Merchant CRM', tipe_entitas=tipe, relasi='pelanggan')
    return MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)


class MemberModelTest(TestCase):

    def setUp(self):
        self.merchant = _make_merchant()

    def test_member_id_auto_generated(self):
        m = Member.objects.create(
            merchant_config=self.merchant,
            name='Budi Santoso',
            phone='081234567890',
        )
        self.assertTrue(m.member_id.startswith('MBR-'))

    def test_member_id_sequential(self):
        m1 = Member.objects.create(merchant_config=self.merchant, name='A', phone='0811111111')
        m2 = Member.objects.create(merchant_config=self.merchant, name='B', phone='0822222222')
        seq1 = int(m1.member_id.split('-')[1])
        seq2 = int(m2.member_id.split('-')[1])
        self.assertEqual(seq2, seq1 + 1)

    def test_unique_phone_per_merchant(self):
        Member.objects.create(merchant_config=self.merchant, name='A', phone='0811111111')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Member.objects.create(merchant_config=self.merchant, name='B', phone='0811111111')

    def test_initial_tier_is_regular(self):
        m = Member.objects.create(merchant_config=self.merchant, name='A', phone='0833333333')
        self.assertEqual(m.tier, 'REGULAR')
        self.assertEqual(m.points, 0)
        self.assertEqual(m.total_spent, Decimal('0'))


class MemberTierConfigTest(TestCase):

    def setUp(self):
        self.merchant = _make_merchant()

    def test_tier_config_unique_per_merchant(self):
        MemberTierConfig.objects.create(
            merchant_config=self.merchant,
            tier='SILVER',
            min_total_spent=Decimal('1000000'),
            points_per_thousand=2,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            MemberTierConfig.objects.create(
                merchant_config=self.merchant,
                tier='SILVER',
                min_total_spent=Decimal('2000000'),
                points_per_thousand=3,
            )
