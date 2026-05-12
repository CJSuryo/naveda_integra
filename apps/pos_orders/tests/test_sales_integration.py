"""sales_integration helper — provides _make_accounting_setup for other test modules.

The create_sales_from_order bridge is deprecated (manual cashier now uses /sales/pos/ directly).
Tests for the bridge have been removed. This module is kept for its shared setup helper.
"""
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType


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
