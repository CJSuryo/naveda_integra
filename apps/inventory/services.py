"""Inventory transaction services Fase 6 — movement + jurnal balance-checked."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from . import ledger
from .models import StockAdjustment, StockOpname, StockTransfer, ReturCustomer


def _next_nomor_jurnal(prefix: str) -> str:
    last = (JurnalHeader.objects.filter(nomor_transaksi__startswith=prefix)
            .order_by('-nomor_transaksi').values_list('nomor_transaksi', flat=True).first())
    try:
        seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
    except (ValueError, IndexError):
        seq = 1
    return f'{prefix}{seq:03d}'


def _post_journal(tanggal, prefix, uraian, entitas_bisnis, lines):
    """lines = [(akun, debit, kredit), ...]. Balance-checked, satu JurnalHeader."""
    total_d = sum((d for _, d, _ in lines), Decimal('0'))
    total_k = sum((k for _, _, k in lines), Decimal('0'))
    if total_d != total_k:
        raise ValueError(f'Jurnal tidak balance: debit {total_d} != kredit {total_k}.')
    header = JurnalHeader.objects.create(
        tanggal=tanggal, nomor_transaksi=_next_nomor_jurnal(prefix),
        uraian_transaksi=uraian, entitas_bisnis=entitas_bisnis, is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(jurnal_header=header, akun=akun, debit=d, kredit=k)
        for akun, d, k in lines
    ])
    return header


@transaction.atomic
def process_adjustment(adj: StockAdjustment) -> JurnalHeader:
    """Posting adjustment: tiap item + qty -> inflow, - qty -> consume; satu jurnal."""
    if adj.status == 'posted':
        raise ValueError('Adjustment sudah diposting.')
    items = list(adj.items.select_related('item').all())
    if not items:
        raise ValueError('Adjustment tanpa item.')
    if not adj.akun_selisih_id:
        raise ValueError('Akun selisih wajib dipilih.')

    naik = Decimal('0')   # total nilai persediaan bertambah
    turun = Decimal('0')  # total nilai persediaan berkurang
    for d in items:
        akun_persediaan = d.item.coa_account
        if akun_persediaan is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account (persediaan).')
        if d.qty > 0:
            mv = ledger.record_inflow(
                d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2, adj.entitas_bisnis_lv3,
                d.qty, d.unit_cost, adj.tanggal, 'adjustment_in', source=adj,
                warehouse=adj.warehouse,
            )
            naik += d.qty * d.unit_cost
        elif d.qty < 0:
            result = ledger.consume_stock(
                d.item, adj.entitas_bisnis, adj.entitas_bisnis_lv2, adj.entitas_bisnis_lv3,
                -d.qty, adj.tanggal, 'adjustment_out', source=adj,
                metode=d.item.metode_biaya_persediaan, warehouse=adj.warehouse,
            )
            mv = result.out_movement
            turun += result.total_cost
        else:
            continue
        d.movement = mv
        d.save(update_fields=['movement'])

    lines = []
    akun_persediaan = items[0].item.coa_account  # asumsi 1 akun persediaan per dokumen
    if naik > 0:
        lines.append((akun_persediaan, naik, Decimal('0')))
        lines.append((adj.akun_selisih, Decimal('0'), naik))
    if turun > 0:
        lines.append((adj.akun_selisih, turun, Decimal('0')))
        lines.append((akun_persediaan, Decimal('0'), turun))

    header = _post_journal(adj.tanggal, 'TRX-ADJ-',
                           f'Penyesuaian Stok {adj.nomor}', adj.entitas_bisnis, lines)
    adj.jurnal_header = header
    adj.status = 'posted'
    adj.save(update_fields=['jurnal_header', 'status'])
    return header


def _reverse_journal(header, request=None):
    if header is None:
        return
    from apps.jurnal.utils import log_jurnal_terhapus
    log_jurnal_terhapus(header, 'inventory', request)
    header.details.all().delete()
    header.delete()


@transaction.atomic
def reverse_adjustment(adj: StockAdjustment, request=None) -> None:
    """Batalkan posting: pulihkan layer (inflow) & konsumsi (outflow), hapus jurnal."""
    if adj.status != 'posted':
        raise ValueError('Adjustment belum diposting.')
    # outflow (adjustment_out) → pulihkan layer yang dikonsumsi
    ledger.reverse_movements(adj)
    # inflow (adjustment_in) → hapus layer (ProtectedError bila sudah dikonsumsi)
    ledger.reverse_inflow_movements(adj)
    _reverse_journal(adj.jurnal_header, request)
    adj.items.update(movement=None)
    adj.jurnal_header = None
    adj.status = 'draft'
    adj.save(update_fields=['jurnal_header', 'status'])


@transaction.atomic
def process_opname(opn: StockOpname):
    """Posting selisih opname. Kembalikan JurnalHeader atau None bila semua selisih 0."""
    if opn.status == 'posted':
        raise ValueError('Opname sudah diposting.')
    items = list(opn.items.select_related('item').all())
    naik = Decimal('0')
    turun = Decimal('0')
    akun_persediaan = None
    for d in items:
        if d.selisih == 0:
            continue
        if d.item.coa_account is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        akun_persediaan = d.item.coa_account
        if d.selisih > 0:
            mv = ledger.record_inflow(
                d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2, opn.entitas_bisnis_lv3,
                d.selisih, d.unit_cost, opn.tanggal, 'opname_in', source=opn,
                warehouse=opn.warehouse)
            naik += d.selisih * d.unit_cost
        else:
            result = ledger.consume_stock(
                d.item, opn.entitas_bisnis, opn.entitas_bisnis_lv2, opn.entitas_bisnis_lv3,
                -d.selisih, opn.tanggal, 'opname_out', source=opn,
                metode=d.item.metode_biaya_persediaan, warehouse=opn.warehouse)
            mv = result.out_movement
            turun += result.total_cost
        d.movement = mv
        d.save(update_fields=['movement'])

    header = None
    if naik > 0 or turun > 0:
        lines = []
        if naik > 0:
            lines.append((akun_persediaan, naik, Decimal('0')))
            lines.append((opn.akun_selisih, Decimal('0'), naik))
        if turun > 0:
            lines.append((opn.akun_selisih, turun, Decimal('0')))
            lines.append((akun_persediaan, Decimal('0'), turun))
        header = _post_journal(opn.tanggal, 'TRX-OPN-',
                               f'Opname Stok {opn.nomor}', opn.entitas_bisnis, lines)
        opn.jurnal_header = header
    opn.status = 'posted'
    opn.save(update_fields=['jurnal_header', 'status'])
    return header


@transaction.atomic
def reverse_opname(opn: StockOpname, request=None) -> None:
    if opn.status != 'posted':
        raise ValueError('Opname belum diposting.')
    ledger.reverse_movements(opn)
    ledger.reverse_inflow_movements(opn)
    _reverse_journal(opn.jurnal_header, request)
    opn.items.update(movement=None)
    opn.jurnal_header = None
    opn.status = 'draft'
    opn.save(update_fields=['jurnal_header', 'status'])


@transaction.atomic
def process_transfer(trf: StockTransfer) -> None:
    if trf.status == 'posted':
        raise ValueError('Transfer sudah diposting.')
    if trf.eb_asal_id == trf.eb_tujuan_id and trf.warehouse_asal_id == trf.warehouse_tujuan_id:
        raise ValueError('Transfer asal dan tujuan tidak boleh sama (entitas & gudang identik).')
    if trf.is_cross_entity and not trf.akun_perantara_id:
        raise ValueError('Transfer lintas entitas wajib mengisi Akun Perantara.')
    items = list(trf.items.select_related('item').all())
    if not items:
        raise ValueError('Transfer tanpa item.')

    total_value = Decimal('0')
    akun_persediaan = None
    for d in items:
        if d.item.coa_account is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        akun_persediaan = d.item.coa_account
        result = ledger.consume_stock(
            d.item, trf.eb_asal, trf.eb_asal_lv2, trf.eb_asal_lv3, d.qty,
            trf.tanggal, 'transfer_out', source=trf,
            metode=d.item.metode_biaya_persediaan, warehouse=trf.warehouse_asal)
        unit_cost = (result.total_cost / d.qty) if d.qty else Decimal('0')
        mv_in = ledger.record_inflow(
            d.item, trf.eb_tujuan, trf.eb_tujuan_lv2, trf.eb_tujuan_lv3, d.qty,
            unit_cost, trf.tanggal, 'transfer_in', source=trf,
            warehouse=trf.warehouse_tujuan)
        d.unit_cost = unit_cost
        d.movement_out = result.out_movement
        d.movement_in = mv_in
        d.save(update_fields=['unit_cost', 'movement_out', 'movement_in'])
        total_value += result.total_cost

    if trf.is_cross_entity and total_value > 0:
        trf.jurnal_header_asal = _post_journal(
            trf.tanggal, 'TRX-TRF-', f'Transfer Keluar {trf.nomor}', trf.eb_asal,
            [(trf.akun_perantara, total_value, Decimal('0')),
             (akun_persediaan, Decimal('0'), total_value)])
        trf.jurnal_header_tujuan = _post_journal(
            trf.tanggal, 'TRX-TRF-', f'Transfer Masuk {trf.nomor}', trf.eb_tujuan,
            [(akun_persediaan, total_value, Decimal('0')),
             (trf.akun_perantara, Decimal('0'), total_value)])
    trf.status = 'posted'
    trf.save(update_fields=['jurnal_header_asal', 'jurnal_header_tujuan', 'status'])


@transaction.atomic
def reverse_transfer(trf: StockTransfer, request=None) -> None:
    if trf.status != 'posted':
        raise ValueError('Transfer belum diposting.')
    ledger.reverse_movements(trf)
    ledger.reverse_inflow_movements(trf)
    _reverse_journal(trf.jurnal_header_asal, request)
    _reverse_journal(trf.jurnal_header_tujuan, request)
    trf.items.update(movement_out=None, movement_in=None)
    trf.jurnal_header_asal = None
    trf.jurnal_header_tujuan = None
    trf.status = 'draft'
    trf.save(update_fields=['jurnal_header_asal', 'jurnal_header_tujuan', 'status'])


@transaction.atomic
def process_retur_customer(rtc: ReturCustomer, akun_pendapatan=None,
                           akun_piutang=None, akun_hpp=None) -> JurnalHeader:
    """Retur pelanggan: barang masuk (inflow biaya HPP asli) + balik pendapatan & HPP.

    Bila item punya sales_item asal, akun diambil dari sana (revenue_account,
    payment_account atau sales_eb.payment_account sebagai fallback, offset_coa_account
    untuk HPP). Parameter akun_pendapatan/akun_piutang/akun_hpp hanya dipakai bila
    sales_item kosong (retur berdiri sendiri / unit test).

    Catatan untuk pemanggil (mis. UI/form): keputusan pakai akun sales_item vs.
    override adalah PER ITEM (ReturCustomerItem.sales_item), bukan berdasarkan
    ReturCustomer.sales_header di header. Kedua field tidak otomatis konsisten —
    header bisa punya sales_header terisi sementara sebagian item tidak
    terhubung ke sales_item manapun. UI yang menampilkan field override akun
    harus mengecek sales_item per baris item, bukan hanya sales_header di header.
    """
    if rtc.status == 'posted':
        raise ValueError('Retur sudah diposting.')
    items = list(rtc.items.select_related('item', 'sales_item', 'sales_item__sales_eb').all())
    if not items:
        raise ValueError('Retur tanpa item.')

    total_pendapatan = Decimal('0')
    total_hpp = Decimal('0')
    ap = api = ahpp = None
    akun_persediaan = None
    for d in items:
        akun_persediaan = d.item.coa_account
        if akun_persediaan is None:
            raise ValueError(f'Item {d.item.item_id} belum punya coa_account.')
        # Asumsi 1 set akun pendapatan/piutang/HPP per dokumen — bila item campuran
        # (sebagian punya sales_item, sebagian tidak), item terakhir yang diproses menang.
        si = d.sales_item
        if si is not None:
            ap = si.revenue_account
            api = si.payment_account or si.sales_eb.payment_account
            ahpp = si.offset_coa_account
        else:
            ap = akun_pendapatan
            api = akun_piutang
            ahpp = akun_hpp
        mv = ledger.record_inflow(
            d.item, rtc.entitas_bisnis, rtc.entitas_bisnis_lv2, rtc.entitas_bisnis_lv3,
            d.qty, d.unit_cost, rtc.tanggal, 'return_customer', source=rtc,
            warehouse=rtc.warehouse)
        d.movement = mv
        d.save(update_fields=['movement'])
        total_pendapatan += d.qty * d.harga_jual
        total_hpp += d.qty * d.unit_cost

    if not (ap and api and ahpp):
        raise ValueError('Akun pendapatan/piutang/HPP retur tidak lengkap.')
    lines = [
        (ap, total_pendapatan, Decimal('0')),          # D Pendapatan (balik)
        (api, Decimal('0'), total_pendapatan),         # K Piutang/Kas
        (akun_persediaan, total_hpp, Decimal('0')),    # D Persediaan (balik HPP)
        (ahpp, Decimal('0'), total_hpp),               # K HPP
    ]
    header = _post_journal(rtc.tanggal, 'TRX-RTC-',
                           f'Retur Pelanggan {rtc.nomor}', rtc.entitas_bisnis, lines)
    rtc.jurnal_header = header
    rtc.status = 'posted'
    rtc.save(update_fields=['jurnal_header', 'status'])
    return header


@transaction.atomic
def reverse_retur_customer(rtc: ReturCustomer, request=None) -> None:
    if rtc.status != 'posted':
        raise ValueError('Retur belum diposting.')
    ledger.reverse_inflow_movements(rtc)  # hapus layer return_customer
    _reverse_journal(rtc.jurnal_header, request)
    rtc.items.update(movement=None)
    rtc.jurnal_header = None
    rtc.status = 'draft'
    rtc.save(update_fields=['jurnal_header', 'status'])
