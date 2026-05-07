"""Integration tests — hit real DB, no mocks. Verify journal balance invariant."""
import datetime
from decimal import Decimal
from django.test import TestCase
from django.db.models import Sum
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType, ItemMasterPurchase, FIFOBatch
from apps.accounts.models import User
from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
from pos_catalog.models import POSProduct
from pos_orders.models import Order, OrderItem, OrderPayment
from apps.jurnal.models import JurnalDetail


def _make_accounting_setup():
    revenue_acct = Akun.objects.create(kode_akun='4-POS-001', nama='Pendapatan POS Test', kategori_id='pendapatan')
    hpp_acct = Akun.objects.create(kode_akun='5-POS-001', nama='HPP POS Test', kategori_id='beban')
    cash_acct = Akun.objects.create(kode_akun='1-POS-001', nama='Kas POS Test', kategori_id='aset')
    inventory_acct = Akun.objects.create(kode_akun='1-POS-002', nama='Persediaan POS Test', kategori_id='aset')
    stt = SubTransactionType.objects.create(
        nama='Penjualan POS Test', module='sales', direction='outflow',
        default_offset_account=hpp_acct,
    )
    return revenue_acct, hpp_acct, cash_acct, inventory_acct, stt


class CreateSalesFromOrderTest(TestCase):

    def setUp(self):
        self.revenue_acct, self.hpp_acct, self.cash_acct, self.inventory_acct, self.stt = (
            _make_accounting_setup()
        )
        tipe = TipeEntitas.objects.create(nama='FnB')
        self.eb = EntitasBisnis.objects.create(nama='Merchant Test', tipe_entitas=tipe, relasi='pelanggan')
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=self.eb, nama='Toko A')

        self.merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=self.eb,
            is_pos_active=True,
            revenue_account=self.revenue_acct,
            offset_coa_account=self.hpp_acct,
            default_payment_account=self.cash_acct,
            sub_transaction_type=self.stt,
        )
        self.store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2, merchant_config=self.merchant,
        )
        self.pm = PaymentMethod.objects.create(
            merchant_config=self.merchant, name='Tunai', method_type=PaymentMethod.CASH,
            payment_account=self.cash_acct,
        )
        self.item_master = ItemMasterPurchase.objects.create(
            nama='Kopi Test', tipe_item='FG',
            coa_account=self.inventory_acct,
        )
        self.product = POSProduct.objects.create(
            item_master=self.item_master, merchant_config=self.merchant,
            pos_name='Kopi Test', selling_price=Decimal('25000'), track_inventory=True,
        )
        FIFOBatch.objects.create(
            item=self.item_master, tanggal='2026-01-01',
            quantity_in=Decimal('100'), remaining_qty=Decimal('100'),
            unit_price=Decimal('10000'),
        )
        self.user = User.objects.create_user(email='kasir_test@test.com', password='pw', name='Kasir Test')
        shift_def = WorkShift.objects.create(
            store=self.store, name='Pagi',
            start_time=datetime.time(8, 0), end_time=datetime.time(16, 0),
        )
        self.shift_log = ShiftLog.objects.create(
            store=self.store, shift=shift_def, employee=self.user,
            clock_in=timezone.now(), opening_cash=Decimal('500000'),
        )

    def _make_completed_order(self, qty=Decimal('2')):
        order = Order.objects.create(
            order_number='ORD-TEST-001',
            store=self.store,
            shift_log=self.shift_log,
            cashier=self.user,
            status=Order.STATUS_COMPLETED,
        )
        OrderItem.objects.create(
            order=order, product=self.product,
            quantity=qty, unit_price=self.product.selling_price,
            modifier_total=Decimal('0'),
            subtotal=qty * self.product.selling_price,
        )
        OrderPayment.objects.create(
            order=order, payment_method=self.pm,
            amount=qty * self.product.selling_price, is_confirmed=True,
        )
        order.subtotal = order.items.aggregate(s=Sum('subtotal'))['s'] or Decimal('0')
        order.total_amount = order.subtotal
        order.save(update_fields=['subtotal', 'total_amount'])
        return order

    def test_creates_sales_header(self):
        from pos_orders.services.sales_integration import create_sales_from_order
        order = self._make_completed_order()
        sales = create_sales_from_order(order)
        self.assertIsNotNone(sales)
        self.assertIsNotNone(sales.transaction_id)
        order.refresh_from_db()
        self.assertEqual(order.sales_header_id, sales.pk)

    def test_creates_sales_items_for_each_order_item(self):
        from pos_orders.services.sales_integration import create_sales_from_order
        order = self._make_completed_order(qty=Decimal('3'))
        sales = create_sales_from_order(order)
        items = sales.entitas_groups.first().items.all()
        self.assertEqual(items.count(), 1)
        si = items.first()
        self.assertEqual(si.quantity, Decimal('3'))
        self.assertEqual(si.selling_price, self.product.selling_price)

    def test_journal_balance_invariant(self):
        """CRITICAL: debit total must equal kredit total after integration."""
        from pos_orders.services.sales_integration import create_sales_from_order
        from apps.jurnal.models import JurnalHeader
        order = self._make_completed_order(qty=Decimal('2'))
        sales = create_sales_from_order(order)
        headers = JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Penjualan {sales.transaction_id}'
        )
        self.assertGreater(headers.count(), 0, 'No journal headers created')
        total_debit = JurnalDetail.objects.filter(
            jurnal_header__in=headers
        ).aggregate(s=Sum('debit'))['s'] or Decimal('0')
        total_kredit = JurnalDetail.objects.filter(
            jurnal_header__in=headers
        ).aggregate(s=Sum('kredit'))['s'] or Decimal('0')
        self.assertEqual(
            total_debit, total_kredit,
            f'Journal imbalance: debit={total_debit}, kredit={total_kredit}'
        )

    def test_idempotent_guard_raises_if_already_integrated(self):
        from pos_orders.services.sales_integration import create_sales_from_order
        order = self._make_completed_order()
        create_sales_from_order(order)
        with self.assertRaises(ValueError):
            create_sales_from_order(order)

    def test_raises_if_order_not_completed(self):
        from pos_orders.services.sales_integration import create_sales_from_order
        order = self._make_completed_order()
        order.status = Order.STATUS_OPEN
        order.sales_header = None
        order.save(update_fields=['status', 'sales_header'])
        with self.assertRaises(ValueError):
            create_sales_from_order(order)

    def test_raises_if_merchant_missing_revenue_account(self):
        from pos_orders.services.sales_integration import create_sales_from_order
        self.merchant.revenue_account = None
        self.merchant.save(update_fields=['revenue_account'])
        order = self._make_completed_order()
        order.sales_header = None
        order.save(update_fields=['sales_header'])
        with self.assertRaises(ValueError):
            create_sales_from_order(order)
