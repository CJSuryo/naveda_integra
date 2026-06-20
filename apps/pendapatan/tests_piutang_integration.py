from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.master_data.models import Akun
from apps.pendapatan.models import (
    PendapatanHeader,
    PendapatanPiutangProfil,
    PIUTANG_PROFIL_FIELDS,
)


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
