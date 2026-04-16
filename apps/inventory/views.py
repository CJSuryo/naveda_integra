"""Inventory views — CRUD for InventoryRecord."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import InventoryRecordForm
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
    # Purchase or saldo-awal inflow (the transaction that created this record)
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
    else:
        # Saldo awal — compute original quantity from remaining + all consumed allocations
        from decimal import Decimal
        from django.db.models import Sum
        from apps.sales.models import SalesItemFIFOAllocation as _SIFA
        consumed_total = (
            _SIFA.objects
            .filter(inventory_record=record)
            .aggregate(total=Sum('quantity_consumed'))['total'] or Decimal('0')
        )
        original_qty = record.quantity + consumed_total
        mutations.append({
            'tanggal': record.tanggal,
            'tipe': 'Masuk (Saldo Awal)',
            'referensi': f'Saldo Awal {record.tanggal}',
            'url': None,
            'quantity': original_qty,
            'keterangan': 'Saldo awal persediaan',
        })

    # Sales outflows — via SalesItemFIFOAllocation for accurate per-batch quantities
    from apps.sales.models import SalesItemFIFOAllocation
    alloc_qs = (
        SalesItemFIFOAllocation.objects
        .filter(inventory_record=record)
        .select_related(
            'sales_item__sales_eb__sales_header',
            'sales_item__sales_eb__entitas_bisnis',
        )
        .order_by('sales_item__sales_eb__sales_header__tanggal')
    )
    for alloc in alloc_qs:
        sh = alloc.sales_item.sales_eb.sales_header
        mutations.append({
            'tanggal': sh.tanggal,
            'tipe': 'Keluar (Sales)',
            'referensi': sh.transaction_id,
            'url': f'/sales/{sh.pk}/',
            'quantity': alloc.quantity_consumed,
            'keterangan': f'Penjualan via {sh.transaction_id} ({alloc.sales_item.sales_eb.entitas_bisnis.nama})',
        })

    return render(request, 'inventory/inventory_detail.html', {
        'record': record,
        'mutations': mutations,
    })


@login_required
def inventory_create(request: HttpRequest) -> HttpResponse:
    """Manually create a new InventoryRecord (e.g. saldo awal)."""
    if request.method == 'POST':
        form = InventoryRecordForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Inventory record {record.inventory_number} berhasil dibuat.')
            return redirect('inventory:detail', pk=record.pk)
    else:
        form = InventoryRecordForm()
    return render(request, 'inventory/inventory_form.html', {'form': form, 'title': 'Tambah Inventory Record'})


@login_required
def inventory_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing InventoryRecord."""
    record = get_object_or_404(InventoryRecord, pk=pk)
    if request.method == 'POST':
        form = InventoryRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, f'Inventory record {record.inventory_number} berhasil diperbarui.')
            return redirect('inventory:detail', pk=record.pk)
    else:
        form = InventoryRecordForm(instance=record)
    return render(request, 'inventory/inventory_form.html', {
        'form': form,
        'record': record,
        'title': f'Edit {record.inventory_number}',
    })


@login_required
def inventory_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an InventoryRecord."""
    record = get_object_or_404(InventoryRecord, pk=pk)
    if request.method == 'POST':
        number = record.inventory_number
        record.delete()
        messages.success(request, f'Inventory record {number} berhasil dihapus.')
        return redirect('inventory:list')
    return redirect('inventory:list')
