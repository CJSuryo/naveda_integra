"""Laporan inventory — valuasi, HPP, velocity. Read-only, sumber StockMovement.

Semua fungsi murni (tanpa request). Kuantitas & nilai dalam base uom (Decimal).
"""
from collections import defaultdict
from decimal import Decimal

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
