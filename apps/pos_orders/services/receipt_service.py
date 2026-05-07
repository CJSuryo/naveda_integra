import socket
import logging

logger = logging.getLogger(__name__)

ESC = b'\x1b'
INIT_PRINTER = ESC + b'@'
CUT_PAPER = ESC + b'd\x05'
BOLD_ON = ESC + b'E\x01'
BOLD_OFF = ESC + b'E\x00'
ALIGN_CENTER = ESC + b'a\x01'
ALIGN_LEFT = ESC + b'a\x00'
LINE_WIDTH = 42


def generate_receipt_text(order) -> str:
    """Return human-readable receipt as plain string for preview or ESC/POS printing."""
    store = order.store
    merchant = store.merchant_config
    lines = []

    def rule(char='-'):
        lines.append(char * LINE_WIDTH)

    def center(text):
        lines.append(str(text).center(LINE_WIDTH))

    def pair(left, right, width=LINE_WIDTH):
        gap = width - len(left) - len(right)
        lines.append(left + ' ' * max(gap, 1) + right)

    if store.receipt_header:
        lines.append(store.receipt_header)
    else:
        center(store.entitas_bisnis_lv2.nama)
        alamat = getattr(merchant.entitas_bisnis, 'alamat', None)
        if alamat:
            center(alamat)

    rule()
    pair('No. Order:', order.order_number or '—')
    tanggal = order.completed_at or order.created_at
    pair('Tanggal:', tanggal.strftime('%d/%m/%Y %H:%M'))
    cashier_name = order.cashier.get_full_name() if hasattr(order.cashier, 'get_full_name') else ''
    pair('Kasir:', cashier_name or order.cashier.email)
    if order.table_number:
        pair('Meja:', order.table_number)
    if order.customer_name:
        pair('Pelanggan:', order.customer_name)
    rule()

    for item in order.items.exclude(status='CANCELLED').select_related('product'):
        item_name = item.product.pos_name
        unit_price = item.unit_price + item.modifier_total
        subtotal = unit_price * item.quantity
        qty_str = f'{item.quantity:g}'
        lines.append(f'{item_name[:28]}')
        pair(f'  {qty_str} x {unit_price:,.0f}', f'{subtotal:,.0f}')
        for mod in item.modifiers.all():
            lines.append(f'    + {mod.option_name_snapshot}')
        if item.notes:
            lines.append(f'    * {item.notes}')

    rule()
    pair('Subtotal:', f'Rp {order.subtotal:,.0f}')
    if order.discount_amount:
        pair('Diskon:', f'-Rp {order.discount_amount:,.0f}')
    if order.service_charge_amount:
        pair('Service Charge:', f'Rp {order.service_charge_amount:,.0f}')
    if order.tax_amount:
        pair('Pajak:', f'Rp {order.tax_amount:,.0f}')
    rule('=')
    pair('TOTAL:', f'Rp {order.total_amount:,.0f}')
    rule('=')

    for payment in order.payments.filter(is_confirmed=True).select_related('payment_method'):
        pair(payment.payment_method.name, f'Rp {payment.amount:,.0f}')

    rule()
    if store.receipt_footer:
        lines.append(store.receipt_footer)
    else:
        center('Terima kasih!')
        center('Selamat datang kembali')

    return '\n'.join(lines)


def send_to_printer(store, text: str) -> None:
    """Send receipt text to ESC/POS network printer. No-op if printer_ip is blank. Never raises."""
    if not store.printer_ip:
        return

    try:
        data = (
            INIT_PRINTER
            + text.encode('cp437', errors='replace')
            + b'\n'
            + CUT_PAPER
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect((store.printer_ip, store.printer_port or 9100))
            sock.sendall(data)
    except Exception as exc:
        logger.error(
            'ESC/POS printer send failed for store %s (%s:%s): %s',
            store.pk, store.printer_ip, store.printer_port, exc,
        )
