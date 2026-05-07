from decimal import Decimal
from django.test import TestCase
from pos_orders.models import Order, Refund, RefundItem
from apps.pos_orders.tests.test_sales_integration import CreateSalesFromOrderTest


class RefundServiceTest(TestCase):

    def setUp(self):
        from apps.pos_orders.tests.test_sales_integration import _make_accounting_setup
        from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
        from apps.purchase.models import ItemMasterPurchase, FIFOBatch
        from apps.accounts.models import User
        from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
        from pos_catalog.models import POSProduct
        from pos_orders.models import OrderItem, OrderPayment
        import datetime
        from django.utils import timezone
        from django.db.models import Sum

        revenue_acct, hpp_acct, cash_acct, inventory_acct, stt = _make_accounting_setup()

        tipe = TipeEntitas.objects.create(nama='FnBRef')
        eb = EntitasBisnis.objects.create(nama='Merchant Ref', tipe_entitas=tipe, relasi='pelanggan')
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Ref')

        merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=eb, is_pos_active=True,
            revenue_account=revenue_acct, offset_coa_account=hpp_acct,
            default_payment_account=cash_acct, sub_transaction_type=stt,
        )
        self.store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
        self.pm = PaymentMethod.objects.create(
            merchant_config=merchant, name='Tunai', method_type=PaymentMethod.CASH,
            payment_account=cash_acct,
        )
        item_master = ItemMasterPurchase.objects.create(
            nama='Kopi Ref', tipe_item='FG', coa_account=inventory_acct,
        )
        product = POSProduct.objects.create(
            item_master=item_master, merchant_config=merchant,
            pos_name='Kopi Ref', selling_price=Decimal('25000'), track_inventory=True,
        )
        FIFOBatch.objects.create(
            item=item_master, tanggal='2026-01-01',
            quantity_in=Decimal('100'), remaining_qty=Decimal('100'),
            unit_price=Decimal('10000'),
        )
        self.user = User.objects.create_user(email='kasir_ref@test.com', password='pw', name='Kasir Ref')
        shift_def = WorkShift.objects.create(
            store=self.store, name='Pagi',
            start_time=datetime.time(8, 0), end_time=datetime.time(16, 0),
        )
        shift_log = ShiftLog.objects.create(
            store=self.store, shift=shift_def, employee=self.user,
            clock_in=timezone.now(), opening_cash=Decimal('500000'),
        )

        qty = Decimal('2')
        self.order = Order.objects.create(
            order_number='ORD-REF-001', store=self.store, shift_log=shift_log,
            cashier=self.user, status=Order.STATUS_COMPLETED,
        )
        self.order_item = OrderItem.objects.create(
            order=self.order, product=product, quantity=qty,
            unit_price=product.selling_price, modifier_total=Decimal('0'),
            subtotal=qty * product.selling_price,
        )
        OrderPayment.objects.create(
            order=self.order, payment_method=self.pm,
            amount=qty * product.selling_price, is_confirmed=True,
        )
        self.order.subtotal = qty * product.selling_price
        self.order.total_amount = self.order.subtotal
        self.order.save(update_fields=['subtotal', 'total_amount'])

        # Integrate so sales_header exists
        from pos_orders.services.sales_integration import create_sales_from_order
        create_sales_from_order(self.order)

    def test_initiate_full_refund(self):
        from pos_orders.services.refund_service import initiate_refund
        refund = initiate_refund(
            order=self.order, by_user=self.user, reason='Customer changed mind',
            refund_type=Refund.REFUND_FULL, refund_method=self.pm,
        )
        self.assertEqual(refund.status, Refund.REFUND_STATUS_PENDING)
        self.assertEqual(refund.refund_type, Refund.REFUND_FULL)
        self.assertEqual(refund.amount, self.order.total_amount)

    def test_initiate_refund_raises_if_not_completed(self):
        from pos_orders.services.refund_service import initiate_refund
        self.order.status = Order.STATUS_OPEN
        self.order.save(update_fields=['status'])
        with self.assertRaises(ValueError):
            initiate_refund(self.order, self.user, 'reason', Refund.REFUND_FULL, self.pm)

    def test_approve_refund(self):
        from pos_orders.services.refund_service import initiate_refund, approve_refund
        refund = initiate_refund(self.order, self.user, 'reason', Refund.REFUND_FULL, self.pm)
        approved = approve_refund(refund, approved_by=self.user)
        self.assertEqual(approved.status, Refund.REFUND_STATUS_APPROVED)
        self.assertEqual(approved.approved_by, self.user)

    def test_complete_refund_reverses_sales(self):
        from pos_orders.services.refund_service import initiate_refund, approve_refund, complete_refund
        refund = initiate_refund(self.order, self.user, 'reason', Refund.REFUND_FULL, self.pm)
        approve_refund(refund, self.user)
        complete_refund(refund)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_REFUNDED)
        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.REFUND_STATUS_COMPLETED)

    def test_complete_refund_raises_if_not_approved(self):
        from pos_orders.services.refund_service import initiate_refund, complete_refund
        refund = initiate_refund(self.order, self.user, 'reason', Refund.REFUND_FULL, self.pm)
        with self.assertRaises(ValueError):
            complete_refund(refund)

    def test_initiate_partial_refund(self):
        from pos_orders.services.refund_service import initiate_refund
        refund = initiate_refund(
            order=self.order, by_user=self.user, reason='Wrong item',
            refund_type=Refund.REFUND_PARTIAL, refund_method=self.pm,
            items=[{
                'order_item_id': self.order_item.pk,
                'quantity': Decimal('1'),
                'amount': self.order_item.unit_price,
            }],
        )
        self.assertEqual(refund.refund_type, Refund.REFUND_PARTIAL)
        self.assertEqual(refund.items.count(), 1)
        ri = refund.items.first()
        self.assertEqual(ri.quantity, Decimal('1'))
