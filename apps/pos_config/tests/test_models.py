import datetime

from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User, Role
from pos_config.models import (
    MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog,
)
from .factories import make_lv1, make_lv2, make_lv3, make_merchant, make_store


class MerchantPOSConfigTest(TestCase):
    def setUp(self):
        self.lv1 = make_lv1(nama='Grup Naveda')
        self.lv2 = make_lv2(self.lv1, nama='PT Kafe Naveda')

    def test_create_merchant_config_on_lv2(self):
        config = MerchantPOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2,
            is_pos_active=True,
            default_tax_pct=11,
            default_service_charge_pct=5,
        )
        self.assertEqual(config.entitas_bisnis_lv2, self.lv2)
        self.assertEqual(str(config), 'POS Config — PT Kafe Naveda')

    def test_entitas_bisnis_property_returns_lv1_group(self):
        config = make_merchant(self.lv2)
        self.assertEqual(config.entitas_bisnis, self.lv1)

    def test_one_merchant_config_per_lv2(self):
        MerchantPOSConfig.objects.create(entitas_bisnis_lv2=self.lv2)
        with self.assertRaises(IntegrityError):
            MerchantPOSConfig.objects.create(entitas_bisnis_lv2=self.lv2)


class StorePOSConfigTest(TestCase):
    def setUp(self):
        self.lv2 = make_lv2()
        self.merchant = make_merchant(
            self.lv2, default_tax_pct=11, default_service_charge_pct=5
        )
        self.lv3 = make_lv3(self.lv2, nama='Cabang Utama')

    def test_store_binds_to_lv3(self):
        store = make_store(self.merchant, self.lv3)
        self.assertEqual(store.entitas_bisnis_lv3, self.lv3)

    def test_one_store_config_per_lv3(self):
        make_store(self.merchant, self.lv3)
        with self.assertRaises(IntegrityError):
            StorePOSConfig.objects.create(
                entitas_bisnis_lv3=self.lv3, merchant_config=self.merchant
            )

    def test_effective_tax_pct_inherits_merchant_when_null(self):
        store = make_store(self.merchant, self.lv3, tax_pct=None)
        self.assertEqual(store.effective_tax_pct(), 11)

    def test_effective_tax_pct_uses_store_override(self):
        store = make_store(self.merchant, self.lv3, tax_pct=8)
        self.assertEqual(store.effective_tax_pct(), 8)

    def test_effective_service_charge_pct_inherits_merchant_when_null(self):
        store = make_store(self.merchant, self.lv3, service_charge_pct=None)
        self.assertEqual(store.effective_service_charge_pct(), 5)

    def test_effective_service_charge_pct_uses_store_override(self):
        store = make_store(self.merchant, self.lv3, service_charge_pct=2)
        self.assertEqual(store.effective_service_charge_pct(), 2)


class ShiftLogTest(TestCase):
    def setUp(self):
        self.store = make_store()
        self.shift = WorkShift.objects.create(
            store=self.store, name='Pagi',
            start_time=datetime.time(8, 0), end_time=datetime.time(16, 0),
        )
        role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='Kasir POS')
        self.user = User.objects.create_user(
            email='kasir@test.com', password='pass', name='Budi', role=role
        )

    def test_shift_log_is_active_when_clock_out_is_none(self):
        log = ShiftLog.objects.create(
            store=self.store, shift=self.shift, employee=self.user,
            clock_in=datetime.datetime(2026, 5, 5, 8, 0, tzinfo=datetime.timezone.utc),
            opening_cash=500000,
        )
        self.assertTrue(log.is_active)

    def test_shift_log_not_active_when_clocked_out(self):
        log = ShiftLog.objects.create(
            store=self.store, shift=self.shift, employee=self.user,
            clock_in=datetime.datetime(2026, 5, 5, 8, 0, tzinfo=datetime.timezone.utc),
            clock_out=datetime.datetime(2026, 5, 5, 16, 0, tzinfo=datetime.timezone.utc),
            opening_cash=500000, closing_cash=600000,
        )
        self.assertFalse(log.is_active)


class AccountingFieldsTest(TestCase):
    def setUp(self):
        from apps.master_data.models import Akun
        from apps.purchase.models import SubTransactionType
        self.lv2 = make_lv2()
        self.merchant = make_merchant(self.lv2, is_pos_active=True)
        self.revenue_account = Akun.objects.create(
            kode_akun='4-001', nama='Pendapatan POS', kategori_id='pendapatan'
        )
        self.hpp_account = Akun.objects.create(
            kode_akun='5-001', nama='HPP POS', kategori_id='beban'
        )
        self.cash_account = Akun.objects.create(
            kode_akun='1-001', nama='Kas POS', kategori_id='aset'
        )
        self.stt = SubTransactionType.objects.create(
            nama='Penjualan POS', module='sales', direction='outflow',
            default_offset_account=self.hpp_account,
        )

    def test_merchant_accounting_fields_persist(self):
        self.merchant.revenue_account = self.revenue_account
        self.merchant.offset_coa_account = self.hpp_account
        self.merchant.default_payment_account = self.cash_account
        self.merchant.sub_transaction_type = self.stt
        self.merchant.save()
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.revenue_account_id, self.revenue_account.pk)
        self.assertEqual(self.merchant.offset_coa_account_id, self.hpp_account.pk)
        self.assertEqual(self.merchant.default_payment_account_id, self.cash_account.pk)
        self.assertEqual(self.merchant.sub_transaction_type_id, self.stt.pk)

    def test_store_accounting_overrides_persist(self):
        store = make_store(self.merchant)
        store.revenue_account = self.revenue_account
        store.sub_transaction_type = self.stt
        store.save()
        store.refresh_from_db()
        self.assertEqual(store.revenue_account_id, self.revenue_account.pk)
        self.assertEqual(store.sub_transaction_type_id, self.stt.pk)

    def test_payment_method_payment_account_field_exists(self):
        store = make_store(self.merchant)
        pm = PaymentMethod.objects.create(
            merchant_config=self.merchant, store=store,
            name='QRIS', method_type=PaymentMethod.QRIS,
        )
        pm.payment_account = self.cash_account
        pm.save()
        pm.refresh_from_db()
        self.assertEqual(pm.payment_account_id, self.cash_account.pk)

    def test_aggregator_payment_method_type_available(self):
        pm = PaymentMethod.objects.create(
            merchant_config=self.merchant, name='GoFood',
            method_type=PaymentMethod.AGGREGATOR,
        )
        self.assertEqual(pm.get_method_type_display(), 'Aggregator (GoFood/GrabFood/ShopeeFood)')
