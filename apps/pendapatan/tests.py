from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType

from .models import PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog
from .services import confirm_pendapatan, create_pendapatan_header


def make_fixtures():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT Sewa', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang', kode_akun='1.2.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1')
    stt = SubTransactionType.objects.create(
        nama='Sewa', module='pendapatan', direction='inflow',
        default_offset_account=coa_revenue,
    )
    return {'tipe': tipe, 'eb': eb, 'coa_kas': coa_kas, 'coa_piutang': coa_piutang,
            'coa_revenue': coa_revenue, 'stt': stt}


def make_header(f, payment_type='cash'):
    header = create_pendapatan_header(
        tanggal=date(2026, 6, 1),
        deskripsi='Sewa bulan Juni',
        payment_type=payment_type,
        entitas_bisnis=f['eb'],
        payment_account=f['coa_kas'] if payment_type == 'cash' else f['coa_piutang'],
        items=[{
            'deskripsi_item': 'Sewa Gedung A',
            'kategori': 'sewa',
            'sub_transaction_type': f['stt'],
            'jumlah_bruto': Decimal('5000000'),
            'revenue_account': f['coa_revenue'],
            'payment_account': f['coa_kas'] if payment_type == 'cash' else f['coa_piutang'],
        }],
    )
    return header


class CreatePendapatanHeaderTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_header_with_draft_status(self):
        header = make_header(self.f)
        self.assertEqual(header.status, 'draft')
        self.assertTrue(header.transaction_id.startswith('TRX-PND-'))

    def test_creates_eb_group_and_item(self):
        header = make_header(self.f)
        self.assertEqual(header.entitas_groups.count(), 1)
        eb_group = header.entitas_groups.first()
        self.assertEqual(eb_group.items.count(), 1)

    def test_logs_created_event(self):
        make_header(self.f)
        self.assertEqual(PendapatanEventLog.objects.filter(event_type='CREATED').count(), 1)


class ConfirmPendapatanCashTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.header = make_header(self.f, payment_type='cash')

    def test_status_becomes_confirmed(self):
        confirm_pendapatan(self.header)
        self.header.refresh_from_db()
        self.assertEqual(self.header.status, 'confirmed')

    def test_generates_journal(self):
        from apps.jurnal.models import JurnalHeader
        confirm_pendapatan(self.header)
        self.assertGreater(JurnalHeader.objects.count(), 0)

    def test_cash_journal_dr_payment_cr_revenue(self):
        confirm_pendapatan(self.header)
        from apps.jurnal.models import JurnalDetail
        dr = JurnalDetail.objects.filter(debit__gt=0).first()
        cr = JurnalDetail.objects.filter(kredit__gt=0).first()
        self.assertEqual(dr.akun, self.f['coa_kas'])
        self.assertEqual(cr.akun, self.f['coa_revenue'])

    def test_raises_if_already_confirmed(self):
        confirm_pendapatan(self.header)
        self.header.refresh_from_db()
        with self.assertRaises(ValueError):
            confirm_pendapatan(self.header)


class ConfirmPendapatanCreditTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()
        self.header = make_header(self.f, payment_type='credit')

    def test_creates_piutang_header(self):
        from apps.piutang.models import PiutangHeader
        confirm_pendapatan(self.header)
        self.assertEqual(PiutangHeader.objects.filter(source_pendapatan=self.header).count(), 1)

    def test_credit_journal_dr_piutang_cr_revenue(self):
        confirm_pendapatan(self.header)
        from apps.jurnal.models import JurnalDetail
        dr = JurnalDetail.objects.filter(debit__gt=0).first()
        cr = JurnalDetail.objects.filter(kredit__gt=0).first()
        self.assertEqual(dr.akun, self.f['coa_piutang'])
        self.assertEqual(cr.akun, self.f['coa_revenue'])
