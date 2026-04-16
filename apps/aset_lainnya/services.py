"""Aset Lainnya services — amortization calculation and journal generation."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.master_data.models import Akun

from .models import AsetLainnyaRecord


# ---------------------------------------------------------------------------
# Amortization Calculation Engine — 4 methods
# ---------------------------------------------------------------------------

def calc_straight_line(total_value: Decimal, nilai_residu: Decimal, masa_manfaat: int) -> Decimal:
    if masa_manfaat <= 0:
        return Decimal('0')
    return (total_value - nilai_residu) / Decimal(masa_manfaat)


def calc_declining_balance(total_value: Decimal, nilai_residu: Decimal,
                           masa_manfaat: int, akumulasi: Decimal) -> Decimal:
    if masa_manfaat <= 0:
        return Decimal('0')
    nilai_buku = total_value - akumulasi
    if nilai_buku <= nilai_residu:
        return Decimal('0')
    rate = Decimal('2') / Decimal(masa_manfaat)
    amortization = nilai_buku * rate
    if (nilai_buku - amortization) < nilai_residu:
        amortization = nilai_buku - nilai_residu
    return max(amortization, Decimal('0'))


def calc_units_of_production(total_value: Decimal, nilai_residu: Decimal,
                             estimasi_unit: Decimal, unit_aktual: Decimal) -> Decimal:
    if not estimasi_unit or estimasi_unit <= 0:
        return Decimal('0')
    return (unit_aktual / estimasi_unit) * (total_value - nilai_residu)


def calc_revenue_based(total_value: Decimal, nilai_residu: Decimal,
                       estimasi_pendapatan: Decimal, pendapatan_aktual: Decimal) -> Decimal:
    if not estimasi_pendapatan or estimasi_pendapatan <= 0:
        return Decimal('0')
    return (pendapatan_aktual / estimasi_pendapatan) * (total_value - nilai_residu)


def calculate_amortization(record: AsetLainnyaRecord,
                           unit_aktual: Decimal = Decimal('0'),
                           pendapatan_aktual: Decimal = Decimal('0')) -> Decimal:
    metode = record.metode_amortisasi or (record.item.metode_amortisasi if record.item else '')
    masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
    residu = record.nilai_residu

    if metode == 'straight_line':
        return calc_straight_line(record.total_value, residu, masa)
    elif metode == 'declining_balance':
        return calc_declining_balance(record.total_value, residu, masa, record.akumulasi_amortisasi)
    elif metode == 'units_of_production':
        return calc_units_of_production(record.total_value, residu,
                                        record.estimasi_unit_produksi or Decimal('0'), unit_aktual)
    elif metode == 'revenue_based':
        return calc_revenue_based(record.total_value, residu, Decimal('0'), pendapatan_aktual)
    return Decimal('0')


# ---------------------------------------------------------------------------
# Journal Generation
# ---------------------------------------------------------------------------

def _next_amortization_journal_number() -> str:
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-AMR-')
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'TRX-AMR-{seq:03d}'


def process_amortization(record: AsetLainnyaRecord, amortization_amount: Decimal,
                         tanggal=None) -> JurnalHeader:
    """Process amortization creating journal entry.

    Debit:  Beban Amortisasi (kode akun 5.1.31.xx)
    Credit: Akumulasi Amortisasi (kode akun 1.3.2.xx)
    """
    if tanggal is None:
        tanggal = timezone.now().date()

    if amortization_amount <= 0:
        raise ValueError('Jumlah amortisasi harus lebih dari 0.')

    nilai_buku = record.total_value - record.akumulasi_amortisasi
    if amortization_amount > nilai_buku - record.nilai_residu:
        raise ValueError(
            f'Jumlah amortisasi ({amortization_amount:,.0f}) melebihi '
            f'nilai buku yang dapat diamortisasi ({nilai_buku - record.nilai_residu:,.0f}).'
        )

    beban_akun = Akun.objects.filter(kode_akun__startswith='5.1.31').first()
    akumulasi_akun = Akun.objects.filter(kode_akun__startswith='1.3.2').first()

    if not beban_akun:
        raise ValueError('Akun Beban Amortisasi (5.1.31.xx) belum tersedia di Chart of Accounts.')
    if not akumulasi_akun:
        raise ValueError('Akun Akumulasi Amortisasi (1.3.2.xx) belum tersedia di Chart of Accounts.')

    with transaction.atomic():
        record.akumulasi_amortisasi += amortization_amount
        record.save()

        nomor = _next_amortization_journal_number()
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Amortisasi {record.aset_number} — {record.item.nama}',
            entitas_bisnis=record.entitas_bisnis,
            is_penyesuaian=True,
        )

        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=beban_akun,
                debit=amortization_amount,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=akumulasi_akun,
                debit=Decimal('0'),
                kredit=amortization_amount,
            ),
        ])

    return header
