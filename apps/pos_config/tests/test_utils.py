from decimal import Decimal

from django.test import TestCase

from pos_config.models import StorePOSConfig
from pos_config.utils import resolve_pos_config

from .factories import make_lv2, make_lv3, make_merchant, make_store


class ResolvePOSConfigTests(TestCase):
    """resolve_pos_config walks lv3 (store) → lv2 (merchant)."""

    def setUp(self):
        from apps.master_data.models import Akun
        from apps.purchase.models import SubTransactionType

        self.revenue = Akun.objects.create(
            kode_akun='4-100', nama='Pendapatan', kategori_id='pendapatan'
        )
        self.hpp = Akun.objects.create(kode_akun='5-100', nama='HPP', kategori_id='beban')
        self.kas = Akun.objects.create(kode_akun='1-100', nama='Kas', kategori_id='aset')
        self.store_revenue = Akun.objects.create(
            kode_akun='4-200', nama='Pendapatan Cabang', kategori_id='pendapatan'
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan POS', module='sales', direction='outflow',
            default_offset_account=self.hpp,
        )

        self.lv2 = make_lv2()
        self.merchant = make_merchant(
            self.lv2,
            default_tax_pct=Decimal('11'),
            default_service_charge_pct=Decimal('5'),
            revenue_account=self.revenue,
            offset_coa_account=self.hpp,
            default_payment_account=self.kas,
            sub_transaction_type=self.stt,
            tax_inclusive=True,
            currency='IDR',
        )
        self.lv3 = make_lv3(self.lv2)

    def test_inherits_everything_from_merchant_when_store_blank(self):
        make_store(self.merchant, self.lv3)
        cfg = resolve_pos_config(self.lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('11'))
        self.assertEqual(cfg['service_charge_pct'], Decimal('5'))
        self.assertEqual(cfg['revenue_account_id'], self.revenue.pk)
        self.assertEqual(cfg['offset_coa_account_id'], self.hpp.pk)
        self.assertEqual(cfg['payment_account_id'], self.kas.pk)
        self.assertEqual(cfg['sub_transaction_type_id'], self.stt.pk)
        self.assertTrue(cfg['tax_inclusive'])
        self.assertEqual(cfg['currency'], 'IDR')

    def test_store_override_wins(self):
        make_store(
            self.merchant, self.lv3,
            tax_pct=Decimal('8'), revenue_account=self.store_revenue,
        )
        cfg = resolve_pos_config(self.lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('8'))
        self.assertEqual(cfg['revenue_account_id'], self.store_revenue.pk)
        # Untouched fields still fall through to the merchant.
        self.assertEqual(cfg['offset_coa_account_id'], self.hpp.pk)

    def test_falls_back_to_lv2_config_when_store_config_missing(self):
        cfg = resolve_pos_config(self.lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('11'))
        self.assertEqual(cfg['revenue_account_id'], self.revenue.pk)

    def test_returns_safe_defaults_when_nothing_configured(self):
        bare_lv3 = make_lv3(make_lv2(), nama='Cabang Tanpa Config')
        cfg = resolve_pos_config(bare_lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('0'))
        self.assertEqual(cfg['service_charge_pct'], Decimal('0'))
        self.assertIsNone(cfg['revenue_account_id'])
        self.assertEqual(cfg['currency'], 'IDR')
        self.assertFalse(cfg['tax_inclusive'])

    def test_zero_store_override_is_respected_not_treated_as_blank(self):
        """A store tax of 0% must not fall through to the merchant's 11%."""
        make_store(self.merchant, self.lv3, tax_pct=Decimal('0'))
        cfg = resolve_pos_config(self.lv3)
        self.assertEqual(cfg['tax_pct'], Decimal('0'))
