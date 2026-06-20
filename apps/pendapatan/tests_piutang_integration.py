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
