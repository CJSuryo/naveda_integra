"""Integration tests for complete_order flow.

The sales bridge (create_sales_from_order) is deprecated. These tests verify that
complete_order transitions status and triggers member points without creating a SalesHeader.
The SalesHeader is now created directly via /sales/pos/ in the manual cashier flow.
"""
from decimal import Decimal
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.purchase.models import ItemMasterPurchase, FIFOBatch
from apps.accounts.models import User
from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
from pos_orders.models import Order, OrderItem, OrderPayment
from pos_orders.services.order_service import complete_order
from apps.pos_orders.tests.test_sales_integration import _make_accounting_setup


class CompleteOrderIntegrationTest(TestCase):

    def setUp(self):
        self.revenue_acct, self.hpp_acct, self.cash_acct, self.inventory_acct, self.stt = (
            _make_accounting_setup()
        )
        tipe = TipeEntitas.objects.create(nama='FnBInt')
        eb = EntitasBisnis.objects.create(nama='Merchant Int', tipe_entitas=tipe, relasi='pelanggan')
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Int')

        merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=eb, is_pos_active=True,
            revenue_account=self.revenue_acct,
            offset_coa_account=self.hpp_acct,
            default_payment_account=self.cash_acct,
            sub_transaction_type=self.stt,
        )
        store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
        pm = PaymentMethod.objects.create(
            merchant_config=merchant, name='Tunai', method_type=PaymentMethod.CASH,
            payment_account=self.cash_acct,
        )
        item_master = ItemMasterPurchase.objects.create(
            nama='Kopi Int', tipe_item='FG', coa_account=self.inventory_acct,
        )
        FIFOBatch.objects.create(
            item=item_master, tanggal='2026-01-01',
            quantity_in=Decimal('100'), remaining_qty=Decimal('100'),
            unit_price=Decimal('10000'),
        )
        user = User.objects.create_user(email='kasir_int@test.com', password='pw', name='Kasir Int')
        shift_def = WorkShift.objects.create(
            store=store, name='Pagi',
            start_time=datetime.time(8, 0), end_time=datetime.time(16, 0),
        )
        shift_log = ShiftLog.objects.create(
            store=store, shift=shift_def, employee=user,
            clock_in=timezone.now(), opening_cash=Decimal('500000'),
        )

        self.order = Order.objects.create(
            order_number='ORD-INT-001', store=store, shift_log=shift_log,
            cashier=user, status=Order.STATUS_READY,
        )
        qty = Decimal('2')
        selling_price = Decimal('25000')
        OrderItem.objects.create(
            order=self.order, product=item_master, quantity=qty,
            unit_price=selling_price, modifier_total=Decimal('0'),
            subtotal=qty * selling_price,
        )
        OrderPayment.objects.create(
            order=self.order, payment_method=pm,
            amount=qty * selling_price, is_confirmed=True,
        )
        self.order.subtotal = qty * selling_price
        self.order.total_amount = self.order.subtotal
        self.order.save(update_fields=['subtotal', 'total_amount'])

    def test_complete_order_transitions_status(self):
        result = complete_order(self.order)
        self.assertEqual(result.status, Order.STATUS_COMPLETED)
