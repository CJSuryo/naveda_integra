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
