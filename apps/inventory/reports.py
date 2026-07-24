"""Laporan inventory — valuasi, HPP, velocity. Read-only, sumber StockMovement.

Semua fungsi murni (tanpa request). Kuantitas & nilai dalam base uom (Decimal).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from .ledger import OUTFLOW_MOVEMENT_TYPES
from .models import StockConsumption, StockMovement

INVENTORY_TIPE_ITEMS = ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB')


def _kategori_nama(item) -> str:
    return item.kategori.nama if getattr(item, 'kategori', None) else '(Tanpa Kategori)'


def valuation_report(eb_lv1_ids, *, warehouse_id=None, tipe_item=None, as_of=None):
    """Nilai persediaan on-hand dari layer inflow tersisa (remaining_qty > 0).

    eb_lv1_ids: iterable PK EntitasBisnis lv1 yang boleh diakses.
    as_of: bila diisi, hanya layer dengan tanggal <= as_of (aproksimasi untuk
    tanggal lampau; eksak untuk hari ini). Kembalikan dict rows + subtotal.
    """
    eb_ids = list(eb_lv1_ids)
    layers = (
        StockMovement.objects
        .filter(remaining_qty__gt=0, entitas_bisnis_id__in=eb_ids,
                item__tipe_item__in=INVENTORY_TIPE_ITEMS)
        .select_related('item', 'item__kategori', 'item__stock_uom', 'warehouse')
    )
    if warehouse_id:
        layers = layers.filter(warehouse_id=warehouse_id)
    if tipe_item:
        layers = layers.filter(item__tipe_item=tipe_item)
    if as_of:
        layers = layers.filter(tanggal__lte=as_of)

    agg = defaultdict(lambda: {'on_hand_qty': Decimal('0'), 'total_value': Decimal('0')})
    meta = {}
    for lyr in layers:
        key = lyr.item_id
        agg[key]['on_hand_qty'] += lyr.remaining_qty
        agg[key]['total_value'] += lyr.remaining_qty * lyr.unit_cost
        meta[key] = lyr.item

    rows = []
    sub_kat = defaultdict(lambda: Decimal('0'))
    grand = Decimal('0')
    for item_id, vals in agg.items():
        item = meta[item_id]
        qty = vals['on_hand_qty']
        value = vals['total_value']
        unit_cost_avg = (value / qty).quantize(Decimal('0.0001')) if qty else Decimal('0')
        kategori = _kategori_nama(item)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'tipe_item': item.tipe_item,
            'kategori': kategori,
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'on_hand_qty': qty,
            'unit_cost_avg': unit_cost_avg,
            'total_value': value,
        })
        sub_kat[kategori] += value
        grand += value

    rows.sort(key=lambda r: (r['kategori'], r['item_id']))
    return {
        'rows': rows,
        'subtotals_kategori': dict(sub_kat),
        'grand_total_value': grand,
    }


def hpp_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *, warehouse_id=None):
    """HPP (COGS) untuk penjualan pada rentang tanggal, biaya layer-akurat.

    Sumber: gerakan sale_out pada rentang, biaya diambil dari StockConsumption
    (qty*unit_cost per layer). return_customer pada rentang mengurangi qty & HPP.
    """
    eb_ids = list(eb_lv1_ids)
    out_qs = (
        StockMovement.objects
        .filter(movement_type='sale_out', entitas_bisnis_id__in=eb_ids,
                tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)
        .select_related('item', 'item__kategori', 'item__stock_uom')
    )
    if warehouse_id:
        out_qs = out_qs.filter(warehouse_id=warehouse_id)

    agg = defaultdict(lambda: {'qty': Decimal('0'), 'hpp': Decimal('0')})
    meta = {}
    for mv in out_qs:
        # qty pada outflow bertanda negatif; qty terjual = -qty
        agg[mv.item_id]['qty'] += -mv.qty
        hpp = Decimal('0')
        # Jumlahkan biaya per-layer dari StockConsumption, bukan qty*mv.unit_cost:
        # unit_cost pada movement adalah rata-rata FIFO yang sudah dikuantisasi
        # (DecimalField), sehingga qty*unit_cost bisa meleset tipis (mis. 70.0005
        # vs 70.0000) dibanding penjumlahan biaya aktual tiap layer FIFO.
        for alloc in StockConsumption.objects.filter(out_movement=mv):
            hpp += alloc.qty * alloc.unit_cost
        agg[mv.item_id]['hpp'] += hpp
        meta[mv.item_id] = mv.item

    # retur pelanggan mengurangi HPP & qty (pembalik penjualan)
    ret_qs = (
        StockMovement.objects
        .filter(movement_type='return_customer', entitas_bisnis_id__in=eb_ids,
                tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)
        .select_related('item')
    )
    if warehouse_id:
        ret_qs = ret_qs.filter(warehouse_id=warehouse_id)
    for mv in ret_qs:
        if mv.item_id in agg:
            agg[mv.item_id]['qty'] -= mv.qty  # inflow qty positif -> kurangi
            agg[mv.item_id]['hpp'] -= mv.qty * mv.unit_cost

    rows = []
    sub_kat = defaultdict(lambda: Decimal('0'))
    grand = Decimal('0')
    for item_id, vals in agg.items():
        item = meta[item_id]
        kategori = _kategori_nama(item)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'kategori': kategori,
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'qty_terjual': vals['qty'],
            'total_hpp': vals['hpp'],
        })
        sub_kat[kategori] += vals['hpp']
        grand += vals['hpp']

    rows.sort(key=lambda r: (r['kategori'], r['item_id']))
    return {
        'rows': rows,
        'subtotals_kategori': dict(sub_kat),
        'grand_total_hpp': grand,
    }


def velocity_report(eb_lv1_ids, tanggal_dari, tanggal_sampai, *,
                    warehouse_id=None, velocity_filter=None):
    """Slow/Fast moving: tag manual velocity_category + metrik aktual per item.

    Untuk tiap item persediaan dalam scope EB: total qty keluar & jumlah gerakan
    pada rentang, hari sejak keluar terakhir, on-hand saat ini. mismatch_flag
    True bila tag 'fast'/'medium' tapi tak ada gerakan keluar pada rentang, atau
    tag 'dead' tapi ADA gerakan.
    """
    from datetime import date as _date
    eb_ids = list(eb_lv1_ids)

    base = StockMovement.objects.filter(
        entitas_bisnis_id__in=eb_ids, item__tipe_item__in=INVENTORY_TIPE_ITEMS)
    if warehouse_id:
        base = base.filter(warehouse_id=warehouse_id)

    # item-item yang punya gerakan apa pun dalam scope
    items = {}
    for mv in base.select_related('item', 'item__kategori', 'item__stock_uom'):
        items[mv.item_id] = mv.item

    outflow = base.filter(
        movement_type__in=OUTFLOW_MOVEMENT_TYPES,
        tanggal__gte=tanggal_dari, tanggal__lte=tanggal_sampai)

    qty_keluar = defaultdict(lambda: Decimal('0'))
    jumlah = defaultdict(int)
    last_out = {}
    for mv in outflow:
        qty_keluar[mv.item_id] += -mv.qty
        jumlah[mv.item_id] += 1
        if mv.item_id not in last_out or mv.tanggal > last_out[mv.item_id]:
            last_out[mv.item_id] = mv.tanggal

    onhand = defaultdict(lambda: Decimal('0'))
    for r in base.filter(remaining_qty__gt=0).values('item_id').annotate(
            s=Sum('remaining_qty')):
        onhand[r['item_id']] = r['s'] or Decimal('0')

    today = _date.today()
    rows = []
    for item_id, item in items.items():
        vc = item.velocity_category or ''
        if velocity_filter and vc != velocity_filter:
            continue
        qk = qty_keluar[item_id]
        moved = qk > 0
        last = last_out.get(item_id)
        mismatch = (vc in ('fast', 'medium') and not moved) or (vc == 'dead' and moved)
        rows.append({
            'item': item,
            'item_id': item.item_id,
            'nama': item.nama,
            'kategori': _kategori_nama(item),
            'satuan': item.stock_uom.kode if getattr(item, 'stock_uom', None) else '',
            'velocity_category': vc,
            'velocity_label': item.get_velocity_category_display() if vc else '(Belum ditag)',
            'qty_keluar': qk,
            'jumlah_gerakan': jumlah[item_id],
            'hari_sejak_keluar_terakhir': (today - last).days if last else None,
            'on_hand': onhand[item_id],
            'mismatch_flag': mismatch,
        })

    rows.sort(key=lambda r: (-r['qty_keluar'], r['item_id']))
    return rows
