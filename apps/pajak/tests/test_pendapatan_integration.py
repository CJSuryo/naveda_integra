from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType
from apps.jurnal.models import JurnalHeader
from apps.pendapatan.services import create_pendapatan_header, confirm_pendapatan, void_pendapatan
from apps.pajak.models import PajakTransaksi


def make_base_fixtures():
    tipe = TipeEntitas.objects.create(nama='Penyewa')
    eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Usaha', kode_akun='1.2.1')
    coa_revenue = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Jasa', kode_akun='4.1.1')
    coa_ppn = Akun.objects.create(kategori_id='kewajiban', nama='Utang PPN', kode_akun='2.1.1')
    stt = SubTransactionType.objects.create(
        nama='Jasa', module='pendapatan', direction='inflow',
        default_offset_account=coa_revenue,
    )
    return {
        'eb': eb, 'coa_kas': coa_kas, 'coa_piutang': coa_piutang,
        'coa_revenue': coa_revenue, 'coa_ppn': coa_ppn, 'stt': stt,
    }


class ConfirmPendapatanTaxIntegrationTest(TestCase):
    """
    Integration test: confirm_pendapatan delegates tax creation to apps.pajak
    for KPs that have a tax_type configured.
    """

    def setUp(self):
        self.f = make_base_fixtures()

    def _make_header_with_tax(self):
        """
        Create a PendapatanHeader (cash, POINT_IN_TIME) with a KP that has
        PPN keluaran configured. Use manual tax amount to avoid needing TarifPajak.
        """
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa konsultasi dengan PPN',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi A',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('1000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_lines': [{
                    'tax_type': 'ppn_keluaran',
                    'tax': Decimal('110000'),          # manual override → skips TarifPajak lookup
                    'tax_account': self.f['coa_ppn'],
                    'tax_payment_account': self.f['coa_kas'],
                }],
            }],
        )
        return header

    def test_pajak_transaksi_created_after_confirm(self):
        """After confirm, a PajakTransaksi should exist for the KP."""
        header = self._make_header_with_tax()
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        self.assertTrue(
            PajakTransaksi.objects.filter(
                source_type='pendapatan_kp',
                source_id=kp.pk,
            ).exists()
        )

    def test_pajak_transaksi_status_is_final(self):
        """The PajakTransaksi created at confirm should have status='final'."""
        header = self._make_header_with_tax()
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        pajak_trx = PajakTransaksi.objects.get(
            source_type='pendapatan_kp',
            source_id=kp.pk,
        )
        self.assertEqual(pajak_trx.status, 'final')

    def test_pajak_jurnal_header_number_starts_with_trx_paj(self):
        """The journal created by confirm_pajak should start with TRX-PAJ."""
        header = self._make_header_with_tax()
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        pajak_trx = PajakTransaksi.objects.get(
            source_type='pendapatan_kp',
            source_id=kp.pk,
        )
        self.assertIsNotNone(pajak_trx.jurnal_header)
        self.assertTrue(
            pajak_trx.jurnal_header.nomor_transaksi.startswith('TRX-PAJ'),
            f'Expected TRX-PAJ prefix, got: {pajak_trx.jurnal_header.nomor_transaksi}',
        )

    def _make_header_with_pph23(self, coa_pph23):
        """
        Create a PendapatanHeader (cash) with a KP that has PPh 23 configured.
        Manual tax amount → skips TarifPajak lookup. tax_account is the PPh
        prepaid asset, tax_payment_account is Kas (the offset).
        """
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa konsultasi dengan PPh 23',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi PPh23',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('1000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_lines': [{
                    'tax_type': 'pph_23',
                    'tax': Decimal('2000'),            # manual override → skips TarifPajak lookup
                    'tax_account': coa_pph23,
                    'tax_payment_account': self.f['coa_kas'],
                }],
            }],
        )
        return header

    def test_pph23_sifat_pajak_is_prepaid(self):
        """A PPh 23 KP must produce a PajakTransaksi with sifat_pajak='prepaid'."""
        coa_pph23 = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dibayar Dimuka', kode_akun='1.3.1',
        )
        header = self._make_header_with_pph23(coa_pph23)
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        pajak_trx = PajakTransaksi.objects.get(
            source_type='pendapatan_kp', source_id=kp.pk,
        )
        self.assertEqual(pajak_trx.sifat_pajak, 'prepaid')

    def test_pph23_journal_direction_dr_pajak_cr_lawan(self):
        """
        For PPh 23 (prepaid), the journal must debit the tax account (akun_pajak)
        and credit the offset account (akun_lawan / Kas).
        """
        coa_pph23 = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dibayar Dimuka', kode_akun='1.3.1',
        )
        header = self._make_header_with_pph23(coa_pph23)
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        pajak_trx = PajakTransaksi.objects.get(
            source_type='pendapatan_kp', source_id=kp.pk,
        )
        self.assertIsNotNone(pajak_trx.jurnal_header)

        details = list(pajak_trx.jurnal_header.details.all())
        debit_detail = next(d for d in details if d.debit > 0)
        kredit_detail = next(d for d in details if d.kredit > 0)

        # prepaid: Dr akun_pajak (PPh DDM), Cr akun_lawan (Kas)
        self.assertEqual(debit_detail.akun_id, coa_pph23.pk)
        self.assertEqual(kredit_detail.akun_id, self.f['coa_kas'].pk)
        self.assertEqual(debit_detail.debit, Decimal('2000'))
        self.assertEqual(kredit_detail.kredit, Decimal('2000'))

    def test_no_pajak_transaksi_when_no_tax_type(self):
        """KPs without a tax_type must not create any PajakTransaksi."""
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa tanpa pajak',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi B',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('500000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
            }],
        )
        confirm_pendapatan(header, user=None)
        self.assertEqual(PajakTransaksi.objects.count(), 0)

    def test_ppn_and_pph23_on_same_kp_creates_two_pajak_transaksi(self):
        """A KP with both PPN Keluaran and PPh 23 creates two PajakTransaksi records."""
        coa_pph23 = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dibayar Dimuka Test', kode_akun='1.3.2',
        )
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa dengan PPN + PPh 23',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Jasa Dual Tax',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('1000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_lines': [
                    {
                        'tax_type': 'ppn_keluaran',
                        'tax': Decimal('110000'),
                        'tax_account': self.f['coa_ppn'],
                        'tax_payment_account': self.f['coa_kas'],
                    },
                    {
                        'tax_type': 'pph_23',
                        'tax': Decimal('20000'),
                        'tax_account': coa_pph23,
                        'tax_payment_account': self.f['coa_kas'],
                    },
                ],
            }],
        )
        confirm_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        pajak_qs = PajakTransaksi.objects.filter(
            source_type='pendapatan_kp', source_id=kp.pk,
        )
        self.assertEqual(pajak_qs.count(), 2)
        jenis_list = sorted(pajak_qs.values_list('jenis_pajak', flat=True))
        self.assertIn('ppn_umum', jenis_list)
        self.assertIn('pph_23_jasa', jenis_list)

        ppn = pajak_qs.get(jenis_pajak='ppn_umum')
        self.assertEqual(ppn.jumlah_pajak, Decimal('110000'))
        self.assertEqual(ppn.status, 'final')

        pph = pajak_qs.get(jenis_pajak='pph_23_jasa')
        self.assertEqual(pph.jumlah_pajak, Decimal('20000'))
        self.assertEqual(pph.sifat_pajak, 'prepaid')
        self.assertEqual(pph.status, 'final')

    def test_void_cancels_all_tax_lines(self):
        """void_pendapatan cancels all PajakTransaksi for a dual-tax KP."""
        coa_pph23 = Akun.objects.create(
            kategori_id='aset', nama='PPh 23 Dimuka Void Test', kode_akun='1.3.3',
        )
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Dual tax void test',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Jasa Dual Void',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('500000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_lines': [
                    {'tax_type': 'ppn_keluaran', 'tax': Decimal('55000'),
                     'tax_account': self.f['coa_ppn'], 'tax_payment_account': self.f['coa_kas']},
                    {'tax_type': 'pph_23', 'tax': Decimal('10000'),
                     'tax_account': coa_pph23, 'tax_payment_account': self.f['coa_kas']},
                ],
            }],
        )
        confirm_pendapatan(header, user=None)
        void_pendapatan(header, user=None)

        kp = header.entitas_groups.first().items.first()
        cancelled = PajakTransaksi.objects.filter(
            source_type='pendapatan_kp', source_id=kp.pk, status='dibatalkan',
        )
        self.assertEqual(cancelled.count(), 2)


class VoidPendapatanTaxIntegrationTest(TestCase):
    """
    Integration test: void_pendapatan cancels linked PajakTransaksi records
    (status → 'dibatalkan') and posts reversal journals for the tax.
    """

    def setUp(self):
        self.f = make_base_fixtures()

    def _make_confirmed_header_with_tax(self):
        """Create and confirm a cash PIT header that has PPN keluaran configured."""
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa konsultasi dengan PPN (void test)',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi void',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('1000000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
                'tax_lines': [{
                    'tax_type': 'ppn_keluaran',
                    'tax': Decimal('110000'),
                    'tax_account': self.f['coa_ppn'],
                    'tax_payment_account': self.f['coa_kas'],
                }],
            }],
        )
        confirm_pendapatan(header, user=None)
        return header

    def test_void_cancels_pajak_transaksi(self):
        """After void_pendapatan, PajakTransaksi status must be 'dibatalkan'."""
        header = self._make_confirmed_header_with_tax()
        kp = header.entitas_groups.first().items.first()

        # Sanity: pajak exists and is final before void
        pajak_trx = PajakTransaksi.objects.get(
            source_type='pendapatan_kp', source_id=kp.pk,
        )
        self.assertEqual(pajak_trx.status, 'final')

        void_pendapatan(header, user=None)

        pajak_trx.refresh_from_db()
        self.assertEqual(pajak_trx.status, 'dibatalkan')

    def test_void_creates_reversal_pajak_journal(self):
        """void_pendapatan must create a reversal JurnalHeader (is_penyesuaian=True) for the tax."""
        header = self._make_confirmed_header_with_tax()

        penyesuaian_before = JurnalHeader.objects.filter(is_penyesuaian=True).count()

        void_pendapatan(header, user=None)

        penyesuaian_after = JurnalHeader.objects.filter(is_penyesuaian=True).count()
        # At minimum 2 reversal journals: one for TRX-PND-J and one for TRX-PAJ
        self.assertGreater(penyesuaian_after, penyesuaian_before + 1)

    def test_void_no_pajak_transaksi_unchanged_when_no_tax(self):
        """void_pendapatan on a KP without tax_type must not create or cancel any PajakTransaksi."""
        header = create_pendapatan_header(
            tanggal=date(2026, 6, 1),
            deskripsi='Jasa tanpa pajak (void test)',
            payment_type='cash',
            entitas_bisnis=self.f['eb'],
            payment_account=self.f['coa_kas'],
            items=[{
                'deskripsi_item': 'Konsultasi C',
                'kategori': 'jasa',
                'sub_transaction_type': self.f['stt'],
                'jumlah_bruto': Decimal('500000'),
                'revenue_account': self.f['coa_revenue'],
                'payment_account': self.f['coa_kas'],
            }],
        )
        confirm_pendapatan(header, user=None)
        self.assertEqual(PajakTransaksi.objects.count(), 0)

        void_pendapatan(header, user=None)
        self.assertEqual(PajakTransaksi.objects.count(), 0)
