from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.accounts.models import User, Role
from pos_config.models import (
    MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog, WebPushSubscription
)
import datetime


class MerchantPOSConfigTest(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.entitas = EntitasBisnis.objects.create(
            nama='Kafe Naveda', tipe_entitas=tipe, relasi='pelanggan'
        )

    def test_create_merchant_config(self):
        config = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.entitas,
            is_pos_active=True,
            default_tax_pct=11,
            default_service_charge_pct=5,
            tax_inclusive=False,
        )
        self.assertEqual(config.entitas_bisnis, self.entitas)
        self.assertEqual(str(config), 'POS Config — Kafe Naveda')

    def test_one_to_one_constraint(self):
        MerchantPOSConfig.objects.create(entitas_bisnis=self.entitas)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            MerchantPOSConfig.objects.create(entitas_bisnis=self.entitas)


class StorePOSConfigTest(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        entitas = EntitasBisnis.objects.create(nama='Kafe Naveda', tipe_entitas=tipe, relasi='pelanggan')
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=entitas, default_tax_pct=11, default_service_charge_pct=5
        )
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=entitas, nama='Cabang Utama')

    def test_effective_tax_pct_inherits_merchant_when_null(self):
        store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2, merchant_config=self.merchant, tax_pct=None
        )
        self.assertEqual(store.effective_tax_pct(), 11)

    def test_effective_tax_pct_uses_store_override(self):
        store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2, merchant_config=self.merchant, tax_pct=8
        )
        self.assertEqual(store.effective_tax_pct(), 8)

    def test_effective_service_charge_pct_inherits_merchant_when_null(self):
        store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2, merchant_config=self.merchant, service_charge_pct=None
        )
        self.assertEqual(store.effective_service_charge_pct(), 5)


class ShiftLogTest(TestCase):
    def setUp(self):
        tipe = TipeEntitas.objects.create(nama='FnB')
        entitas = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
        merchant = MerchantPOSConfig.objects.create(entitas_bisnis=entitas)
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=entitas, nama='Pusat')
        self.store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
        self.shift = WorkShift.objects.create(
            store=self.store, name='Pagi', start_time=datetime.time(8, 0), end_time=datetime.time(16, 0)
        )
        role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='Kasir POS')
        self.user = User.objects.create_user(email='kasir@test.com', password='pass', name='Budi', role=role)

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


class MerchantAccountingFieldsTest(TestCase):
    def setUp(self):
        from apps.master_data.models import Akun
        from apps.purchase.models import SubTransactionType
        tipe = TipeEntitas.objects.create(nama='FnB2')
        self.eb = EntitasBisnis.objects.create(
            nama='Test Merchant', tipe_entitas=tipe, relasi='pelanggan'
        )
        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb, is_pos_active=True,
        )
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

    def test_merchant_accounting_fields_exist(self):
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

    def test_payment_method_payment_account_field_exists(self):
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Toko A')
        StorePOSConfig.objects.create(
            entitas_bisnis_lv2=lv2, merchant_config=self.merchant,
        )
        pm = PaymentMethod.objects.create(
            merchant_config=self.merchant, name='QRIS', method_type=PaymentMethod.QRIS,
        )
        pm.payment_account = self.cash_account
        pm.save()
        pm.refresh_from_db()
        self.assertEqual(pm.payment_account_id, self.cash_account.pk)
