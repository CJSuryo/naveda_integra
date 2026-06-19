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
                'tax_type': 'ppn_keluaran',
                'tax': Decimal('110000'),          # manual override → skips TarifPajak lookup
                'tax_account': self.f['coa_ppn'],
                'tax_payment_account': self.f['coa_kas'],
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
                'tax_type': 'ppn_keluaran',
                'tax': Decimal('110000'),
                'tax_account': self.f['coa_ppn'],
                'tax_payment_account': self.f['coa_kas'],
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
