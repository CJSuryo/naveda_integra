"""Test that complete_order triggers sales integration end-to-end."""
from decimal import Decimal
from django.test import TestCase
from django.db.models import Sum

from pos_orders.models import Order, OrderPayment
from pos_orders.services.order_service import complete_order
from apps.sales.models import SalesHeader
from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.pos_orders.tests.test_sales_integration import (
    _make_accounting_setup, CreateSalesFromOrderTest,
)


class CompleteOrderIntegrationTest(TestCase):

    def setUp(self):
        self.revenue_acct, self.hpp_acct, self.cash_acct, self.inventory_acct, self.stt = (
            _make_accounting_setup()
        )
        # Reuse full base setup
        from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
        from apps.purchase.models import ItemMasterPurchase, FIFOBatch
        from apps.accounts.models import User
        from pos_config.models import (
            MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
        )
        from pos_catalog.models import POSProduct
        from pos_orders.models import OrderItem
        import datetime
        from django.utils import timezone

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
        product = POSProduct.objects.create(
            item_master=item_master, merchant_config=merchant,
            pos_name='Kopi Int', selling_price=Decimal('25000'), track_inventory=True,
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

        # Create order in READY status (complete_order can transition from READY)
        self.order = Order.objects.create(
            order_number='ORD-INT-001', store=store, shift_log=shift_log,
            cashier=user, status=Order.STATUS_READY,
        )
        qty = Decimal('2')
        OrderItem.objects.create(
            order=self.order, product=product, quantity=qty,
            unit_price=product.selling_price, modifier_total=Decimal('0'),
            subtotal=qty * product.selling_price,
        )
        OrderPayment.objects.create(
            order=self.order, payment_method=pm,
            amount=qty * product.selling_price, is_confirmed=True,
        )
        self.order.subtotal = qty * product.selling_price
        self.order.total_amount = self.order.subtotal
        self.order.save(update_fields=['subtotal', 'total_amount'])

    def test_complete_order_creates_sales_header(self):
        result = complete_order(self.order)
        self.assertEqual(result.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(result.sales_header_id)

    def test_complete_order_journal_balanced(self):
        result = complete_order(self.order)
        headers = JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Penjualan {result.sales_header.transaction_id}'
        )
        debit = JurnalDetail.objects.filter(
            jurnal_header__in=headers
        ).aggregate(s=Sum('debit'))['s'] or Decimal('0')
        kredit = JurnalDetail.objects.filter(
            jurnal_header__in=headers
        ).aggregate(s=Sum('kredit'))['s'] or Decimal('0')
        self.assertEqual(debit, kredit)
