from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase


class ReceiptTextTest(TestCase):

    def setUp(self):
        from apps.pos_orders.tests.test_sales_integration import _make_accounting_setup
        from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
        from apps.purchase.models import ItemMasterPurchase
        from apps.accounts.models import User
        from pos_config.models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
        from pos_orders.models import Order, OrderItem, OrderPayment
        import datetime
        from django.utils import timezone

        revenue_acct, hpp_acct, cash_acct, inventory_acct, stt = _make_accounting_setup()
        tipe = TipeEntitas.objects.create(nama='FnBRcp')
        eb = EntitasBisnis.objects.create(nama='Merchant Rcp', tipe_entitas=tipe, relasi='pelanggan')
        self.lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko A')

        merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=eb, is_pos_active=True,
            revenue_account=revenue_acct, offset_coa_account=hpp_acct,
            default_payment_account=cash_acct, sub_transaction_type=stt,
        )
        self.store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=self.lv2, merchant_config=merchant,
        )
        pm = PaymentMethod.objects.create(
            merchant_config=merchant, name='Tunai', method_type=PaymentMethod.CASH,
            payment_account=cash_acct,
        )
        item_master = ItemMasterPurchase.objects.create(
            nama='Kopi Test', tipe_item='FG', coa_account=inventory_acct,
        )
        user = User.objects.create_user(email='kasir_rcp@test.com', password='pw', name='Kasir Rcp')
        shift_def = WorkShift.objects.create(
            store=self.store, name='Pagi',
            start_time=datetime.time(8, 0), end_time=datetime.time(16, 0),
        )
        shift_log = ShiftLog.objects.create(
            store=self.store, shift=shift_def, employee=user,
            clock_in=timezone.now(), opening_cash=Decimal('500000'),
        )

        selling_price = Decimal('25000')
        qty = Decimal('2')
        self.order = Order.objects.create(
            order_number='ORD-RCP-001', store=self.store, shift_log=shift_log,
            cashier=user, status=Order.STATUS_COMPLETED,
        )
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

    def test_receipt_contains_store_name(self):
        from pos_orders.services.receipt_service import generate_receipt_text
        text = generate_receipt_text(self.order)
        self.assertIn('Toko A', text)

    def test_receipt_contains_order_number(self):
        from pos_orders.services.receipt_service import generate_receipt_text
        text = generate_receipt_text(self.order)
        self.assertIn(self.order.order_number, text)

    def test_receipt_contains_item_name_and_qty(self):
        from pos_orders.services.receipt_service import generate_receipt_text
        text = generate_receipt_text(self.order)
        self.assertIn('Kopi Test', text)
        self.assertIn('2', text)

    def test_receipt_contains_total(self):
        from pos_orders.services.receipt_service import generate_receipt_text
        text = generate_receipt_text(self.order)
        self.assertIn('50', text)

    def test_receipt_contains_payment_method(self):
        from pos_orders.services.receipt_service import generate_receipt_text
        text = generate_receipt_text(self.order)
        self.assertIn('Tunai', text)


class SendToPrinterTest(TestCase):

    def setUp(self):
        from apps.pos_orders.tests.test_sales_integration import _make_accounting_setup
        from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, TipeEntitas
        from apps.accounts.models import User
        from pos_config.models import MerchantPOSConfig, StorePOSConfig

        revenue_acct, hpp_acct, cash_acct, inventory_acct, stt = _make_accounting_setup()
        tipe = TipeEntitas.objects.create(nama='FnBPrt')
        eb = EntitasBisnis.objects.create(nama='Merchant Prt', tipe_entitas=tipe, relasi='pelanggan')
        lv2 = EntitasBisnisLv2.objects.create(entitas_bisnis=eb, nama='Toko Prt')
        merchant = MerchantPOSConfig.objects.create(
            entitas_bisnis=eb, is_pos_active=True,
            revenue_account=revenue_acct, offset_coa_account=hpp_acct,
            default_payment_account=cash_acct, sub_transaction_type=stt,
        )
        self.store = StorePOSConfig.objects.create(
            entitas_bisnis_lv2=lv2, merchant_config=merchant,
        )

    def test_noop_when_no_printer_ip(self):
        from pos_orders.services.receipt_service import send_to_printer
        self.store.printer_ip = None
        self.store.save(update_fields=['printer_ip'])
        send_to_printer(self.store, 'test receipt text')

    @patch('pos_orders.services.receipt_service.socket.socket')
    def test_sends_text_via_tcp(self, mock_socket_class):
        from pos_orders.services.receipt_service import send_to_printer
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__ = MagicMock(return_value=mock_sock)
        mock_socket_class.return_value.__exit__ = MagicMock(return_value=False)
        self.store.printer_ip = '192.168.1.100'
        self.store.printer_port = 9100
        self.store.save(update_fields=['printer_ip', 'printer_port'])
        send_to_printer(self.store, 'Hello Receipt')
        mock_sock.connect.assert_called_once_with(('192.168.1.100', 9100))
        mock_sock.sendall.assert_called_once()

    @patch('pos_orders.services.receipt_service.socket.socket')
    def test_logs_error_but_does_not_raise_on_socket_failure(self, mock_socket_class):
        from pos_orders.services.receipt_service import send_to_printer
        mock_socket_class.side_effect = OSError('Connection refused')
        self.store.printer_ip = '192.168.1.100'
        self.store.save(update_fields=['printer_ip'])
        send_to_printer(self.store, 'test')
