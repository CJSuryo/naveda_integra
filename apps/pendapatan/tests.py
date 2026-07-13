from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType

from .models import PendapatanHeader, PendapatanEntitasBisnis, PendapatanItem, PendapatanEventLog, PendapatanPiutangProfil
from .services import confirm_pendapatan, create_pendapatan_header, compute_next_date, generate_from_recurring


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
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=self.header,
            debitur=str(self.f['eb']),
            coa_piutang_account=self.f['coa_piutang'],
        )

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


class ComputeNextDateTests(TestCase):
    def test_harian(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'harian'), date(2026, 1, 16))

    def test_mingguan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'mingguan'), date(2026, 1, 22))

    def test_bulanan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 31), 'bulanan'), date(2026, 2, 28))

    def test_triwulanan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'triwulanan'), date(2026, 4, 15))

    def test_semesteran(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'semesteran'), date(2026, 7, 15))

    def test_tahunan(self):
        self.assertEqual(compute_next_date(date(2026, 1, 15), 'tahunan'), date(2027, 1, 15))

    def test_unknown_frekuensi_raises(self):
        with self.assertRaises(ValueError):
            compute_next_date(date(2026, 1, 1), 'dekade')

    def test_invalid_frekuensi_raises(self):
        from datetime import date
        with self.assertRaises(ValueError):
            compute_next_date(date(2026, 1, 15), 'tidak_dikenal')


class GenerateFromRecurringTests(TestCase):
    def setUp(self):
        from apps.pendapatan.models import RecurringTemplate

        tipe = TipeEntitas.objects.create(nama='Pelanggan')
        self.eb = EntitasBisnis.objects.create(
            nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan'
        )
        self.revenue_akun = Akun.objects.create(
            kategori_id='pendapatan', nama='Pendapatan Sewa', kode_akun='4.1.1'
        )
        self.kas_akun = Akun.objects.create(
            kategori_id='aset', nama='Kas', kode_akun='1.1.1'
        )
        self.stt = SubTransactionType.objects.create(
            nama='Pendapatan Sewa', module='pendapatan', direction='inflow',
            default_offset_account=self.revenue_akun,
        )
        self.template = RecurringTemplate.objects.create(
            nama='Sewa Kantor',
            entitas_bisnis=self.eb,
            deskripsi_item='Sewa bulan berikutnya',
            kategori='jasa',
            sub_transaction_type=self.stt,
            jumlah=Decimal('5000000'),
            revenue_account=self.revenue_akun,
            payment_account=self.kas_akun,
            payment_type='cash',
            frekuensi='bulanan',
            tanggal_mulai=date(2026, 1, 1),
            tanggal_berikutnya=date(2026, 1, 1),
        )

    def test_creates_pendapatan_header(self):
        header = generate_from_recurring(self.template, user=None)
        self.assertIsNotNone(header.pk)
        self.assertEqual(header.source_type, 'recurring')
        self.assertEqual(header.source_recurring, self.template)
        self.assertEqual(header.status, 'draft')

    def test_creates_pendapatan_item(self):
        header = generate_from_recurring(self.template, user=None)
        items = header.entitas_groups.first().items.all()
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.first().jumlah_bruto, Decimal('5000000'))

    def test_advances_tanggal_berikutnya(self):
        generate_from_recurring(self.template, user=None)
        self.template.refresh_from_db()
        self.assertEqual(self.template.tanggal_berikutnya, date(2026, 2, 1))

    def test_deactivates_after_tanggal_selesai(self):
        self.template.tanggal_selesai = date(2026, 1, 31)
        self.template.save()
        generate_from_recurring(self.template, user=None)
        self.template.refresh_from_db()
        self.assertFalse(self.template.is_active)

    def test_auto_confirm_confirms_header(self):
        self.template.auto_confirm = True
        self.template.save()
        header = generate_from_recurring(self.template, user=None)
        self.assertEqual(header.status, 'confirmed')

    def test_logs_recurring_generated_event(self):
        from apps.pendapatan.models import PendapatanEventLog
        header = generate_from_recurring(self.template, user=None)
        self.assertTrue(
            PendapatanEventLog.objects.filter(
                pendapatan_header=header,
                event_type='RECURRING_GENERATED',
            ).exists()
        )


class TaxLineManualFlagTests(TestCase):
    """Baris pajak auto (is_manual=False) tidak boleh terlabel override."""

    def setUp(self):
        from datetime import date as _date
        from apps.pajak.models import TarifPajak, PajakTransaksi
        from .models import KPTaxLine
        self._PajakTransaksi = PajakTransaksi
        self.f = make_fixtures()
        self.coa_pph23 = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dibayar di Muka', kode_akun='1.1.20')
        TarifPajak.objects.create(
            jenis_pajak='pph_23_jasa', nama='PPh 23 Jasa', tarif_persen=Decimal('2.0000'),
            faktor_dpp=Decimal('1.000000'), berlaku_mulai=_date(2026, 1, 1))
        self.KPTaxLine = KPTaxLine

    def _make_header_with_taxline(self, is_manual, tax_value):
        header = make_header(self.f, payment_type='cash')
        kp = header.entitas_groups.first().items.first()
        kp.nilai_kontrak = Decimal('3500000')
        kp.save(update_fields=['nilai_kontrak'])
        self.KPTaxLine.objects.create(
            kp=kp, tax_type='pph_23', tax=tax_value, is_manual=is_manual,
            tax_account=self.coa_pph23, tax_payment_account=self.f['coa_kas'])
        return header

    def test_auto_line_not_overridden_and_recomputed(self):
        # Auto: nilai tersimpan keliru (999), harus dihitung ulang jadi 2% x 3.5jt = 70.000.
        header = self._make_header_with_taxline(is_manual=False, tax_value=Decimal('999'))
        confirm_pendapatan(header)
        pt = self._PajakTransaksi.objects.get(jenis_pajak='pph_23_jasa')
        self.assertFalse(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('70000'))

    def test_manual_line_is_overridden_and_kept(self):
        header = self._make_header_with_taxline(is_manual=True, tax_value=Decimal('65000'))
        confirm_pendapatan(header)
        pt = self._PajakTransaksi.objects.get(jenis_pajak='pph_23_jasa')
        self.assertTrue(pt.is_overridden)
        self.assertEqual(pt.jumlah_pajak, Decimal('65000'))


class InvoiceTotalTaxSifatTests(TestCase):
    """Invoice harus menambah PPN (dipungut) dan mengurangi PPh (dipotong klien)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import KPTaxLine
        self.f = make_fixtures()
        self.coa_utang_ppn = Akun.objects.create(
            kategori_id='kewajiban', nama='Utang PPN Keluaran', kode_akun='2.1.6')
        self.coa_pph23_ddm = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dibayar di Muka', kode_akun='1.1.20')
        self.header = make_header(self.f, payment_type='cash')
        kp = self.header.entitas_groups.first().items.first()
        kp.nilai_kontrak = Decimal('3500000')
        kp.save(update_fields=['nilai_kontrak'])
        # PPN keluaran dipungut (+385.000), PPh 23 dipotong klien (-70.000)
        KPTaxLine.objects.create(
            kp=kp, tax_type='ppn_keluaran', tax=Decimal('385000'),
            tax_account=self.coa_utang_ppn, tax_payment_account=self.f['coa_kas'])
        KPTaxLine.objects.create(
            kp=kp, tax_type='pph_23', tax=Decimal('70000'),
            tax_account=self.coa_pph23_ddm, tax_payment_account=self.f['coa_kas'])
        User = get_user_model()
        self.user = User.objects.create_user(
            email='akuntan@nif.test', password='x')

    def test_invoice_total_subtracts_withholding(self):
        self.client.force_login(self.user)
        resp = self.client.get(f'/pendapatan/{self.header.pk}/invoice/')
        self.assertEqual(resp.status_code, 200)
        gdata = resp.context['eb_groups_data'][0]
        self.assertEqual(gdata['subtotal'], Decimal('3500000'))
        self.assertEqual(gdata['pungut_total'], Decimal('385000'))
        self.assertEqual(gdata['potong_total'], Decimal('70000'))
        # 3.500.000 + 385.000 (PPN) - 70.000 (PPh 23) = 3.815.000, BUKAN 3.955.000
        self.assertEqual(gdata['group_total'], Decimal('3815000'))


class PendapatanInvoicePaymentLabelTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='pend-inv@test.com', password='pass', name='Invoice User')
        self.client.force_login(self.user)
        self.f = make_fixtures()
        self.f['coa_kas'].is_kas_setara = True
        self.f['coa_kas'].save()
        # coa_piutang keeps the default is_kas_setara=False

    def test_cash_header_shows_lunas(self):
        header = make_header(self.f, payment_type='cash')
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')

    def test_credit_header_without_piutang_shows_belum_lunas(self):
        header = make_header(self.f, payment_type='credit')
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Belum Lunas')

    def test_credit_header_with_paid_piutang_shows_lunas(self):
        from apps.piutang.models import PiutangHeader
        header = make_header(self.f, payment_type='credit')
        PiutangHeader.objects.create(
            nomor_piutang='PTG-TEST-002',
            source_type='from_pendapatan',
            source_pendapatan=header,
            coa_piutang_account=self.f['coa_piutang'],
            jumlah_pokok=Decimal('5000000'),
            jumlah_terbayar=Decimal('5000000'),
            status='paid',
        )
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Lunas')
        self.assertNotContains(resp, 'Belum Lunas')

    def test_all_cash_items_label_kas(self):
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Sewa dua gedung, keduanya cash',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[
                {
                    'deskripsi_item': 'Sewa Gedung A',
                    'kategori': 'sewa',
                    'sub_transaction_type': self.f['stt'],
                    'jumlah_bruto': Decimal('5000000'),
                    'revenue_account': self.f['coa_revenue'],
                    'payment_account': self.f['coa_kas'],
                },
                {
                    'deskripsi_item': 'Sewa Gedung B',
                    'kategori': 'sewa',
                    'sub_transaction_type': self.f['stt'],
                    'jumlah_bruto': Decimal('3000000'),
                    'revenue_account': self.f['coa_revenue'],
                    'payment_account': self.f['coa_kas'],
                },
            ],
        )
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Kas')
        self.assertNotContains(resp, 'Kas dan Kredit')

    def test_mixed_items_label_kas_dan_kredit(self):
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Sewa dua gedung, satu cash satu kredit',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[
                {
                    'deskripsi_item': 'Sewa Gedung A',
                    'kategori': 'sewa',
                    'sub_transaction_type': self.f['stt'],
                    'jumlah_bruto': Decimal('5000000'),
                    'revenue_account': self.f['coa_revenue'],
                    'payment_account': self.f['coa_kas'],
                },
                {
                    'deskripsi_item': 'Sewa Gedung B',
                    'kategori': 'sewa',
                    'sub_transaction_type': self.f['stt'],
                    'jumlah_bruto': Decimal('3000000'),
                    'revenue_account': self.f['coa_revenue'],
                    'payment_account': self.f['coa_piutang'],
                },
            ],
        )
        resp = self.client.get(reverse('pendapatan:invoice', args=[header.pk]))
        self.assertContains(resp, 'Kas dan Kredit')
