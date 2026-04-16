"""Inventory views — CRUD for InventoryRecord."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import InventoryRecordForm
from .models import InventoryRecord

BULK_TO_SATUAN_MAP = {'RMB': 'RM', 'FGB': 'FG', 'ITMB': 'ITM'}


@login_required
def inventory_list(request: HttpRequest) -> HttpResponse:
    """List all inventory records with optional filters, split by Satuan and Bulk tabs."""
    qs = InventoryRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')
    tab = request.GET.get('tab', 'satuan')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)

    BULK_TYPES = ('RMB', 'FGB', 'ITMB')
    SATUAN_TYPES = ('RM', 'FG', 'ITM')

    records_satuan = qs.filter(item__tipe_item__in=SATUAN_TYPES)
    records_bulk = qs.filter(item__tipe_item__in=BULK_TYPES)

    from apps.purchase.models import ItemMasterPurchase
    from apps.entitas_bisnis.models import EntitasBisnis

    return render(request, 'inventory/inventory_list.html', {
        'records_satuan': records_satuan,
        'records_bulk': records_bulk,
        'items': ItemMasterPurchase.objects.filter(
            tipe_item__in=list(SATUAN_TYPES) + list(BULK_TYPES),
        ).order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
        'active_tab': tab,
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

    context = {
        'record': record,
        'mutations': mutations,
    }

    # For bulk items, provide satuan items for conversion modal
    if record.item.tipe_item in BULK_TO_SATUAN_MAP:
        from apps.purchase.models import ItemMasterPurchase
        satuan_tipe = BULK_TO_SATUAN_MAP[record.item.tipe_item]
        context['satuan_items'] = ItemMasterPurchase.objects.filter(
            tipe_item=satuan_tipe,
        ).order_by('item_id')
        context['is_bulk'] = True

    return render(request, 'inventory/inventory_detail.html', context)


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


@login_required
def convert_bulk_to_satuan(request: HttpRequest, pk: int) -> HttpResponse:
    """Convert a bulk inventory record to satuan inventory records.

    Deducts value from the bulk record and creates a new satuan InventoryRecord
    with the specified quantity and unit price. Also creates corresponding
    satuan FIFO batch.
    """
    from decimal import Decimal
    from apps.purchase.models import ItemMasterPurchase, FIFOBatch

    record = get_object_or_404(
        InventoryRecord.objects.select_related('item', 'entitas_bisnis'),
        pk=pk,
    )

    if record.item.tipe_item not in BULK_TO_SATUAN_MAP:
        messages.error(request, 'Record ini bukan tipe bulk.')
        return redirect('inventory:detail', pk=pk)

    if request.method != 'POST':
        return redirect('inventory:detail', pk=pk)

    satuan_tipe = BULK_TO_SATUAN_MAP[record.item.tipe_item]

    # Get or validate the target satuan item
    satuan_item_id = request.POST.get('satuan_item_id', '')
    quantity = request.POST.get('quantity', '')
    unit_price = request.POST.get('unit_price', '')

    # Validation
    errors = []
    if not satuan_item_id:
        errors.append('Item satuan wajib dipilih.')
    if not quantity:
        errors.append('Jumlah wajib diisi.')
    if not unit_price:
        errors.append('Harga satuan wajib diisi.')

    if errors:
        messages.error(request, ' '.join(errors))
        return redirect('inventory:detail', pk=pk)

    try:
        qty = Decimal(quantity)
        price = Decimal(unit_price)
    except Exception:
        messages.error(request, 'Jumlah dan harga harus berupa angka.')
        return redirect('inventory:detail', pk=pk)

    if qty <= 0 or price <= 0:
        messages.error(request, 'Jumlah dan harga harus lebih dari 0.')
        return redirect('inventory:detail', pk=pk)

    total_deduction = qty * price

    if total_deduction > record.total_value:
        messages.error(
            request,
            f'Nilai konversi ({total_deduction:,.0f}) melebihi sisa nilai bulk ({record.total_value:,.0f}).',
        )
        return redirect('inventory:detail', pk=pk)

    # Validate satuan item exists and has correct type
    try:
        satuan_item = ItemMasterPurchase.objects.get(pk=satuan_item_id, tipe_item=satuan_tipe)
    except ItemMasterPurchase.DoesNotExist:
        messages.error(request, f'Item satuan tipe {satuan_tipe} tidak ditemukan.')
        return redirect('inventory:detail', pk=pk)

    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        # Deduct from bulk record
        record.total_value -= total_deduction
        record.unit_price = record.total_value  # bulk: unit_price tracks total value
        record.save()

        # Also deduct from bulk FIFO batch
        bulk_batches = (
            FIFOBatch.objects
            .filter(item=record.item, remaining_qty__gt=0)
            .order_by('tanggal', 'created_at')
            .select_for_update()
        )
        remaining_deduct = total_deduction
        for batch in bulk_batches:
            if remaining_deduct <= 0:
                break
            batch_value = batch.remaining_qty * batch.unit_price
            deduct = min(batch_value, remaining_deduct)
            if deduct > 0 and batch.unit_price:
                batch.remaining_qty = (batch_value - deduct) / batch.unit_price
                batch.save()
                remaining_deduct -= deduct

        # Create satuan InventoryRecord
        new_record = InventoryRecord(
            item=satuan_item,
            entitas_bisnis=record.entitas_bisnis,
            quantity=qty,
            unit_price=price,
            tanggal=record.tanggal,
            metode_alokasi=record.metode_alokasi,
        )
        new_record.save()

        # Create satuan FIFO batch
        FIFOBatch.objects.create(
            item=satuan_item,
            entitas_bisnis=record.entitas_bisnis,
            tanggal=record.tanggal,
            quantity_in=qty,
            remaining_qty=qty,
            unit_price=price,
        )

    messages.success(
        request,
        f'Berhasil konversi {qty:,.0f} unit {satuan_item.nama} '
        f'(Rp {total_deduction:,.0f}) dari {record.inventory_number}.',
    )
    return redirect('inventory:detail', pk=pk)
