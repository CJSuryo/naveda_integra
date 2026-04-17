"""Aset Tetap services — depreciation calculation and journal generation."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.master_data.models import Akun

from .models import AsetTetapRecord


# ---------------------------------------------------------------------------
# Depreciation Calculation Engine — 5 methods (daily basis, 1 year = 365 days)
# ---------------------------------------------------------------------------

def calc_straight_line(total_value: Decimal, nilai_residu: Decimal, masa_manfaat: int) -> Decimal:
    """Garis Lurus: (HP - NR) / (UmurTahun × 365) — returns daily rate."""
    total_hari = masa_manfaat * 365
    if total_hari <= 0:
        return Decimal('0')
    return (total_value - nilai_residu) / Decimal(total_hari)


def calc_double_declining(total_value: Decimal, nilai_residu: Decimal,
                          masa_manfaat: int, akumulasi: Decimal) -> Decimal:
    """Saldo Menurun Ganda: (nilai_buku × 2/umur) / 365 — returns daily rate for current year.

    Validates that nilai buku does not fall below nilai residu.
    """
    if masa_manfaat <= 0:
        return Decimal('0')
    nilai_buku = total_value - akumulasi
    if nilai_buku <= nilai_residu:
        return Decimal('0')
    tarif_tahunan = Decimal('2') / Decimal(masa_manfaat)
    beban_tahunan = nilai_buku * tarif_tahunan
    daily = beban_tahunan / Decimal('365')
    # Validate: nilai buku after 1 day must not go below nilai residu
    if (nilai_buku - daily) < nilai_residu:
        daily = nilai_buku - nilai_residu
    return max(daily, Decimal('0'))


def calc_sum_of_years(total_value: Decimal, nilai_residu: Decimal,
                      masa_manfaat: int, tahun_ke: int) -> Decimal:
    """Jumlah Angka Tahun: (sisa_umur/JAT × (HP-NR)) / 365 — returns daily rate for given year."""
    if masa_manfaat <= 0 or tahun_ke > masa_manfaat:
        return Decimal('0')
    jat = Decimal(masa_manfaat * (masa_manfaat + 1)) / Decimal('2')
    sisa_umur = Decimal(masa_manfaat - tahun_ke + 1)
    beban_tahunan = (sisa_umur / jat) * (total_value - nilai_residu)
    return beban_tahunan / Decimal('365')


def calc_service_hours(total_value: Decimal, nilai_residu: Decimal,
                       estimasi_jam: Decimal, jam_aktual: Decimal) -> Decimal:
    """Satuan Jam Kerja: tarif_per_jam × jam_terpakai — returns amount for given hours."""
    if not estimasi_jam or estimasi_jam <= 0:
        return Decimal('0')
    tarif_per_jam = (total_value - nilai_residu) / estimasi_jam
    return tarif_per_jam * jam_aktual


def calc_units_of_production(total_value: Decimal, nilai_residu: Decimal,
                             estimasi_unit: Decimal, unit_aktual: Decimal) -> Decimal:
    """Satuan Hasil Produksi: tarif_per_unit × unit_diproduksi — returns amount for given units."""
    if not estimasi_unit or estimasi_unit <= 0:
        return Decimal('0')
    tarif_per_unit = (total_value - nilai_residu) / estimasi_unit
    return tarif_per_unit * unit_aktual


def calculate_depreciation(record: AsetTetapRecord, tahun_ke: int = 1,
                           jam_aktual: Decimal = Decimal('0'),
                           unit_aktual: Decimal = Decimal('0'),
                           days: int = 30) -> Decimal:
    """Calculate depreciation for a given record and period.

    For time-based methods (straight_line, double_declining, sum_of_years),
    returns the daily rate multiplied by ``days`` (default 30 for monthly processing).

    For activity-based methods (service_hours, units_of_production),
    ``days`` is ignored; the amount depends purely on actual usage.

    Args:
        record: The AsetTetapRecord to depreciate.
        tahun_ke: Year number (1-based) for sum_of_years and double_declining.
        jam_aktual: Actual hours used this period (for service_hours method).
        unit_aktual: Actual units produced this period (for units_of_production method).
        days: Number of days in the period (default 30 ≈ monthly).

    Returns:
        Depreciation amount for this period.
    """
    metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
    masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
    residu = record.nilai_residu

    if metode == 'straight_line':
        return calc_straight_line(record.total_value, residu, masa) * Decimal(days)
    elif metode == 'double_declining':
        return calc_double_declining(record.total_value, residu, masa, record.akumulasi_penyusutan) * Decimal(days)
    elif metode == 'sum_of_years':
        return calc_sum_of_years(record.total_value, residu, masa, tahun_ke) * Decimal(days)
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
