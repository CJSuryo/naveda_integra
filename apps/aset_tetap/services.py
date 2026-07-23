"""Aset Tetap services — depreciation calculation and journal generation."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.master_data.models import Akun

from .models import AsetTetapRecord, AssetDisposal, AssetMaintenance, AssetTransfer


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
    kategori = record.item.kategori if record.item else None
    metode = (
        record.metode_penyusutan
        or (record.item.metode_penyusutan if record.item else '')
        or (kategori.metode_penyusutan_default if kategori else '')
    )
    masa = (
        record.masa_manfaat
        or (record.item.masa_manfaat if record.item else 0)
        or (kategori.masa_manfaat_default if kategori else 0)
        or 0
    )
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

def _next_journal_number(prefix: str) -> str:
    """Generate sequential journal number for a given prefix (e.g. 'TRX-DEP-', 'TRX-DSP-')."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith=prefix)
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
    return f'{prefix}{seq:03d}'


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

    if record.status == 'dilepas':
        raise ValueError('Aset sudah dilepas — penyusutan tidak dapat diproses.')

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
        nomor = _next_journal_number('TRX-DEP-')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Penyusutan {record.aset_number} — {record.item.nama}',
            entitas_bisnis=record.entitas_bisnis,
            is_penyesuaian=False,
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


# ---------------------------------------------------------------------------
# Journal Generation for Asset Disposal
# ---------------------------------------------------------------------------

def _resolve_asset_account(record: AsetTetapRecord):
    """Akun aset yang didebit saat perolehan: purchase_item.coa_account -> item.coa_account."""
    if record.purchase_item_id and record.purchase_item and record.purchase_item.coa_account:
        return record.purchase_item.coa_account
    if record.item and record.item.coa_account:
        return record.item.coa_account
    return None


def process_asset_disposal(disposal: AssetDisposal) -> JurnalHeader:
    """Proses pelepasan aset: hitung snapshot, kurangi aset, buat jurnal pelepasan.

    Jurnal:
        Kredit Aset (perolehan dilepas)
        Debit  Akumulasi Penyusutan (akumulasi dilepas)
        Debit  Kas/Piutang (harga jual) -- hanya jenis 'jual' & harga_jual > 0
        Laba (kredit) / Rugi (debit) pada akun_laba_rugi -- selisih
    """
    quantize = Decimal('0.0001')
    aset = disposal.aset
    jenis = disposal.jenis
    quantity = disposal.quantity

    # Normalisasi non-jual
    if jenis != 'jual':
        disposal.harga_jual = Decimal('0')
        disposal.akun_kas = None
    harga_jual = disposal.harga_jual or Decimal('0')

    # Validasi
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas dan tidak dapat dilepas lagi.')
    if quantity is None or quantity <= 0:
        raise ValueError('Quantity pelepasan harus lebih dari 0.')
    if quantity > aset.quantity:
        raise ValueError(
            f'Quantity pelepasan ({quantity}) melebihi sisa quantity aset ({aset.quantity}).'
        )
    if harga_jual < 0:
        raise ValueError('Harga jual tidak boleh negatif.')
    if jenis == 'jual' and harga_jual > 0 and not disposal.akun_kas:
        raise ValueError('Akun Kas/Piutang wajib dipilih untuk pelepasan jenis jual.')
    if not disposal.akun_laba_rugi_id:
        raise ValueError('Akun Laba/Rugi Pelepasan wajib dipilih.')

    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')
    akun_akumulasi = Akun.objects.filter(kode_akun__startswith='1.2.7').first()
    if not akun_akumulasi:
        raise ValueError('Akun Akumulasi Penyusutan (1.2.7.xx) belum tersedia di Chart of Accounts.')

    # Snapshot pro-rata
    fraksi = quantity / aset.quantity
    perolehan_dilepas = (quantity * aset.harga_perolehan).quantize(quantize)
    akumulasi_dilepas = (aset.akumulasi_penyusutan * fraksi).quantize(quantize)
    residu_dilepas = (aset.nilai_residu * fraksi).quantize(quantize)
    nilai_buku_dilepas = perolehan_dilepas - akumulasi_dilepas
    laba_rugi = (harga_jual - nilai_buku_dilepas).quantize(quantize)

    # Baris jurnal: (akun, debit, kredit)
    lines = [
        (akun_aset, Decimal('0'), perolehan_dilepas),        # Kredit aset
        (akun_akumulasi, akumulasi_dilepas, Decimal('0')),   # Debit akumulasi
    ]
    if jenis == 'jual' and harga_jual > 0:
        lines.append((disposal.akun_kas, harga_jual, Decimal('0')))   # Debit kas
    if laba_rugi > 0:
        lines.append((disposal.akun_laba_rugi, Decimal('0'), laba_rugi))   # Kredit laba
    elif laba_rugi < 0:
        lines.append((disposal.akun_laba_rugi, -laba_rugi, Decimal('0')))  # Debit rugi

    total_debit = sum((d for _, d, _ in lines), Decimal('0'))
    total_kredit = sum((k for _, _, k in lines), Decimal('0'))
    if total_debit != total_kredit:
        raise ValueError(
            f'Jurnal pelepasan tidak balance: debit {total_debit} != kredit {total_kredit}.'
        )

    with transaction.atomic():
        disposal.perolehan_dilepas = perolehan_dilepas
        disposal.akumulasi_dilepas = akumulasi_dilepas
        disposal.residu_dilepas = residu_dilepas
        disposal.laba_rugi = laba_rugi

        aset.quantity -= quantity
        aset.akumulasi_penyusutan -= akumulasi_dilepas
        aset.nilai_residu -= residu_dilepas
        if aset.quantity <= 0:
            aset.status = 'dilepas'
        aset.save()

        header = JurnalHeader.objects.create(
            tanggal=disposal.tanggal,
            nomor_transaksi=_next_journal_number('TRX-DSP-'),
            uraian_transaksi=f'Pelepasan {aset.aset_number} ({jenis}) — {aset.item.nama}',
            entitas_bisnis=aset.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
            for akun, d, k in lines
        ])
        disposal.jurnal_header = header
        disposal.save()

    return header


def reverse_asset_disposal(disposal: AssetDisposal, request=None) -> None:
    """Batalkan pelepasan: hapus jurnal (dengan log), pulihkan state aset dari snapshot,
    lalu hapus record disposal. Boleh dilakukan kapan saja (tidak harus yang terakhir).
    """
    from apps.jurnal.utils import log_jurnal_terhapus

    aset = disposal.aset
    with transaction.atomic():
        header = disposal.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()

        aset.quantity += disposal.quantity
        aset.akumulasi_penyusutan += disposal.akumulasi_dilepas
        aset.nilai_residu += disposal.residu_dilepas
        aset.status = 'aktif'
        aset.save()

        disposal.delete()


# ---------------------------------------------------------------------------
# Journal Generation for Asset Maintenance
# ---------------------------------------------------------------------------

def process_asset_maintenance(mtn: AssetMaintenance) -> JurnalHeader:
    """Jurnal: D Beban Pemeliharaan, K Kas/Utang. Update kondisi aset bila diisi."""
    if mtn.biaya is None or mtn.biaya <= 0:
        raise ValueError('Biaya maintenance harus lebih dari 0.')
    aset = mtn.aset
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas — maintenance tidak dapat diproses.')

    with transaction.atomic():
        mtn.kondisi_sebelum = aset.kondisi
        if mtn.kondisi_setelah:
            aset.kondisi = mtn.kondisi_setelah
            aset.save()

        header = JurnalHeader.objects.create(
            tanggal=mtn.tanggal,
            nomor_transaksi=_next_journal_number('TRX-MTN-'),
            uraian_transaksi=f'Maintenance {aset.aset_number} ({mtn.get_jenis_display()})',
            entitas_bisnis=aset.entitas_bisnis,
            is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=header, akun=mtn.akun_beban, debit=mtn.biaya, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=header, akun=mtn.akun_kas_utang, debit=Decimal('0'), kredit=mtn.biaya),
        ])
        mtn.jurnal_header = header
        mtn.save()
    return header


def reverse_asset_maintenance(mtn: AssetMaintenance, request=None) -> None:
    """Batalkan maintenance: hapus jurnal, pulihkan kondisi aset, hapus record."""
    from apps.jurnal.utils import log_jurnal_terhapus
    aset = mtn.aset
    with transaction.atomic():
        header = mtn.jurnal_header
        if header:
            log_jurnal_terhapus(header, 'aset_tetap', request)
            header.details.all().delete()
            header.delete()
        if mtn.kondisi_sebelum:
            aset.kondisi = mtn.kondisi_sebelum
            aset.save()
        mtn.delete()


# ---------------------------------------------------------------------------
# Journal Generation for Asset Transfer (intra-EB & antar-EB)
# ---------------------------------------------------------------------------

def process_asset_transfer(trf: 'AssetTransfer') -> 'JurnalHeader | None':
    """Intra-EB: update lokasi/dept/PIC (tanpa jurnal).
    Antar-EB: dua jurnal seimbang (EB asal & tujuan) via akun antar-entitas, carry-over HP & akumulasi.
    """
    aset = trf.aset
    if aset.status != 'aktif':
        raise ValueError('Aset sudah dilepas — transfer tidak dapat diproses.')

    # Snapshot asal
    trf.lokasi_asal = aset.lokasi_aset
    trf.dept_asal = aset.departemen
    trf.pic_lama = aset.pic

    if trf.jenis == 'intra_eb':
        with transaction.atomic():
            if trf.lokasi_tujuan_id:
                aset.lokasi_aset = trf.lokasi_tujuan
            if trf.dept_tujuan_id:
                aset.departemen = trf.dept_tujuan
            if trf.pic_baru:
                aset.pic = trf.pic_baru
            aset.save()
            trf.save()
        return None

    # antar_eb — divalidasi & dijurnal di fungsi terpisah
    return _process_transfer_antar_eb(trf)


def _process_transfer_antar_eb(trf: 'AssetTransfer') -> JurnalHeader:
    aset = trf.aset
    if not trf.eb_tujuan_id or trf.eb_tujuan_id == aset.entitas_bisnis_id:
        raise ValueError('EB tujuan harus berbeda dari EB asal.')
    if not trf.akun_antar_entitas_id:
        raise ValueError('Akun Antar-Entitas wajib dipilih untuk transfer antar entitas.')
    if not trf.akun_akumulasi_id:
        raise ValueError('Akun Akumulasi Penyusutan wajib dipilih.')
    akun_aset = _resolve_asset_account(aset)
    if not akun_aset:
        raise ValueError('Akun Aset tidak dapat ditentukan (coa_account item/purchase kosong).')

    hp = aset.total_value
    akum = aset.akumulasi_penyusutan
    nilai_buku = hp - akum
    eb_asal = aset.entitas_bisnis

    with transaction.atomic():
        trf.eb_asal = eb_asal
        trf.perolehan = hp
        trf.akumulasi = akum

        # Jurnal EB asal: K Aset (HP), D Akumulasi (akum), D antar-entitas (nilai buku)
        h_asal = JurnalHeader.objects.create(
            tanggal=trf.tanggal, nomor_transaksi=_next_journal_number('TRX-TRF-'),
            uraian_transaksi=f'Transfer keluar {aset.aset_number} ke {trf.eb_tujuan.nama}',
            entitas_bisnis=eb_asal, is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=h_asal, akun=akun_aset, debit=Decimal('0'), kredit=hp),
            JurnalDetail(jurnal_header=h_asal, akun=trf.akun_akumulasi, debit=akum, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=h_asal, akun=trf.akun_antar_entitas, debit=nilai_buku, kredit=Decimal('0')),
        ])

        # Jurnal EB tujuan: D Aset (HP), K Akumulasi (akum), K antar-entitas (nilai buku)
        h_tujuan = JurnalHeader.objects.create(
            tanggal=trf.tanggal, nomor_transaksi=_next_journal_number('TRX-TRF-'),
            uraian_transaksi=f'Transfer masuk {aset.aset_number} dari {eb_asal.nama}',
            entitas_bisnis=trf.eb_tujuan, is_penyesuaian=False,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=h_tujuan, akun=akun_aset, debit=hp, kredit=Decimal('0')),
            JurnalDetail(jurnal_header=h_tujuan, akun=trf.akun_akumulasi, debit=Decimal('0'), kredit=akum),
            JurnalDetail(jurnal_header=h_tujuan, akun=trf.akun_antar_entitas, debit=Decimal('0'), kredit=nilai_buku),
        ])

        # Pindahkan aset ke EB tujuan + lokasi/dept/PIC bila diisi
        aset.entitas_bisnis = trf.eb_tujuan
        if trf.lokasi_tujuan_id:
            aset.lokasi_aset = trf.lokasi_tujuan
        if trf.dept_tujuan_id:
            aset.departemen = trf.dept_tujuan
        if trf.pic_baru:
            aset.pic = trf.pic_baru
        aset.save()

        trf.jurnal_header_asal = h_asal
        trf.jurnal_header_tujuan = h_tujuan
        trf.save()
    return h_asal


def reverse_asset_transfer(trf: 'AssetTransfer', request=None) -> None:
    """Batalkan transfer. Antar-EB: hapus kedua jurnal & pulihkan EB/lokasi/dept/PIC. Intra-EB: pulihkan lokasi/dept/PIC."""
    from apps.jurnal.utils import log_jurnal_terhapus
    aset = trf.aset
    with transaction.atomic():
        for header in (trf.jurnal_header_asal, trf.jurnal_header_tujuan):
            if header:
                log_jurnal_terhapus(header, 'aset_tetap', request)
                header.details.all().delete()
                header.delete()
        if trf.jenis == 'antar_eb' and trf.eb_asal_id:
            aset.entitas_bisnis = trf.eb_asal
        aset.lokasi_aset = trf.lokasi_asal
        aset.departemen = trf.dept_asal
        aset.pic = trf.pic_lama
        aset.save()
        trf.delete()
