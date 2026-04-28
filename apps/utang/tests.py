from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, ItemMasterPurchase, SubTransactionType
from apps.purchase.services import create_automated_journals
from .models import UtangHeader, UtangDetail, UtangPembayaran
from .services import create_utang_for_purchase, create_utang_payment, reverse_utang_for_purchase


class UtangModelTests(TestCase):
    def setUp(self):
        self.eb = EntitasBisnis.objects.create(nama='PT Demo')
        self.coa_utang = Akun.objects.create(kategori_id='kewajiban', nama='Utang Dagang', kode_akun='2.1.1')
        self.coa_cash = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
        self.sub_type = SubTransactionType.objects.create(
            nama='Kredit', module='purchase', direction='inflow', default_offset_account=self.coa_utang,
        )
        self.item = ItemMasterPurchase.objects.create(item_id='RM-0001', nama='Bahan', tipe_item='RM')
        self.purchase = PurchaseHeader.objects.create(transaction_id='PUR-INV-001', tanggal='2026-04-28', deskripsi='Test')
        self.purchase_group = PurchaseEntitasBisnis.objects.create(
            purchase_header=self.purchase,
            entitas_bisnis=self.eb,
        )
        self.purchase_item = PurchaseItem.objects.create(
            purchase_eb=self.purchase_group,
            item=self.item,
            sub_transaction_type=self.sub_type,
            coa_account=self.coa_cash,
            offset_coa_account=self.coa_utang,
            quantity=Decimal('10'),
            unit_price=Decimal('10000'),
        )

    def test_create_utang_for_purchase(self):
        utang_headers = create_utang_for_purchase(self.purchase)
        self.assertEqual(len(utang_headers), 1)
        utang = utang_headers[0]
        self.assertEqual(utang.total_amount, Decimal('100000'))
        self.assertEqual(utang.status, 'open')
        self.assertEqual(utang.details.count(), 1)

    def test_utang_payment(self):
        utang_headers = create_utang_for_purchase(self.purchase)
        utang = utang_headers[0]
        detail = utang.details.first()
        payment = create_utang_payment(
            utang,
            utang_detail=detail,
            tanggal='2026-04-28',
            coa_account=self.coa_cash,
            jumlah=Decimal('50000'),
            keterangan='Bayar parsial',
        )
        utang.refresh_from_db()
        self.assertEqual(utang.status, 'partial')
        self.assertEqual(utang.paid_amount, Decimal('50000'))
        self.assertIsNotNone(payment.jurnal_header)

    def test_reverse_utang_for_purchase(self):
        utang_headers = create_utang_for_purchase(self.purchase)
        self.assertEqual(UtangHeader.objects.count(), 1)
        reverse_utang_for_purchase(self.purchase)
        self.assertEqual(UtangHeader.objects.count(), 0)
