"""Aset Tetap services — depreciation calculation and journal generation."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.master_data.models import Akun

from .models import AsetTetapRecord


# ---------------------------------------------------------------------------
# Depreciation Calculation Engine — 5 methods
# ---------------------------------------------------------------------------

def calc_straight_line(total_value: Decimal, nilai_residu: Decimal, masa_manfaat: int) -> Decimal:
    """Garis Lurus: (Nilai Perolehan - Nilai Residu) / Masa Manfaat."""
    if masa_manfaat <= 0:
        return Decimal('0')
    return (total_value - nilai_residu) / Decimal(masa_manfaat)


def calc_double_declining(total_value: Decimal, nilai_residu: Decimal,
                          masa_manfaat: int, akumulasi: Decimal) -> Decimal:
    """Saldo Menurun Ganda: (2 / Masa Manfaat) × Nilai Buku."""
    if masa_manfaat <= 0:
        return Decimal('0')
    nilai_buku = total_value - akumulasi
    if nilai_buku <= nilai_residu:
        return Decimal('0')
    rate = Decimal('2') / Decimal(masa_manfaat)
    depreciation = nilai_buku * rate
    # Don't depreciate below salvage value
    if (nilai_buku - depreciation) < nilai_residu:
        depreciation = nilai_buku - nilai_residu
    return max(depreciation, Decimal('0'))


def calc_sum_of_years(total_value: Decimal, nilai_residu: Decimal,
                      masa_manfaat: int, tahun_ke: int) -> Decimal:
    """Jumlah Angka Tahun: (Sisa Tahun / Sum of Years) × (Nilai Perolehan - Residu)."""
    if masa_manfaat <= 0 or tahun_ke > masa_manfaat:
        return Decimal('0')
    sum_years = Decimal(masa_manfaat * (masa_manfaat + 1)) / Decimal('2')
    remaining_years = Decimal(masa_manfaat - tahun_ke + 1)
    return (remaining_years / sum_years) * (total_value - nilai_residu)


def calc_service_hours(total_value: Decimal, nilai_residu: Decimal,
                       estimasi_jam: Decimal, jam_aktual: Decimal) -> Decimal:
    """Satuan Jam Kerja: (Jam Aktual / Estimasi Total Jam) × (Nilai Perolehan - Residu)."""
    if not estimasi_jam or estimasi_jam <= 0:
        return Decimal('0')
    return (jam_aktual / estimasi_jam) * (total_value - nilai_residu)


def calc_units_of_production(total_value: Decimal, nilai_residu: Decimal,
                             estimasi_unit: Decimal, unit_aktual: Decimal) -> Decimal:
    """Satuan Hasil Produksi: (Unit Aktual / Estimasi Total Unit) × (Nilai Perolehan - Residu)."""
    if not estimasi_unit or estimasi_unit <= 0:
        return Decimal('0')
    return (unit_aktual / estimasi_unit) * (total_value - nilai_residu)


def calculate_depreciation(record: AsetTetapRecord, tahun_ke: int = 1,
                           jam_aktual: Decimal = Decimal('0'),
                           unit_aktual: Decimal = Decimal('0')) -> Decimal:
    """Calculate annual depreciation for a given record and period.

    Args:
        record: The AsetTetapRecord to depreciate.
        tahun_ke: Year number (1-based) for sum_of_years method.
        jam_aktual: Actual hours used this period (for service_hours method).
        unit_aktual: Actual units produced this period (for units_of_production method).

    Returns:
        Depreciation amount for this period.
    """
    metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
    masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
    residu = record.nilai_residu

    if metode == 'straight_line':
        return calc_straight_line(record.total_value, residu, masa)
    elif metode == 'double_declining':
        return calc_double_declining(record.total_value, residu, masa, record.akumulasi_penyusutan)
    elif metode == 'sum_of_years':
        return calc_sum_of_years(record.total_value, residu, masa, tahun_ke)
    elif metode == 'service_hours':
        return calc_service_hours(record.total_value, residu,
                                  record.estimasi_jam_kerja or Decimal('0'), jam_aktual)
    elif metode == 'units_of_production':
        return calc_units_of_production(record.total_value, residu,
                                        record.estimasi_unit_produksi or Decimal('0'), unit_aktual)
    return Decimal('0')


# ---------------------------------------------------------------------------
# Journal Generation for Depreciation Processing
# ---------------------------------------------------------------------------

def _next_depreciation_journal_number() -> str:
    """Generate sequential journal number for depreciation journals."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-DEP-')
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
    return f'TRX-DEP-{seq:03d}'


def process_depreciation(record: AsetTetapRecord, depreciation_amount: Decimal,
                         tanggal=None) -> JurnalHeader:
    """Process depreciation for a single AsetTetapRecord.

    Creates a journal entry:
        Debit:  Beban Penyusutan (kode akun 5.1.19.xx)
        Credit: Akumulasi Penyusutan (kode akun 1.2.7.xx)

    Updates akumulasi_penyusutan on the record.

    Args:
        record: The asset record to depreciate.
        depreciation_amount: The calculated depreciation amount.
        tanggal: Date for the journal entry. Defaults to today.

    Returns:
        The created JurnalHeader.
    """
    if tanggal is None:
        tanggal = timezone.now().date()

    if depreciation_amount <= 0:
        raise ValueError('Jumlah penyusutan harus lebih dari 0.')

    nilai_buku = record.total_value - record.akumulasi_penyusutan
    if depreciation_amount > nilai_buku - record.nilai_residu:
        raise ValueError(
            f'Jumlah penyusutan ({depreciation_amount:,.0f}) melebihi '
            f'nilai buku yang dapat disusutkan ({nilai_buku - record.nilai_residu:,.0f}).'
        )

    # Find COA accounts: Beban Penyusutan (5.1.19) and Akumulasi Penyusutan (1.2.7)
    beban_akun = Akun.objects.filter(kode_akun__startswith='5.1.19').first()
    akumulasi_akun = Akun.objects.filter(kode_akun__startswith='1.2.7').first()

    if not beban_akun:
        raise ValueError('Akun Beban Penyusutan (5.1.19.xx) belum tersedia di Chart of Accounts.')
    if not akumulasi_akun:
        raise ValueError('Akun Akumulasi Penyusutan (1.2.7.xx) belum tersedia di Chart of Accounts.')

    with transaction.atomic():
        # Update akumulasi_penyusutan
        record.akumulasi_penyusutan += depreciation_amount
        record.save()

        # Create journal entry
        nomor = _next_depreciation_journal_number()
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyusutan {record.aset_number} — {record.item.nama}',
            entitas_bisnis=record.entitas_bisnis,
            is_penyesuaian=True,
        )

        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun=beban_akun,
                debit=depreciation_amount,
                kredit=Decimal('0'),
            ),
            JurnalDetail(
                jurnal_header=header,
                akun=akumulasi_akun,
                debit=Decimal('0'),
                kredit=depreciation_amount,
            ),
        ])

    return header
