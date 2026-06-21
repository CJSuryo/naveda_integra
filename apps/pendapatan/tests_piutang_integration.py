from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.master_data.models import Akun
from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.pendapatan.models import (
    KewajibabPelaksanaan,
    PendapatanEntitasBisnis,
    PendapatanHeader,
    PendapatanPiutangProfil,
    PIUTANG_PROFIL_FIELDS,
)
from apps.purchase.models import SubTransactionType


def _akun(kode, nama, kategori_id='aset'):
    return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)


class PendapatanPiutangProfilModelTest(TestCase):
    def test_profil_one_to_one_with_header(self):
        akun_piutang = _akun('1.1.4', 'Piutang Usaha')
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft',
        )
        profil = PendapatanPiutangProfil.objects.create(
            pendapatan_header=header,
            debitur='PT Maju',
            coa_piutang_account=akun_piutang,
        )
        self.assertEqual(header.piutang_profil, profil)
        self.assertEqual(profil.debitur, 'PT Maju')
        # Constant lists the fields the modal mirrors from PiutangHeader.
        self.assertIn('coa_piutang_account', PIUTANG_PROFIL_FIELDS)
        self.assertIn('jatuh_tempo', PIUTANG_PROFIL_FIELDS)


class AdapterTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)

    def _tipe_entitas(self):
        return TipeEntitas.objects.create(nama='Umum')

    def _stt(self):
        akun = self._akun('2.1.1', 'Offset')
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=akun)

    def test_adapter_maps_profil_and_kp_items(self):
        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        tipe = self._tipe_entitas()
        eb = EntitasBisnis.objects.create(nama='PT Alpha', standar_akuntansi='psak', tipe_entitas=tipe)
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb)
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group, deskripsi_item='Jasa konsultasi', kategori='jasa',
            sub_transaction_type=self._stt(), nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend)
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header, debitur='PT Alpha',
            coa_piutang_account=akun_piutang, jenis_bunga='flat',
            suku_bunga=Decimal('10'))

        from apps.pendapatan.services import pendapatan_to_piutang_payload
        payload, details = pendapatan_to_piutang_payload(header)

        self.assertEqual(payload['debitur'], 'PT Alpha')
        self.assertEqual(payload['coa_piutang_account'], akun_piutang)
        self.assertEqual(payload['jenis_bunga'], 'flat')
        self.assertEqual(payload['tanggal'], header.tanggal)
        self.assertEqual(payload['entitas_bisnis'], eb)
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]['deskripsi'], 'Jasa konsultasi')
        self.assertEqual(details[0]['jumlah'], Decimal('2000'))
        self.assertEqual(details[0]['revenue_account'], akun_pend)

    def test_adapter_raises_without_profil(self):
        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 1, 10), payment_type='credit', status='draft')
        from apps.pendapatan.services import pendapatan_to_piutang_payload
        with self.assertRaises(ValueError):
            pendapatan_to_piutang_payload(header)


class ConfirmCreditTest(TestCase):
    def _akun(self, kode, nama, kategori_id='aset'):
        return Akun.objects.create(kode_akun=kode, nama=nama, kategori_id=kategori_id)

    def _stt(self, akun_offset=None):
        if akun_offset is None:
            akun_offset = self._akun('2.1.9', 'Offset')
        return SubTransactionType.objects.create(
            nama='Pendapatan Jasa', module='pendapatan', direction='inflow',
            default_offset_account=akun_offset)

    def test_confirm_credit_builds_full_piutang_and_books_ar(self):
        from apps.jurnal.models import JurnalDetail
        from apps.piutang.models import PiutangHeader
        from apps.pendapatan.services import confirm_pendapatan

        akun_piutang = self._akun('1.1.4', 'Piutang Usaha')
        akun_pend = self._akun('4.1.1', 'Pendapatan Jasa', kategori_id='pendapatan')
        # A separate cash account — NOT the piutang account — is set as payment_account
        # so the test can prove the debit came from profil.coa_piutang_account, not pay_acct.
        akun_kas = self._akun('1.1.1', 'Kas')

        tipe = TipeEntitas.objects.create(nama='Umum')
        eb = EntitasBisnis.objects.create(nama='PT Beta', standar_akuntansi='psak', tipe_entitas=tipe)

        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 3, 15), payment_type='credit', status='draft',
        )
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb,
            payment_account=akun_kas,  # cash account — should NOT be debited
        )
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item='Jasa konsultasi kredit',
            kategori='jasa',
            sub_transaction_type=self._stt(),
            nilai_kontrak=Decimal('2000'),
            revenue_account=akun_pend,
            recognition_type=KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME,
        )
        PendapatanPiutangProfil.objects.create(
            pendapatan_header=header,
            debitur='PT Beta',
            coa_piutang_account=akun_piutang,
            jenis_bunga='flat',
            suku_bunga=Decimal('10'),
        )

        confirm_pendapatan(header, user=None)
        header.refresh_from_db()
        self.assertEqual(header.status, 'confirmed')

        # Full piutang created with credit terms from profil.
        piutang = PiutangHeader.objects.get(source_pendapatan=header)
        self.assertEqual(piutang.jumlah_pokok, Decimal('2000'))
        self.assertEqual(piutang.jenis_bunga, 'flat')
        self.assertEqual(piutang.coa_piutang_account, akun_piutang)

        # AR journal debits the piutang account (not the cash/payment account).
        debit_lines = JurnalDetail.objects.filter(akun=akun_piutang, debit=Decimal('2000'))
        self.assertTrue(debit_lines.exists(), 'Expected debit on piutang account, found none.')

        # Cash account must NOT be debited.
        cash_debit = JurnalDetail.objects.filter(akun=akun_kas, debit__gt=0)
        self.assertFalse(cash_debit.exists(), 'Cash account should not be debited for credit PIT.')

    def test_confirm_credit_raises_without_profil(self):
        from apps.pendapatan.services import confirm_pendapatan

        akun_pend = self._akun('4.1.2', 'Pendapatan Jasa 2', kategori_id='pendapatan')
        akun_kas = self._akun('1.1.2', 'Kas 2')
        tipe = TipeEntitas.objects.create(nama='Lainnya')
        eb = EntitasBisnis.objects.create(nama='PT Gamma', standar_akuntansi='psak', tipe_entitas=tipe)

        header = PendapatanHeader.objects.create(
            tanggal=date(2026, 3, 15), payment_type='credit', status='draft',
        )
        eb_group = PendapatanEntitasBisnis.objects.create(
            pendapatan_header=header, entitas_bisnis=eb, payment_account=akun_kas,
        )
        KewajibabPelaksanaan.objects.create(
            pendapatan_eb=eb_group,
            deskripsi_item='Jasa tanpa profil',
            kategori='jasa',
            sub_transaction_type=self._stt(akun_kas),
            nilai_kontrak=Decimal('1000'),
            revenue_account=akun_pend,
            recognition_type=KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME,
        )
        # No PendapatanPiutangProfil created — should raise ValueError.
        with self.assertRaises(ValueError):
            confirm_pendapatan(header, user=None)
