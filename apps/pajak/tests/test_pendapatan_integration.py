from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.entitas_bisnis.models import EntitasBisnis, TipeEntitas
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType
from apps.pendapatan.services import create_pendapatan_header


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
