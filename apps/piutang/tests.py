from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun

from .models import PiutangHeader, PiutangDetail, PiutangAuditLog
from .services import create_manual_piutang


def make_fixtures():
    tipe = TipeEntitas.objects.create(nama='Pelanggan')
    eb = EntitasBisnis.objects.create(nama='PT Klien', tipe_entitas=tipe, relasi='pelanggan')
    coa_piutang = Akun.objects.create(kategori_id='aset', nama='Piutang Dagang', kode_akun='1.2.1')
    coa_kas = Akun.objects.create(kategori_id='aset', nama='Kas', kode_akun='1.1.1')
    coa_pendapatan = Akun.objects.create(kategori_id='pendapatan', nama='Pendapatan Jasa', kode_akun='4.1.1')
    return {
        'tipe': tipe, 'eb': eb,
        'coa_piutang': coa_piutang, 'coa_kas': coa_kas, 'coa_pendapatan': coa_pendapatan,
    }


class CreateManualPiutangTests(TestCase):
    def setUp(self):
        self.f = make_fixtures()

    def test_creates_header_with_correct_fields(self):
        piutang = create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='PT Klien',
            deskripsi='Test piutang',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=date(2026, 7, 7),
            details=[{'deskripsi': 'Jasa konsultasi', 'jumlah': Decimal('1000000')}],
        )
        self.assertIsNotNone(piutang.pk)
        self.assertTrue(piutang.nomor_piutang.startswith('TRX-PIU-'))
        self.assertEqual(piutang.jumlah_pokok, Decimal('1000000'))
        self.assertEqual(piutang.status, 'draft')
        self.assertEqual(piutang.details.count(), 1)

    def test_creates_audit_log(self):
        create_manual_piutang(
            tanggal=date(2026, 6, 7),
            entitas_bisnis=self.f['eb'],
            debitur='',
            deskripsi='',
            coa_piutang_account=self.f['coa_piutang'],
            jatuh_tempo=None,
            details=[{'deskripsi': 'Item', 'jumlah': Decimal('500000')}],
        )
        self.assertEqual(PiutangAuditLog.objects.filter(action='CREATED').count(), 1)

    def test_raises_if_no_details(self):
        with self.assertRaises(ValueError):
            create_manual_piutang(
                tanggal=date(2026, 6, 7), entitas_bisnis=self.f['eb'],
                debitur='', deskripsi='', coa_piutang_account=self.f['coa_piutang'],
                jatuh_tempo=None, details=[],
            )

    def test_auto_number_increments(self):
        p1 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='X',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'A', 'jumlah': Decimal('100')}],
        )
        p2 = create_manual_piutang(
            tanggal=date(2026, 6, 7), entitas_bisnis=None, debitur='Y',
            deskripsi='', coa_piutang_account=self.f['coa_piutang'], jatuh_tempo=None,
            details=[{'deskripsi': 'B', 'jumlah': Decimal('200')}],
        )
        n1 = int(p1.nomor_piutang.rsplit('-', 1)[1])
        n2 = int(p2.nomor_piutang.rsplit('-', 1)[1])
        self.assertEqual(n2, n1 + 1)
