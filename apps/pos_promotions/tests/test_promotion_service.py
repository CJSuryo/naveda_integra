import datetime
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig, WorkShift, ShiftLog
from apps.pos_promotions.models import Campaign, Voucher, OrderPromotion
from apps.pos_promotions.services.promotion_service import (
    get_applicable_campaigns, calculate_discount, validate_voucher,
    apply_voucher, generate_voucher_codes,
)


def _make_setup():
    tipe = TipeEntitas.objects.first() or TipeEntitas.objects.create(nama='Test')
    eb = EntitasBisnis.objects.create(nama='Promo Merchant', tipe_entitas=tipe)
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Promo')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    return merchant, store


def _make_order(store, total=Decimal('100000')):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        email='kasir_promo_test@test.com',
        defaults={'name': 'Kasir Promo Test'},
    )
    from pos_orders.models import Order
    shift_def = WorkShift.objects.create(store=store, name='PX', start_time='08:00', end_time='16:00')
    from django.utils import timezone
    sl = ShiftLog.objects.create(store=store, shift=shift_def, employee=user, clock_in=timezone.now(), opening_cash=0)
    return Order.objects.create(
        order_number=f'ORD-PROMO-{Order.objects.count() + 1:03d}',
        store=store, shift_log=sl, cashier=user,
        status='DRAFT', total_amount=total, subtotal=total,
    )


class GetApplicableCampaignsTest(TestCase):
    def setUp(self):
        self.merchant, self.store = _make_setup()
        today = datetime.date.today()
        self.campaign = Campaign.objects.create(
            merchant_config=self.merchant,
            name='Diskon 10%',
            campaign_type=Campaign.TYPE_DISCOUNT_PCT,
            discount_pct=Decimal('10'),
            applicable_to=Campaign.APPLICABLE_ALL,
            start_date=today,
            min_purchase_amount=Decimal('50000'),
        )

    def test_returns_active_campaign(self):
        order = _make_order(self.store, total=Decimal('100000'))
        result = get_applicable_campaigns(order)
        self.assertIn(self.campaign, result)

    def test_excludes_campaign_below_min_purchase(self):
        order = _make_order(self.store, total=Decimal('10000'))
        result = get_applicable_campaigns(order)
        self.assertNotIn(self.campaign, result)

    def test_excludes_expired_campaign(self):
        self.campaign.end_date = datetime.date.today() - datetime.timedelta(days=1)
        self.campaign.save()
        order = _make_order(self.store, total=Decimal('100000'))
        result = get_applicable_campaigns(order)
        self.assertNotIn(self.campaign, result)

    def test_excludes_inactive_campaign(self):
        self.campaign.is_active = False
        self.campaign.save()
        order = _make_order(self.store, total=Decimal('100000'))
        result = get_applicable_campaigns(order)
        self.assertNotIn(self.campaign, result)


class CalculateDiscountTest(TestCase):
    def setUp(self):
        self.merchant, self.store = _make_setup()

    def _make_campaign(self, **kwargs):
        return Campaign.objects.create(
            merchant_config=self.merchant,
            applicable_to=Campaign.APPLICABLE_ALL,
            start_date=datetime.date.today(),
            **kwargs,
        )

    def test_discount_pct(self):
        c = self._make_campaign(name='10%', campaign_type=Campaign.TYPE_DISCOUNT_PCT, discount_pct=Decimal('10'))
        order = _make_order(self.store, total=Decimal('100000'))
        self.assertEqual(calculate_discount(c, order), Decimal('10000'))

    def test_discount_pct_capped(self):
        c = self._make_campaign(
            name='20% cap 15k', campaign_type=Campaign.TYPE_DISCOUNT_PCT,
            discount_pct=Decimal('20'), max_discount_cap=Decimal('15000'),
        )
        order = _make_order(self.store, total=Decimal('100000'))
        self.assertEqual(calculate_discount(c, order), Decimal('15000'))

    def test_discount_fixed(self):
        c = self._make_campaign(name='Rp10k', campaign_type=Campaign.TYPE_DISCOUNT_FIXED, discount_amount=Decimal('10000'))
        order = _make_order(self.store, total=Decimal('50000'))
        self.assertEqual(calculate_discount(c, order), Decimal('10000'))


class ValidateVoucherTest(TestCase):
    def setUp(self):
        self.merchant, self.store = _make_setup()
        self.campaign = Campaign.objects.create(
            merchant_config=self.merchant, name='V', campaign_type=Campaign.TYPE_VOUCHER,
            applicable_to=Campaign.APPLICABLE_ALL, start_date=datetime.date.today(),
        )
        self.voucher = Voucher.objects.create(campaign=self.campaign, code='SAVE50')

    def test_valid_voucher(self):
        order = _make_order(self.store)
        voucher, error = validate_voucher('SAVE50', order)
        self.assertIsNotNone(voucher)
        self.assertIsNone(error)

    def test_invalid_code(self):
        order = _make_order(self.store)
        voucher, error = validate_voucher('BADCODE', order)
        self.assertIsNone(voucher)
        self.assertIsNotNone(error)

    def test_already_used_voucher(self):
        self.voucher.is_used = True
        self.voucher.save()
        order = _make_order(self.store)
        voucher, error = validate_voucher('SAVE50', order)
        self.assertIsNone(voucher)
        self.assertIsNotNone(error)


class GenerateVoucherCodesTest(TestCase):
    def setUp(self):
        self.merchant, _ = _make_setup()
        self.campaign = Campaign.objects.create(
            merchant_config=self.merchant, name='Batch', campaign_type=Campaign.TYPE_VOUCHER,
            applicable_to=Campaign.APPLICABLE_ALL, start_date=datetime.date.today(),
        )

    def test_generates_correct_count(self):
        vouchers = generate_voucher_codes(self.campaign, count=5, prefix='BATCH')
        self.assertEqual(len(vouchers), 5)
        self.assertEqual(Voucher.objects.filter(campaign=self.campaign).count(), 5)

    def test_codes_start_with_prefix(self):
        vouchers = generate_voucher_codes(self.campaign, count=3, prefix='TEST')
        for v in vouchers:
            self.assertTrue(v.code.startswith('TEST'))

    def test_codes_unique(self):
        vouchers = generate_voucher_codes(self.campaign, count=10)
        codes = [v.code for v in vouchers]
        self.assertEqual(len(set(codes)), 10)
