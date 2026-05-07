from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod
from pos_catalog.models import POSProduct
from pos_orders.models import Order, OrderItem, OrderPayment
from apps.accounts.models import User, Role
import datetime


def make_store():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Pusat')
    merchant = MerchantPOSConfig.objects.create(entitas_bisnis=eb)
    return StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)


def make_cashier():
    role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
    return User.objects.create_user(email='kasir@test.com', password='pass', name='Budi', role=role)


def make_order(store, cashier):
    return Order.objects.create(
        store=store, cashier=cashier,
        order_number='ORD-TST-20260506-001',
        status=Order.STATUS_DRAFT,
        order_type=Order.ORDER_TYPE_DINE_IN,
        subtotal=Decimal('50000'),
        tax_amount=Decimal('5500'),
        service_charge_amount=Decimal('5000'),
        total_amount=Decimal('60500'),
    )


class OrderStateMachineTest(TestCase):
    def setUp(self):
        self.store = make_store()
        self.cashier = make_cashier()

    def test_draft_can_transition_to_open(self):
        order = make_order(self.store, self.cashier)
        self.assertTrue(order.can_transition_to(Order.STATUS_OPEN))

    def test_draft_can_transition_to_cancelled(self):
        order = make_order(self.store, self.cashier)
        self.assertTrue(order.can_transition_to(Order.STATUS_CANCELLED))

    def test_draft_cannot_transition_to_completed(self):
        order = make_order(self.store, self.cashier)
        self.assertFalse(order.can_transition_to(Order.STATUS_COMPLETED))

    def test_completed_cannot_transition_to_open(self):
        order = make_order(self.store, self.cashier)
        order.status = Order.STATUS_COMPLETED
        self.assertFalse(order.can_transition_to(Order.STATUS_OPEN))

    def test_completed_can_transition_to_refunded(self):
        order = make_order(self.store, self.cashier)
        order.status = Order.STATUS_COMPLETED
        self.assertTrue(order.can_transition_to(Order.STATUS_REFUNDED))

    def test_cancelled_has_no_valid_transitions(self):
        order = make_order(self.store, self.cashier)
        order.status = Order.STATUS_CANCELLED
        for status in [Order.STATUS_OPEN, Order.STATUS_COMPLETED, Order.STATUS_REFUNDED]:
            self.assertFalse(order.can_transition_to(status))


class OrderIsFullyPaidTest(TestCase):
    def setUp(self):
        self.store = make_store()
        self.cashier = make_cashier()
        self.method = PaymentMethod.objects.create(
            merchant_config=self.store.merchant_config,
            name='Tunai', method_type='CASH',
        )

    def test_not_fully_paid_with_no_payments(self):
        order = make_order(self.store, self.cashier)
        self.assertFalse(order.is_fully_paid())

    def test_fully_paid_when_confirmed_payments_cover_total(self):
        order = make_order(self.store, self.cashier)
        OrderPayment.objects.create(
            order=order, payment_method=self.method,
            amount=Decimal('60500'), is_confirmed=True,
        )
        self.assertTrue(order.is_fully_paid())

    def test_not_fully_paid_when_payment_unconfirmed(self):
        order = make_order(self.store, self.cashier)
        OrderPayment.objects.create(
            order=order, payment_method=self.method,
            amount=Decimal('60500'), is_confirmed=False,
        )
        self.assertFalse(order.is_fully_paid())

    def test_fully_paid_with_split_payments(self):
        order = make_order(self.store, self.cashier)
        OrderPayment.objects.create(order=order, payment_method=self.method, amount=Decimal('30000'), is_confirmed=True)
        OrderPayment.objects.create(order=order, payment_method=self.method, amount=Decimal('30500'), is_confirmed=True)
        self.assertTrue(order.is_fully_paid())


class OrderRecalculateTotalsTest(TestCase):
    def setUp(self):
        self.store = make_store()
        self.store.merchant_config.default_tax_pct = Decimal('11')
        self.store.merchant_config.tax_inclusive = False
        self.store.merchant_config.save()
        self.store.service_charge_pct = Decimal('5')
        self.store.save()
        self.cashier = make_cashier()
        kat = KategoriItem.objects.create(nama='Makan', tipe_item='ITM')
        item = ItemMasterPurchase.objects.create(nama='Nasi', tipe_item='ITM', kategori=kat)
        self.product = POSProduct.objects.create(
            item_master=item, merchant_config=self.store.merchant_config,
            pos_name='Nasi Goreng', selling_price=Decimal('25000'),
        )

    def test_recalculate_totals_tax_exclusive(self):
        order = Order.objects.create(
            store=self.store, cashier=self.cashier,
            order_number='ORD-TST-001', status=Order.STATUS_DRAFT,
            order_type=Order.ORDER_TYPE_DINE_IN,
        )
        OrderItem.objects.create(
            order=order, product=self.product,
            quantity=Decimal('2'), unit_price=Decimal('25000'),
            modifier_total=Decimal('0'), subtotal=Decimal('50000'),
            status='PENDING',
        )
        order.recalculate_totals()
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal('50000'))
        self.assertEqual(order.tax_amount, Decimal('5500'))
        self.assertEqual(order.service_charge_amount, Decimal('2500'))
        self.assertEqual(order.total_amount, Decimal('58000'))
