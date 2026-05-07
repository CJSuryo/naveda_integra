from django.db import transaction
from pos_orders.models import Order
import datetime


def generate_order_number(store) -> str:
    """
    Generate sequential order number: ORD-{store_code}-{YYYYMMDD}-{seq:03d}
    Uses select_for_update() to prevent duplicates under concurrent requests.
    store_code = first 3 chars of store.entitas_bisnis_lv2.nama, uppercased.
    """
    today = datetime.date.today()
    date_str = today.strftime('%Y%m%d')
    store_code = store.entitas_bisnis_lv2.nama[:3].upper()
    prefix = f'ORD-{store_code}-{date_str}-'

    with transaction.atomic():
        last = (
            Order.objects
            .select_for_update()
            .filter(order_number__startswith=prefix)
            .order_by('-order_number')
            .values_list('order_number', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'{prefix}{seq:03d}'
