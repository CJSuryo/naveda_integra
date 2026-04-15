"""Inventory views — CRUD for InventoryRecord."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import InventoryRecord


@login_required
def inventory_list(request: HttpRequest) -> HttpResponse:
    """List all inventory records with optional filters."""
    qs = InventoryRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)

    from apps.purchase.models import ItemMasterPurchase
    from apps.entitas_bisnis.models import EntitasBisnis

    return render(request, 'inventory/inventory_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.all().order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
    })


@login_required
def inventory_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show inventory record detail with mutation history."""
    record = get_object_or_404(
        InventoryRecord.objects.select_related(
            'item', 'entitas_bisnis',
            'purchase_item__purchase_eb__purchase_header',
        ),
        pk=pk,
    )

    # Build mutation history for this inventory record
    # Purchase inflow (the purchase that created this record)
    mutations = []
    if record.purchase_item:
        mutations.append({
            'tanggal': record.tanggal,
            'tipe': 'Masuk (Purchase)',
            'referensi': record.purchase_item.purchase_eb.purchase_header.transaction_id,
            'url': None,
            'quantity': record.purchase_item.quantity,
            'keterangan': f'Pembelian via {record.purchase_item.purchase_eb.purchase_header.transaction_id}',
        })

        # Sales outflows — find SalesItems that consumed FIFO batches linked to this purchase item
        from apps.purchase.models import FIFOBatch
        from apps.sales.models import SalesItem

        fifo_batches = FIFOBatch.objects.filter(purchase_item=record.purchase_item)
        original_qty = sum(b.quantity_in for b in fifo_batches)
        consumed_qty = sum(b.quantity_in - b.remaining_qty for b in fifo_batches)

        if consumed_qty > 0:
            # Find sales items that used this item during the same period
            sales_items = (
                SalesItem.objects
                .filter(item=record.item, cogs_amount__gt=0)
                .select_related('sales_eb__sales_header', 'sales_eb__entitas_bisnis')
                .order_by('sales_eb__sales_header__tanggal')
            )
            for si in sales_items:
                mutations.append({
                    'tanggal': si.sales_eb.sales_header.tanggal,
                    'tipe': 'Keluar (Sales)',
                    'referensi': si.sales_eb.sales_header.transaction_id,
                    'url': f'/sales/{si.sales_eb.sales_header_id}/',
                    'quantity': si.quantity,
                    'keterangan': f'Penjualan via {si.sales_eb.sales_header.transaction_id} ({si.sales_eb.entitas_bisnis.nama})',
                })

    return render(request, 'inventory/inventory_detail.html', {
        'record': record,
        'mutations': mutations,
    })
