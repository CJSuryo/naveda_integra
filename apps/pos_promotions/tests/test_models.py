import datetime
from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from pos_config.models import MerchantPOSConfig
from apps.pos_promotions.models import Campaign, Voucher


def _make_merchant():
    tipe = TipeEntitas.objects.first() or TipeEntitas.objects.create(nama='Test')
    eb = EntitasBisnis.objects.create(nama='Test Merchant Promo', tipe_entitas=tipe)
    return MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)


class CampaignModelTest(TestCase):

    def setUp(self):
        self.merchant = _make_merchant()

    def test_create_discount_pct_campaign(self):
        c = Campaign.objects.create(
            merchant_config=self.merchant,
            name='Diskon 20%',
            campaign_type=Campaign.TYPE_DISCOUNT_PCT,
            discount_pct=Decimal('20'),
            min_purchase_amount=Decimal('50000'),
            applicable_to=Campaign.APPLICABLE_ALL,
            start_date=datetime.date.today(),
        )
        self.assertEqual(c.campaign_type, 'DISCOUNT_PCT')
        self.assertTrue(c.is_active)

    def test_voucher_unique_code(self):
        c = Campaign.objects.create(
            merchant_config=self.merchant,
            name='Voucher Test',
            campaign_type=Campaign.TYPE_VOUCHER,
            applicable_to=Campaign.APPLICABLE_ALL,
            start_date=datetime.date.today(),
        )
        Voucher.objects.create(campaign=c, code='PROMO001')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Voucher.objects.create(campaign=c, code='PROMO001')
