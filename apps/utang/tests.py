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


class ReverseUtangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_reverse_utang_header_writes_utang_terhapus(self):
        headers = create_utang_for_purchase(self.f['purchase'])
        utang = headers[0]
        reverse_utang_header(utang, user=None)
        self.assertEqual(UtangTerhapus.objects.count(), 1)
        record = UtangTerhapus.objects.first()
        self.assertIn('total_amount', record.snapshot)
        self.assertEqual(record.nomor_utang, utang.nomor_utang)

    def test_reverse_utang_header_deletes_payment_journals_not_purchase_journals(self):
        from apps.jurnal.models import JurnalHeader
        create_automated_journals(self.f['purchase'])
        journal_count_before = JurnalHeader.objects.count()
        headers = create_utang_for_purchase(self.f['purchase'])
        utang = headers[0]
        payment = create_utang_payment(
            utang,
            utang_detail=utang.details.first(),
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('10000'),
            keterangan='Test',
        )
        self.assertIsNotNone(payment.jurnal_header)
        payment_journal_id = payment.jurnal_header_id
        reverse_utang_header(utang, user=None)
        self.assertFalse(JurnalHeader.objects.filter(pk=payment_journal_id).exists())
        self.assertEqual(JurnalHeader.objects.count(), journal_count_before)

    def test_reverse_utang_for_purchase_clears_all_utang(self):
        create_utang_for_purchase(self.f['purchase'])
        self.assertEqual(UtangHeader.objects.count(), 1)
        reverse_utang_for_purchase(self.f['purchase'])
        self.assertEqual(UtangHeader.objects.count(), 0)
        self.assertEqual(UtangTerhapus.objects.count(), 1)


class UtangPaymentTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]
        self.detail = self.utang.details.first()

    def test_payment_creates_journal_and_updates_status(self):
        payment = create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('50000'),
            keterangan='Bayar parsial',
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'partial')
        self.assertIsNotNone(payment.jurnal_header)

    def test_overpayment_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_utang_payment(
                self.utang,
                utang_detail=self.detail,
                tanggal=date(2026, 4, 28),
                coa_account=self.f['coa_cash'],
                jumlah=Decimal('200000'),
                keterangan='Overpay',
            )

    def test_full_payment_sets_paid_status(self):
        create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('100000'),
            keterangan='Lunas',
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'paid')

    def test_reverse_utang_payment_deletes_journal_and_recalculates_status(self):
        from apps.jurnal.models import JurnalHeader
        payment = create_utang_payment(
            self.utang,
            utang_detail=self.detail,
            tanggal=date(2026, 4, 28),
            coa_account=self.f['coa_cash'],
            jumlah=Decimal('50000'),
            keterangan='Bayar',
        )
        payment_journal_id = payment.jurnal_header_id
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'partial')

        reverse_utang_payment(payment)

        self.assertFalse(JurnalHeader.objects.filter(pk=payment_journal_id).exists())
        self.assertFalse(
            self.utang.pembayaran.filter(pk=payment.pk).exists()
        )
        self.utang.refresh_from_db()
        self.assertEqual(self.utang.status, 'open')


class UtangReportingTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]

    def test_get_utang_per_subjek_returns_open_utang(self):
        from .services import get_utang_per_subjek
        result = list(get_utang_per_subjek())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['entitas_bisnis__nama'], 'PT Demo')
        self.assertEqual(result[0]['jumlah_invoice'], 1)

    def test_get_utang_per_group_akun_returns_kewajiban_sum(self):
        from .services import get_utang_per_group_akun
        result = list(get_utang_per_group_akun())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['total'], Decimal('100000'))

    def test_get_utang_aging_buckets_current(self):
        from .services import get_utang_aging
        from django.utils import timezone
        self.utang.tanggal_jatuh_tempo = date(2099, 1, 1)
        self.utang.save()
        buckets = get_utang_aging()
        self.assertEqual(len(buckets['current']), 1)
        self.assertEqual(len(buckets['due_1_30']), 0)

    def test_get_utang_jatuh_tempo_returns_upcoming(self):
        from .services import get_utang_jatuh_tempo
        from django.utils import timezone
        tomorrow = timezone.now().date() + timedelta(days=1)
        self.utang.tanggal_jatuh_tempo = tomorrow
        self.utang.save()
        result = list(get_utang_jatuh_tempo(hari_ke_depan=7))
        self.assertEqual(len(result), 1)

    def test_get_utang_jatuh_tempo_excludes_far_future(self):
        from .services import get_utang_jatuh_tempo
        self.utang.tanggal_jatuh_tempo = date(2099, 1, 1)
        self.utang.save()
        result = list(get_utang_jatuh_tempo(hari_ke_depan=7))
        self.assertEqual(len(result), 0)


class UtangFormTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        headers = create_utang_for_purchase(self.f['purchase'])
        self.utang = headers[0]

    def test_payment_form_utang_detail_scoped_to_header(self):
        from .forms import UtangPembayaranForm
        from apps.purchase.models import PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem
        purchase2 = PurchaseHeader.objects.create(
            transaction_id='PUR-INV-0002', tanggal=date(2026, 4, 29), deskripsi='Test2',
        )
        pg2 = PurchaseEntitasBisnis.objects.create(
            purchase_header=purchase2, entitas_bisnis=self.f['eb'],
        )
        PurchaseItem.objects.create(
            purchase_eb=pg2,
            item=self.f['item'],
            sub_transaction_type=self.f['sub_type'],
            coa_account=self.f['coa_cash'],
            offset_coa_account=self.f['coa_utang'],
            quantity=Decimal('1'),
            unit_price=Decimal('1000'),
        )
        create_utang_for_purchase(purchase2)
        form = UtangPembayaranForm(utang_header=self.utang)
        self.assertEqual(form.fields['utang_detail'].queryset.count(), 1)

    def test_payment_form_coa_filtered_to_aset(self):
        from .forms import UtangPembayaranForm
        form = UtangPembayaranForm(utang_header=self.utang)
        for akun in form.fields['coa_account'].queryset:
            self.assertEqual(akun.kategori_id, 'aset')

    def test_header_form_filters_entitas_to_pemasok(self):
        from .forms import UtangHeaderForm
        tipe = self.f['tipe']
        EntitasBisnis.objects.create(
            nama='PT Pelanggan', tipe_entitas=tipe, relasi='pelanggan',
        )
        form = UtangHeaderForm()
        for eb in form.fields['entitas_bisnis'].queryset:
            self.assertIn(eb.relasi, ['pemasok', 'keduanya'])


class UtangModelV1Test(TestCase):
    def test_utang_header_has_jenis_utang(self):
        self.assertIn('jenis_utang', [f.name for f in UtangHeader._meta.get_fields()])

    def test_utang_header_has_kreditor(self):
        self.assertIn('kreditor', [f.name for f in UtangHeader._meta.get_fields()])

    def test_utang_header_has_requires_approval(self):
        self.assertIn('requires_approval', [f.name for f in UtangHeader._meta.get_fields()])

    def test_utang_attachment_model_exists(self):
        from apps.utang.models import UtangAttachment
        self.assertTrue(hasattr(UtangAttachment, 'utang_header'))

    def test_utang_audit_log_model_exists(self):
        from apps.utang.models import UtangAuditLog
        self.assertTrue(hasattr(UtangAuditLog, 'action'))


from decimal import Decimal
from apps.utang.services import create_manual_utang, approve_utang, reject_utang
from apps.master_data.models import Akun


class UtangServicesV1Test(TestCase):
    def setUp(self):
        self.akun_utang = Akun.objects.create(kode_akun='2100', nama='Utang Usaha', kategori_id='kewajiban')
        self.akun_kas = Akun.objects.create(kode_akun='1100', nama='Kas', kategori_id='aset')

    def _detail(self, amount='100000'):
        return [{'coa_utang_account': self.akun_utang, 'description': 'Test', 'amount': Decimal(amount)}]

    def test_create_no_approval_goes_to_open(self):
        utang = create_manual_utang(
            tanggal='2026-06-02', entitas_bisnis=None, deskripsi='Test',
            jenis_utang='usaha', kreditor='Vendor A', nomor_referensi='INV-001',
            kategori_jangka_waktu='short_term', coa_source_account=self.akun_kas,
            requires_approval=False, tanggal_jatuh_tempo=None,
            details=self._detail(), user=None,
        )
        self.assertEqual(utang.status, 'open')
        self.assertIsNotNone(utang.jurnal_pembentukan)

    def test_create_with_approval_goes_to_draft(self):
        utang = create_manual_utang(
            tanggal='2026-06-02', entitas_bisnis=None, deskripsi='Test',
            jenis_utang='bank', kreditor='Bank BCA', nomor_referensi='PK-001',
            kategori_jangka_waktu='long_term', coa_source_account=self.akun_kas,
            requires_approval=True, tanggal_jatuh_tempo=None,
            details=self._detail('500000000'), user=None,
        )
        self.assertEqual(utang.status, 'draft')
        self.assertIsNone(utang.jurnal_pembentukan)

    def test_approve_utang(self):
        utang = create_manual_utang(
            tanggal='2026-06-02', entitas_bisnis=None, deskripsi='Test',
            jenis_utang='bank', kreditor='Bank BCA', nomor_referensi='PK-001',
            kategori_jangka_waktu='long_term', coa_source_account=self.akun_kas,
            requires_approval=True, tanggal_jatuh_tempo=None,
            details=self._detail('500000000'), user=None,
        )
        approve_utang(utang, user=None)
        utang.refresh_from_db()
        self.assertEqual(utang.approval_status, 'approved')
        self.assertEqual(utang.status, 'open')
        self.assertIsNotNone(utang.jurnal_pembentukan)

    def test_reject_utang(self):
        utang = create_manual_utang(
            tanggal='2026-06-02', entitas_bisnis=None, deskripsi='Test',
            jenis_utang='bank', kreditor='Bank BCA', nomor_referensi='PK-002',
            kategori_jangka_waktu='long_term', coa_source_account=self.akun_kas,
            requires_approval=True, tanggal_jatuh_tempo=None,
            details=self._detail('500000000'), user=None,
        )
        reject_utang(utang, user=None, notes='Data tidak lengkap')
        utang.refresh_from_db()
        self.assertEqual(utang.approval_status, 'rejected')
        self.assertEqual(utang.status, 'cancelled')


from apps.utang.forms import UtangHeaderForm, UtangDetailFormSet


class UtangFormsV1Test(TestCase):
    def test_header_form_has_jenis_utang_field(self):
        form = UtangHeaderForm()
        self.assertIn('jenis_utang', form.fields)

    def test_header_form_has_kreditor_field(self):
        form = UtangHeaderForm()
        self.assertIn('kreditor', form.fields)

    def test_detail_formset_exists(self):
        self.assertIsNotNone(UtangDetailFormSet)
