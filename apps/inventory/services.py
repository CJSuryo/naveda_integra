"""Inventory transaction services Fase 6 — movement + jurnal balance-checked."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail

from . import ledger
from .models import StockAdjustment, StockOpname


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
