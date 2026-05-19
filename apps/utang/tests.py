from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import (
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem,
    ItemMasterPurchase, SubTransactionType,
)
from apps.purchase.services import create_automated_journals
from .models import UtangHeader, UtangDetail, UtangPembayaran, UtangTerhapus
from .services import (
    create_manual_utang,
    create_utang_for_purchase, create_utang_payment,
    reverse_utang_for_purchase, reverse_utang_header, reverse_utang_payment,
)


def make_fixtures():
    """Return a dict of common test fixtures."""
    tipe = TipeEntitas.objects.create(nama='Distributor')
    eb = EntitasBisnis.objects.create(
        nama='PT Demo', tipe_entitas=tipe, relasi='pemasok',
    )
    coa_utang = Akun.objects.create(
        kategori_id='kewajiban', nama='Utang Dagang', kode_akun='2.1.1',
    )
    coa_cash = Akun.objects.create(
        kategori_id='aset', nama='Kas', kode_akun='1.1.1',
    )
    sub_type = SubTransactionType.objects.create(
        nama='Kredit', module='purchase', direction='inflow',
        default_offset_account=coa_utang,
    )
    item = ItemMasterPurchase.objects.create(
        item_id='RM-0001', nama='Bahan', tipe_item='RM',
    )
    purchase = PurchaseHeader.objects.create(
        transaction_id='PUR-INV-0001', tanggal=date(2026, 4, 28), deskripsi='Test',
    )
    purchase_group = PurchaseEntitasBisnis.objects.create(
        purchase_header=purchase, entitas_bisnis=eb,
    )
    purchase_item = PurchaseItem.objects.create(
        purchase_eb=purchase_group,
        item=item,
        sub_transaction_type=sub_type,
        coa_account=coa_cash,
        offset_coa_account=coa_utang,
        quantity=Decimal('10'),
        unit_price=Decimal('10000'),
    )
    return {
        'tipe': tipe, 'eb': eb, 'coa_utang': coa_utang, 'coa_cash': coa_cash,
        'sub_type': sub_type, 'item': item, 'purchase': purchase,
        'purchase_group': purchase_group, 'purchase_item': purchase_item,
    }


class CreateUtangForPurchaseTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_utang_header_for_kewajiban_item(self):
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        utang = headers[0]
        self.assertEqual(utang.total_amount, Decimal('100000'))
        self.assertEqual(utang.status, 'open')
        self.assertEqual(utang.details.count(), 1)
        self.assertEqual(utang.entitas_bisnis, self.f['eb'])

    def test_skips_non_kewajiban_items(self):
        self.f['purchase_item'].offset_coa_account = self.f['coa_cash']
        self.f['purchase_item'].save()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 0)
        self.assertEqual(UtangHeader.objects.count(), 0)

    def test_payment_term_days_sets_jatuh_tempo(self):
        self.f['sub_type'].payment_term_days = 30
        self.f['sub_type'].save()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        expected = date(2026, 4, 28) + timedelta(days=30)
        self.assertEqual(headers[0].tanggal_jatuh_tempo, expected)

    def test_no_payment_term_uses_param(self):
        jatuh_tempo = date(2026, 6, 1)
        headers = create_utang_for_purchase(
            self.f['purchase'], tanggal_jatuh_tempo=jatuh_tempo,
        )
        self.assertEqual(headers[0].tanggal_jatuh_tempo, jatuh_tempo)

    def test_multiple_items_same_coa_grouped_into_one_header(self):
        item2 = ItemMasterPurchase.objects.create(
            item_id='RM-0002', nama='Bahan2', tipe_item='RM',
        )
        PurchaseItem.objects.create(
            purchase_eb=self.f['purchase_group'],
            item=item2,
            sub_transaction_type=self.f['sub_type'],
            coa_account=self.f['coa_cash'],
            offset_coa_account=self.f['coa_utang'],
            quantity=Decimal('5'),
            unit_price=Decimal('10000'),
        )
        headers = create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0].details.count(), 2)
        self.assertEqual(headers[0].total_amount, Decimal('150000'))
