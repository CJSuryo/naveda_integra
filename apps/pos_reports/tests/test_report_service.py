import datetime
from decimal import Decimal
from django.db import IntegrityError
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig
from apps.pos_reports.models import DailySalesSnapshot


def _make_store():
    tipe = TipeEntitas.objects.create(nama='FnB Reports')
    eb = EntitasBisnis.objects.create(nama='Reports Merchant', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Reports')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    return store


class DailySalesSnapshotModelTest(TestCase):

    def setUp(self):
        self.store = _make_store()

    def test_unique_per_store_date(self):
        today = datetime.date.today()
        DailySalesSnapshot.objects.create(store=self.store, date=today)
        with self.assertRaises(IntegrityError):
            DailySalesSnapshot.objects.create(store=self.store, date=today)

    def test_defaults_zero(self):
        snap = DailySalesSnapshot.objects.create(store=self.store, date=datetime.date.today())
        self.assertEqual(snap.total_orders, 0)
        self.assertEqual(snap.gross_sales, Decimal('0'))


# ── report_service tests ──────────────────────────────────────────────────────

import uuid
from django.utils import timezone
from django.contrib.auth import get_user_model

from pos_config.models import MerchantPOSConfig, StorePOSConfig, WorkShift, ShiftLog, PaymentMethod
from pos_orders.models import Order, OrderItem, OrderPayment
from apps.purchase.models import ItemMasterPurchase
from apps.pos_reports.services.report_service import (
    get_sales_summary, get_top_products, get_payment_breakdown, generate_daily_snapshot,
)

User = get_user_model()


def _make_full_setup():
    tipe = TipeEntitas.objects.create(nama='FnB Report Svc')
    eb = EntitasBisnis.objects.create(nama='Report Test Merchant', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Report')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb, is_pos_active=True)
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    pm_cash = PaymentMethod.objects.create(
        merchant_config=merchant, name='Tunai', method_type=PaymentMethod.CASH,
    )
    pm_qris = PaymentMethod.objects.create(
        merchant_config=merchant, name='QRIS', method_type=PaymentMethod.QRIS,
    )
    user, _ = User.objects.get_or_create(email='rpt_kasir@test.com', defaults={'name': 'Kasir Rpt'})
    shift_def = WorkShift.objects.create(store=store, name='Pagi', start_time='08:00', end_time='16:00')
    sl = ShiftLog.objects.create(store=store, shift=shift_def, employee=user, clock_in=timezone.now(), opening_cash=0)
    product = ItemMasterPurchase.objects.create(nama='Kopi Rpt', tipe_item='FG')
    return store, sl, user, pm_cash, pm_qris, product


def _create_completed_order(store, sl, user, pm, product, total, qty=Decimal('2'), order_num=None):
    num = order_num or f'ORD-RPT-{uuid.uuid4().hex[:6]}'
    order = Order.objects.create(
        order_number=num, store=store, shift_log=sl, cashier=user,
        status=Order.STATUS_COMPLETED,
        subtotal=total, total_amount=total, completed_at=timezone.now(),
    )
    unit_price = Decimal('25000')
    OrderItem.objects.create(
        order=order, product=product, quantity=qty,
        unit_price=unit_price, modifier_total=Decimal('0'),
        subtotal=qty * unit_price,
    )
    OrderPayment.objects.create(
        order=order, payment_method=pm, amount=total, is_confirmed=True,
    )
    return order


class GetSalesSummaryTest(TestCase):
    def setUp(self):
        self.store, self.sl, self.user, self.pm_cash, self.pm_qris, self.product = _make_full_setup()
        _create_completed_order(self.store, self.sl, self.user, self.pm_cash, self.product, Decimal('50000'))
        _create_completed_order(self.store, self.sl, self.user, self.pm_qris, self.product, Decimal('75000'))

    def test_summary_total_orders(self):
        today = timezone.localdate()
        result = get_sales_summary(self.store, today, today)
        self.assertEqual(result['total_orders'], 2)

    def test_summary_gross_sales(self):
        today = timezone.localdate()
        result = get_sales_summary(self.store, today, today)
        self.assertEqual(result['gross_sales'], Decimal('125000'))


class GetTopProductsTest(TestCase):
    def setUp(self):
        self.store, self.sl, self.user, self.pm_cash, _, self.product = _make_full_setup()
        _create_completed_order(self.store, self.sl, self.user, self.pm_cash, self.product, Decimal('50000'), qty=Decimal('2'))
        _create_completed_order(self.store, self.sl, self.user, self.pm_cash, self.product, Decimal('25000'), qty=Decimal('1'))

    def test_returns_top_product(self):
        today = timezone.localdate()
        result = get_top_products(self.store, today, today, limit=10)
        self.assertEqual(len(result), 1)
        product, qty, revenue = result[0]
        self.assertEqual(product.pk, self.product.pk)
        self.assertEqual(qty, Decimal('3'))


class GetPaymentBreakdownTest(TestCase):
    def setUp(self):
        self.store, self.sl, self.user, self.pm_cash, self.pm_qris, self.product = _make_full_setup()
        _create_completed_order(self.store, self.sl, self.user, self.pm_cash, self.product, Decimal('50000'))
        _create_completed_order(self.store, self.sl, self.user, self.pm_qris, self.product, Decimal('75000'))

    def test_cash_amount(self):
        today = timezone.localdate()
        result = get_payment_breakdown(self.store, today, today)
        self.assertEqual(result.get('CASH', Decimal('0')), Decimal('50000'))

    def test_qris_amount(self):
        today = timezone.localdate()
        result = get_payment_breakdown(self.store, today, today)
        self.assertEqual(result.get('QRIS', Decimal('0')), Decimal('75000'))


class GenerateDailySnapshotTest(TestCase):
    def setUp(self):
        self.store, self.sl, self.user, self.pm_cash, self.pm_qris, self.product = _make_full_setup()
        _create_completed_order(self.store, self.sl, self.user, self.pm_cash, self.product, Decimal('50000'))
        _create_completed_order(self.store, self.sl, self.user, self.pm_qris, self.product, Decimal('75000'))

    def test_creates_snapshot(self):
        today = timezone.localdate()
        snap = generate_daily_snapshot(self.store, today, shift_log=self.sl)
        self.assertEqual(snap.total_orders, 2)
        self.assertEqual(snap.gross_sales, Decimal('125000'))
        self.assertEqual(snap.cash_collected, Decimal('50000'))
        self.assertEqual(snap.qris_collected, Decimal('75000'))

    def test_idempotent_update_existing(self):
        today = timezone.localdate()
        generate_daily_snapshot(self.store, today, shift_log=self.sl)
        generate_daily_snapshot(self.store, today, shift_log=self.sl)
        count = DailySalesSnapshot.objects.filter(store=self.store, date=today).count()
        self.assertEqual(count, 1)
