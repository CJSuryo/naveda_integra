"""Manufacturing views — BOM and Production Order management."""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.purchase.models import ItemMasterPurchase

from .forms import BOMForm, ProductionOrderForm, parse_bom_lines
from .models import BillOfMaterials, BOMLine, ProductionOrder
from .services import (
    approve_production,
    compute_estimated_cost,
    get_available_stock,
    get_bom_preview,
    get_fifo_unit_cost,
    process_production,
    reverse_production,
    validate_production,
)


# ---------------------------------------------------------------------------
# BOM views
# ---------------------------------------------------------------------------

@login_required
def bom_list(request):
    boms = (
        BillOfMaterials.objects
        .select_related('finished_good', 'entitas_bisnis')
        .prefetch_related('lines__raw_material')
        .order_by('-tanggal_dibuat', '-created_at')
    )
    return render(request, 'manufacturing/bom_list.html', {'bom_list': boms})


@login_required
def bom_create(request):
    rm_items = (
        ItemMasterPurchase.objects
        .filter(tipe_item__in=['RM', 'RMB'])
        .order_by('nama')
        .values('id', 'item_id', 'nama')
    )
    # Build stock/cost data as JSON for the JS
    rm_data = {}
    for item in rm_items:
        rm_data[str(item['id'])] = {
            'item_id': item['item_id'],
            'nama': item['nama'],
            'stock': str(get_available_stock(item['id'])),
            'fifo_cost': str(get_fifo_unit_cost(item['id'])),
        }

    if request.method == 'POST':
        form = BOMForm(request.POST)
        lines_data, line_errors = parse_bom_lines(request.POST)
        if form.is_valid() and not line_errors:
            with transaction.atomic():
                bom = form.save()
                for line in lines_data:
                    BOMLine.objects.create(bom=bom, **line)
            messages.success(request, f'BOM {bom.bom_id} berhasil dibuat.')
            return redirect('manufacturing:bom_detail', pk=bom.pk)
        # Re-render with errors
        if line_errors:
            for err in line_errors:
                messages.error(request, err)
    else:
        form = BOMForm()

    return render(request, 'manufacturing/bom_form.html', {
        'form': form,
        'rm_data_json': json.dumps(rm_data),
        'is_create': True,
    })


@login_required
def bom_detail(request, pk):
    bom = get_object_or_404(
        BillOfMaterials.objects.select_related('finished_good', 'entitas_bisnis')
        .prefetch_related('lines__raw_material'),
        pk=pk,
    )
    # Annotate each line with current stock + FIFO cost
    lines_preview = []
    for line in bom.lines.select_related('raw_material').all():
        fifo_cost = get_fifo_unit_cost(line.raw_material_id)
        available = get_available_stock(line.raw_material_id)
        lines_preview.append({
            'line': line,
            'fifo_unit_cost': fifo_cost,
            'total_rm_cost': line.qty_required * fifo_cost,
            'available_stock': available,
        })

    production_orders = (
        bom.production_orders
        .select_related('entitas_bisnis')
        .order_by('-tanggal')
    )

    return render(request, 'manufacturing/bom_detail.html', {
        'bom': bom,
        'lines_preview': lines_preview,
        'production_orders': production_orders,
    })


@login_required
def bom_update(request, pk):
    bom = get_object_or_404(BillOfMaterials, pk=pk)
    existing_lines = bom.lines.select_related('raw_material').order_by('id')

    rm_items = (
        ItemMasterPurchase.objects
        .filter(tipe_item__in=['RM', 'RMB'])
        .order_by('nama')
        .values('id', 'item_id', 'nama')
    )
    rm_data = {}
    for item in rm_items:
        rm_data[str(item['id'])] = {
            'item_id': item['item_id'],
            'nama': item['nama'],
            'stock': str(get_available_stock(item['id'])),
            'fifo_cost': str(get_fifo_unit_cost(item['id'])),
        }

    if request.method == 'POST':
        form = BOMForm(request.POST, instance=bom)
        lines_data, line_errors = parse_bom_lines(request.POST)
        if form.is_valid() and not line_errors:
            with transaction.atomic():
                form.save()
                bom.lines.all().delete()
                for line in lines_data:
                    BOMLine.objects.create(bom=bom, **line)
            messages.success(request, f'BOM {bom.bom_id} berhasil diperbarui.')
            return redirect('manufacturing:bom_detail', pk=bom.pk)
        if line_errors:
            for err in line_errors:
                messages.error(request, err)
    else:
        form = BOMForm(instance=bom)

    return render(request, 'manufacturing/bom_form.html', {
        'form': form,
        'bom': bom,
        'existing_lines': existing_lines,
        'rm_data_json': json.dumps(rm_data),
        'is_create': False,
    })


@login_required
def bom_delete(request, pk):
    bom = get_object_or_404(BillOfMaterials, pk=pk)
    if request.method == 'POST':
        bom_id_str = bom.bom_id
        bom.delete()
        messages.success(request, f'BOM {bom_id_str} berhasil dihapus.')
        return redirect('manufacturing:bom_list')
    return render(request, 'manufacturing/bom_confirm_delete.html', {'object': bom})


# ---------------------------------------------------------------------------
# Production Order views
# ---------------------------------------------------------------------------

@login_required
def production_list(request):
    orders = (
        ProductionOrder.objects
        .select_related('bom__finished_good', 'entitas_bisnis')
        .order_by('-tanggal', '-created_at')
    )

    # Filters
    status_filter = request.GET.get('status', '')
    eb_filter = request.GET.get('eb', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    if eb_filter:
        orders = orders.filter(entitas_bisnis_id=eb_filter)

    from apps.entitas_bisnis.models import EntitasBisnis
    eb_list = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')

    return render(request, 'manufacturing/production_list.html', {
        'orders': orders,
        'status_filter': status_filter,
        'eb_filter': eb_filter,
        'eb_list': eb_list,
        'status_choices': ProductionOrder.STATUS_CHOICES,
    })


@login_required
def production_create(request):
    if request.method == 'POST':
        form = ProductionOrderForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.save()
                as_wip = (order.status == 'in_progress')
                try:
                    process_production(order, as_wip=as_wip)
                    if as_wip:
                        messages.success(
                            request,
                            f'Production order {order.production_id} disimpan sebagai Work In Progress.',
                        )
                    else:
                        messages.success(
                            request,
                            f'Production order {order.production_id} berhasil diproses dan diselesaikan.',
                        )
                    return redirect('manufacturing:production_detail', pk=order.pk)
                except ValueError as exc:
                    order.delete()
                    messages.error(request, str(exc))
    else:
        form = ProductionOrderForm()

    boms = (
        BillOfMaterials.objects
        .select_related('finished_good', 'entitas_bisnis')
        .prefetch_related('lines')
        .order_by('bom_id')
    )

    return render(request, 'manufacturing/production_create.html', {
        'form': form,
        'boms': boms,
    })


@login_required
def production_detail(request, pk):
    order = get_object_or_404(
        ProductionOrder.objects
        .select_related(
            'bom__finished_good', 'entitas_bisnis',
            'coa_produksi', 'coa_overhead',
        )
        .prefetch_related(
            'rm_consumptions__bom_line__raw_material',
            'rm_consumptions__fifo_batch',
        ),
        pk=pk,
    )
    return render(request, 'manufacturing/production_detail.html', {'order': order})


@login_required
def production_delete(request, pk):
    order = get_object_or_404(ProductionOrder, pk=pk)
    if order.is_processed:
        messages.error(
            request,
            'Production order yang sudah diproses tidak dapat dihapus langsung. '
            'Gunakan fitur Reverse terlebih dahulu.',
        )
        return redirect('manufacturing:production_detail', pk=pk)

    if request.method == 'POST':
        prod_id = order.production_id
        order.delete()
        messages.success(request, f'Production order {prod_id} berhasil dihapus.')
        return redirect('manufacturing:production_list')

    return render(request, 'manufacturing/production_confirm_delete.html', {'object': order})


@login_required
def production_reverse(request, pk):
    """Reverse a completed production order (restore stocks, delete journals)."""
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST':
        try:
            reverse_production(order)
            messages.success(
                request,
                f'Production order {order.production_id} berhasil di-reverse.',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('manufacturing:production_detail', pk=pk)

    return render(request, 'manufacturing/production_reverse_confirm.html', {'object': order})


@login_required
def production_approve(request, pk):
    """Approve (complete) a WIP production order: create FG stock + completion journal."""
    order = get_object_or_404(ProductionOrder, pk=pk)
    if request.method == 'POST':
        try:
            approve_production(order)
            messages.success(
                request,
                f'Production order {order.production_id} berhasil diselesaikan.',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('manufacturing:production_detail', pk=pk)

    return render(request, 'manufacturing/production_approve_confirm.html', {'object': order})


# ---------------------------------------------------------------------------
# AJAX API endpoints
# ---------------------------------------------------------------------------

@login_required
def api_bom_preview(request):
    """AJAX: compute cost & stock preview for a BOM + qty combination.

    GET params: bom_id, qty_produced, overhead_cost
    Returns JSON with per-RM line data and estimated costs.
    """
    bom_id = request.GET.get('bom_id')
    qty_str = request.GET.get('qty_produced', '0')
    overhead_str = request.GET.get('overhead_cost', '0')

    if not bom_id:
        return JsonResponse({'error': 'bom_id wajib diisi.'}, status=400)

    try:
        bom = BillOfMaterials.objects.select_related('finished_good').get(pk=bom_id)
    except BillOfMaterials.DoesNotExist:
        return JsonResponse({'error': 'BOM tidak ditemukan.'}, status=404)

    try:
        qty = Decimal(qty_str)
        if qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'qty_produced tidak valid.'}, status=400)

    try:
        overhead = Decimal(overhead_str)
        if overhead < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        overhead = Decimal('0')

    result = compute_estimated_cost(bom, qty, overhead)

    lines_json = []
    for row in result['preview']:
        lines_json.append({
            'rm_item_id': row['rm_item'].item_id,
            'rm_nama': row['rm_item'].nama,
            'satuan': '',
            'qty_required_per_unit': str(row['qty_required_per_unit']),
            'qty_required_total': str(row['qty_required_total']),
            'fifo_unit_cost': str(row['fifo_unit_cost']),
            'total_rm_cost': str(row['total_rm_cost']),
            'available_stock': str(row['available_stock']),
            'shortage': str(row['shortage']),
            'is_sufficient': row['is_sufficient'],
        })

    return JsonResponse({
        'lines': lines_json,
        'rm_cost': str(result['rm_cost']),
        'total_cost': str(result['total_cost']),
        'unit_cost': str(result['unit_cost']),
        'all_sufficient': result['all_sufficient'],
    })
