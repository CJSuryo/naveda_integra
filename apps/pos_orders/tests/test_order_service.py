from decimal import Decimal
from django.test import TestCase
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.purchase.models import ItemMasterPurchase, KategoriItem
from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod
from pos_catalog.models import POSProduct, ModifierGroup, ModifierOption, ProductModifierGroup
from pos_orders.models import Order, OrderItem, OrderItemModifier, OrderPayment
from pos_orders.services.order_service import (
    create_order, add_item, remove_item, update_item_quantity,
    process_payment, confirm_payment, cancel_order,
)
from apps.accounts.models import User, Role


def make_env():
    tipe = TipeEntitas.objects.create(nama='FnB')
    eb = EntitasBisnis.objects.create(nama='Kafe', tipe_entitas=tipe, relasi='pelanggan')
    lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Pusat')
    merchant = MerchantPOSConfig.objects.create(
        entitas_bisnis=eb, default_tax_pct=Decimal('10'), default_service_charge_pct=Decimal('0')
    )
    store = StorePOSConfig.objects.create(entitas_bisnis_lv2=lv2, merchant_config=merchant)
    method = PaymentMethod.objects.create(merchant_config=merchant, name='Tunai', method_type='CASH')
    kat = KategoriItem.objects.create(nama='Makan', tipe_item='ITM')
    item = ItemMasterPurchase.objects.create(nama='Nasi Goreng', tipe_item='ITM', kategori=kat)
    product = POSProduct.objects.create(
        item_master=item, merchant_config=merchant,
        pos_name='Nasi Goreng', selling_price=Decimal('25000'),
        track_inventory=False,
    )
    role = Role.objects.create(kode='kasir', nama='Kasir', deskripsi='')
    cashier = User.objects.create_user(email='kasir@test.com', password='pass', name='Budi', role=role)
    return store, method, product, cashier


class CreateOrderTest(TestCase):
    def test_create_order_returns_draft(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        self.assertEqual(order.status, Order.STATUS_DRAFT)
        self.assertEqual(order.source, Order.SOURCE_POS)
        self.assertIsNotNone(order.pk)

    def test_create_order_has_no_order_number_yet(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        self.assertEqual(order.order_number, '')


class AddItemTest(TestCase):
    def test_add_item_creates_order_item(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        item = add_item(order, product, Decimal('2'), [], '')
        self.assertEqual(item.quantity, Decimal('2'))
        self.assertEqual(item.unit_price, product.selling_price)
        self.assertEqual(item.subtotal, Decimal('50000'))

    def test_add_item_with_modifiers_creates_snapshots(self):
        store, method, product, cashier = make_env()
        group = ModifierGroup.objects.create(
            merchant_config=store.merchant_config, name='Ukuran',
            is_required=True, min_selections=1, max_selections=1,
        )
        opt = ModifierOption.objects.create(group=group, name='L', additional_price=Decimal('5000'))
        ProductModifierGroup.objects.create(product=product, modifier_group=group)
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        item = add_item(order, product, Decimal('1'), [opt.pk], '')
        self.assertEqual(item.subtotal, Decimal('30000'))
        mod = item.modifiers.first()
        self.assertEqual(mod.option_name_snapshot, 'L')
        self.assertEqual(mod.price_snapshot, Decimal('5000'))

    def test_modifier_snapshot_preserved_after_price_change(self):
        store, method, product, cashier = make_env()
        group = ModifierGroup.objects.create(
            merchant_config=store.merchant_config, name='Level',
            is_required=False, min_selections=0, max_selections=1,
        )
        opt = ModifierOption.objects.create(group=group, name='Extra', additional_price=Decimal('3000'))
        ProductModifierGroup.objects.create(product=product, modifier_group=group)
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        item = add_item(order, product, Decimal('1'), [opt.pk], '')
        opt.additional_price = Decimal('9999')
        opt.save()
        mod = OrderItemModifier.objects.get(order_item=item)
        self.assertEqual(mod.price_snapshot, Decimal('3000'))


class RemoveItemTest(TestCase):
    def test_remove_item_deletes_it(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        item = add_item(order, product, Decimal('1'), [], '')
        remove_item(item)
        self.assertFalse(OrderItem.objects.filter(pk=item.pk).exists())


class PaymentTest(TestCase):
    def test_process_payment_creates_order_payment(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        add_item(order, product, Decimal('1'), [], '')
        order.recalculate_totals()
        op = process_payment(order, method, Decimal('27500'))
        self.assertTrue(op.is_confirmed)
        self.assertEqual(op.amount, Decimal('27500'))

    def test_qris_payment_not_auto_confirmed(self):
        store, method, product, cashier = make_env()
        qris_method = PaymentMethod.objects.create(
            merchant_config=store.merchant_config, name='QRIS', method_type='QRIS'
        )
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        add_item(order, product, Decimal('1'), [], '')
        order.recalculate_totals()
        op = process_payment(order, qris_method, Decimal('27500'))
        self.assertFalse(op.is_confirmed)

    def test_cancel_order_transitions_status(self):
        store, method, product, cashier = make_env()
        order = create_order(store, cashier, Order.ORDER_TYPE_DINE_IN, Order.SOURCE_POS)
        cancelled = cancel_order(order, 'Pelanggan membatalkan', cashier)
        self.assertEqual(cancelled.status, Order.STATUS_CANCELLED)
