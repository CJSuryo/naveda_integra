from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig, WorkShift, ShiftLog, PaymentMethod
from apps.pos_crm.models import Member, MemberTierConfig, MemberPointLog
from apps.pos_crm.services.member_service import (
    lookup_member, register_member, add_points, redeem_points, check_tier_upgrade,
    deduct_points_for_refund,
)


def _make_setup():
    tipe = TipeEntitas.objects.create(nama='FnB PS')
    eb = EntitasBisnis.objects.create(nama='Test Merchant PS', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko PS')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    MemberTierConfig.objects.create(merchant_config=merchant, tier='REGULAR', min_total_spent=Decimal('0'), points_per_thousand=1)
    MemberTierConfig.objects.create(merchant_config=merchant, tier='SILVER', min_total_spent=Decimal('1000000'), points_per_thousand=2)
    MemberTierConfig.objects.create(merchant_config=merchant, tier='GOLD', min_total_spent=Decimal('5000000'), points_per_thousand=3)
    return merchant, store


class LookupMemberTest(TestCase):
    def setUp(self):
        self.merchant, _ = _make_setup()
        self.member = Member.objects.create(merchant_config=self.merchant, name='Budi', phone='0811111111')

    def test_lookup_by_phone_found(self):
        result = lookup_member('0811111111', self.merchant)
        self.assertEqual(result, self.member)

    def test_lookup_by_phone_not_found(self):
        self.assertIsNone(lookup_member('0899999999', self.merchant))


class RegisterMemberTest(TestCase):
    def setUp(self):
        self.merchant, _ = _make_setup()

    def test_register_creates_member(self):
        m = register_member(self.merchant, 'Siti Rahayu', '0822222222')
        self.assertEqual(m.name, 'Siti Rahayu')
        self.assertTrue(m.member_id.startswith('MBR-'))

    def test_register_duplicate_phone_raises(self):
        register_member(self.merchant, 'A', '0833333333')
        with self.assertRaises(ValueError):
            register_member(self.merchant, 'B', '0833333333')


class AddPointsTest(TestCase):
    def setUp(self):
        self.merchant, self.store = _make_setup()
        self.member = Member.objects.create(merchant_config=self.merchant, name='Citra', phone='0844444444')

    def _make_order(self, total=Decimal('50000')):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(email='kasir_crm@test.com', defaults={'name': 'Kasir CRM'})
        from pos_orders.models import Order
        shift_def = WorkShift.objects.create(store=self.store, name='P', start_time='08:00', end_time='16:00')
        from django.utils import timezone
        sl = ShiftLog.objects.create(store=self.store, shift=shift_def, employee=user, clock_in=timezone.now(), opening_cash=0)
        order = Order.objects.create(
            order_number='ORD-CRM-001',
            store=self.store,
            shift_log=sl,
            cashier=user,
            status='COMPLETED',
            total_amount=total,
            member=self.member,
        )
        return order

    def test_add_points_correct_amount(self):
        order = self._make_order(total=Decimal('50000'))
        log = add_points(self.member, order)
        # floor(50000 / 1000) * 1 = 50 points (REGULAR tier, points_per_thousand=1)
        self.assertEqual(log.points, 50)
        self.member.refresh_from_db()
        self.assertEqual(self.member.points, 50)

    def test_add_points_updates_total_spent(self):
        order = self._make_order(total=Decimal('75000'))
        add_points(self.member, order)
        self.member.refresh_from_db()
        self.assertEqual(self.member.total_spent, Decimal('75000'))
        self.assertEqual(self.member.total_orders, 1)


class RedeemPointsTest(TestCase):
    def setUp(self):
        self.merchant, self.store = _make_setup()
        self.member = Member.objects.create(
            merchant_config=self.merchant, name='Deni', phone='0855555555',
            points=500, total_spent=Decimal('500000'),
        )

    def _make_order(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(email='kasir_crm2@test.com', defaults={'name': 'Kasir CRM 2'})
        from pos_orders.models import Order
        shift_def = WorkShift.objects.create(store=self.store, name='P2', start_time='08:00', end_time='16:00')
        from django.utils import timezone
        sl = ShiftLog.objects.create(store=self.store, shift=shift_def, employee=user, clock_in=timezone.now(), opening_cash=0)
        return Order.objects.create(
            order_number='ORD-CRM-002',
            store=self.store, shift_log=sl, cashier=user,
            status='DRAFT', total_amount=Decimal('100000'), member=self.member,
        )

    def test_redeem_returns_discount_amount(self):
        order = self._make_order()
        discount, log = redeem_points(self.member, order, points_to_redeem=100)
        # point_value=100 per point → 100 points * 100 = Rp 10.000
        self.assertEqual(discount, Decimal('10000'))
        self.assertEqual(log.points, -100)

    def test_redeem_raises_if_insufficient_points(self):
        order = self._make_order()
        with self.assertRaises(ValueError):
            redeem_points(self.member, order, points_to_redeem=9999)


class TierUpgradeTest(TestCase):
    def setUp(self):
        self.merchant, _ = _make_setup()

    def test_no_upgrade_when_below_threshold(self):
        member = Member.objects.create(
            merchant_config=self.merchant, name='E', phone='0866666666',
            total_spent=Decimal('500000'), tier='REGULAR',
        )
        upgraded = check_tier_upgrade(member)
        self.assertFalse(upgraded)
        member.refresh_from_db()
        self.assertEqual(member.tier, 'REGULAR')

    def test_upgrade_to_silver(self):
        member = Member.objects.create(
            merchant_config=self.merchant, name='F', phone='0877777777',
            total_spent=Decimal('1500000'), tier='REGULAR',
        )
        upgraded = check_tier_upgrade(member)
        self.assertTrue(upgraded)
        member.refresh_from_db()
        self.assertEqual(member.tier, 'SILVER')
