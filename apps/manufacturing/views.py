"""Manufacturing views — BOM and Production Order management."""
import json
from decimal import Decimal, InvalidOperation

from naveda_integra.json_utils import safe_json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.purchase.models import ItemMasterPurchase
from apps.purchase.views import _get_eb_tree, _resolve_eb_lv1_ids

from .forms import BOMForm, OverheadCategoryForm, OverheadRateForm, ProductionOrderForm, parse_bom_lines
from .models import BillOfMaterials, BOMLine, OverheadApplied, OverheadCategory, OverheadRate, PeriodClosing, ProductionOrder
from .services import (
    approve_production,
    compute_estimated_cost,
    create_overhead_applied,
    get_available_stock,
    get_bom_preview,
    get_fifo_unit_cost,
    get_overhead_rates_for_period,
    get_period_closing_preview,
    period_end_closing,
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
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    if eb_filter_list:
        boms = boms.filter(entitas_bisnis_id__in=_resolve_eb_lv1_ids(eb_filter_list, request.user))
    return render(request, 'manufacturing/bom_list.html', {
        'bom_list': boms,
        'eb_tree': _get_eb_tree(request.user),
        'eb_filter_list': eb_filter_list,
    })


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
        'rm_data_json': safe_json(rm_data),
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
        'rm_data_json': safe_json(rm_data),
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
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    if status_filter:
        orders = orders.filter(status=status_filter)
    if eb_filter_list:
        orders = orders.filter(entitas_bisnis_id__in=_resolve_eb_lv1_ids(eb_filter_list, request.user))

    return render(request, 'manufacturing/production_list.html', {
        'orders': orders,
        'status_filter': status_filter,
        'eb_filter_list': eb_filter_list,
        'eb_tree': _get_eb_tree(request.user),
        'status_choices': ProductionOrder.STATUS_CHOICES,
    })


@login_required
def production_create(request):
    from datetime import date
    today = date.today()
    default_period = today.strftime('%Y-%m')

    if request.method == 'POST':
        form = ProductionOrderForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.save()
                as_wip = (order.status == 'in_progress')

                # Parse overhead driver values from POST
                periode_bulan = order.tanggal.strftime('%Y-%m')
                prod_categories = (
                    OverheadCategory.objects
                    .filter(overhead_type='PRODUCTION', is_active=True)
                )
                overhead_drivers = {}
                rates_map = get_overhead_rates_for_period(periode_bulan)
                rm_cost_estimate = Decimal(request.POST.get('_rm_cost_estimate', '0') or '0')

                if rm_cost_estimate == 0 and order.bom and order.qty_produced > 0:
                    # Fallback when the browser preview did not populate RM cost.
                    rm_preview = compute_estimated_cost(order.bom, order.qty_produced, Decimal('0'))
                    rm_cost_estimate = rm_preview['rm_cost']

                for cat in prod_categories:
                    rate = rates_map.get(cat.pk)
                    if not rate or rate.rate_per_driver == 0:
                        continue
                    driver = cat.cost_driver
                    if driver == 'PER_UNIT':
                        overhead_drivers[cat.pk] = order.qty_produced
                    elif driver == 'PERSEN_RM_COST':
                        overhead_drivers[cat.pk] = rm_cost_estimate
                    else:
                        raw = request.POST.get(f'overhead_driver_{cat.pk}', '').strip()
                        try:
                            val = Decimal(raw)
                            if val > 0:
                                overhead_drivers[cat.pk] = val
                        except (InvalidOperation, ValueError):
                            pass

                try:
                    if overhead_drivers:
                        create_overhead_applied(order, overhead_drivers, periode_bulan)
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

    # Active PRODUCTION overhead categories + their current period rates
    prod_categories = (
        OverheadCategory.objects
        .filter(overhead_type='PRODUCTION', is_active=True)
        .select_related('coa_expense')
        .order_by('name')
    )
    rates_map = get_overhead_rates_for_period(default_period)
    overhead_cats_ctx = []
    for cat in prod_categories:
        rate = rates_map.get(cat.pk)
        overhead_cats_ctx.append({
            'cat': cat,
            'rate': rate,
            'has_rate': rate is not None,
        })

    boms = (
        BillOfMaterials.objects
        .select_related('finished_good', 'entitas_bisnis')
        .prefetch_related('lines')
        .order_by('bom_id')
    )

    return render(request, 'manufacturing/production_create.html', {
        'form': form,
        'boms': boms,
        'overhead_cats': overhead_cats_ctx,
        'default_period': default_period,
    })


@login_required
def production_detail(request, pk):
    order = get_object_or_404(
        ProductionOrder.objects
        .select_related(
            'bom__finished_good', 'entitas_bisnis',
            'coa_produksi',
        )
        .prefetch_related(
            'rm_consumptions__bom_line__raw_material',
            'rm_consumptions__fifo_batch',
            'overhead_applied__overhead_category',
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


@login_required
def api_boms_by_entity(request):
    """AJAX: return BOMs filtered by entitas_bisnis.

    GET param: eb_id
    Returns JSON list of {id, bom_id, finished_good_nama}.
    """
    eb_id = request.GET.get('eb_id')
    if not eb_id:
        return JsonResponse({'boms': []})
    boms = (
        BillOfMaterials.objects
        .filter(entitas_bisnis_id=eb_id)
        .select_related('finished_good')
        .order_by('bom_id')
    )
    data = [
        {'id': b.pk, 'bom_id': b.bom_id, 'finished_good': b.finished_good.nama}
        for b in boms
    ]
    return JsonResponse({'boms': data})


@login_required
def api_overhead_rates(request):
    """AJAX: return active PRODUCTION overhead rates for a given period.

    GET param: periode (YYYY-MM)
    Returns JSON list of categories with their current rate.
    """
    periode = request.GET.get('periode', '')
    if not periode:
        from datetime import date
        periode = date.today().strftime('%Y-%m')

    categories = (
        OverheadCategory.objects
        .filter(overhead_type='PRODUCTION', is_active=True)
        .order_by('name')
    )
    rates_map = get_overhead_rates_for_period(periode)

    result = []
    for cat in categories:
        rate = rates_map.get(cat.pk)
        result.append({
            'id': cat.pk,
            'name': cat.name,
            'cost_driver': cat.cost_driver,
            'rate_per_driver': str(rate.rate_per_driver) if rate else '0',
            'has_rate': rate is not None,
        })
    return JsonResponse({'categories': result, 'periode': periode})


# ---------------------------------------------------------------------------
# Overhead Category CRUD
# ---------------------------------------------------------------------------

@login_required
def overhead_category_list(request):
    categories = OverheadCategory.objects.select_related('coa_expense', 'coa_overhead_applied').order_by('overhead_type', 'name')
    return render(request, 'manufacturing/overhead_category_list.html', {'categories': categories})


@login_required
def overhead_category_create(request):
    if request.method == 'POST':
        form = OverheadCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f'Overhead category "{cat.name}" berhasil dibuat.')
            return redirect('manufacturing:overhead_category_list')
    else:
        form = OverheadCategoryForm()
    return render(request, 'manufacturing/overhead_category_form.html', {'form': form, 'is_create': True})


@login_required
def overhead_category_update(request, pk):
    cat = get_object_or_404(OverheadCategory, pk=pk)
    if request.method == 'POST':
        form = OverheadCategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, f'Overhead category "{cat.name}" berhasil diperbarui.')
            return redirect('manufacturing:overhead_category_list')
    else:
        form = OverheadCategoryForm(instance=cat)
    return render(request, 'manufacturing/overhead_category_form.html', {'form': form, 'object': cat, 'is_create': False})


@login_required
def overhead_category_delete(request, pk):
    cat = get_object_or_404(OverheadCategory, pk=pk)
    if request.method == 'POST':
        try:
            name = cat.name
            cat.delete()
            messages.success(request, f'Overhead category "{name}" berhasil dihapus.')
        except Exception:
            messages.error(request, 'Tidak dapat menghapus kategori yang masih digunakan.')
        return redirect('manufacturing:overhead_category_list')
    return render(request, 'manufacturing/overhead_category_delete.html', {'object': cat})


# ---------------------------------------------------------------------------
# Overhead Rate Setup
# ---------------------------------------------------------------------------

@login_required
def overhead_rate_setup(request):
    """View / edit overhead rates for a chosen period."""
    from datetime import date
    periode = request.GET.get('periode') or date.today().strftime('%Y-%m')

    prod_categories = (
        OverheadCategory.objects
        .filter(overhead_type='PRODUCTION', is_active=True)
        .order_by('name')
    )
    rates_map = {r.overhead_category_id: r for r in OverheadRate.objects.filter(periode_bulan=periode)}

    if request.method == 'POST':
        errors = []
        with transaction.atomic():
            for cat in prod_categories:
                est_total_str = request.POST.get(f'est_total_{cat.pk}', '').strip()
                est_vol_str = request.POST.get(f'est_vol_{cat.pk}', '').strip()
                rate_str = request.POST.get(f'rate_{cat.pk}', '').strip()
                aktuak_str = request.POST.get(f'aktual_{cat.pk}', '').strip()

                if not est_total_str:
                    continue  # skip empty rows
                try:
                    est_total = Decimal(est_total_str)
                except (InvalidOperation, ValueError):
                    errors.append(f'{cat.name}: estimasi total tidak valid.')
                    continue

                est_vol = None
                if est_vol_str:
                    try:
                        est_vol = Decimal(est_vol_str)
                    except (InvalidOperation, ValueError):
                        errors.append(f'{cat.name}: estimasi volume tidak valid.')
                        continue

                aktual = None
                if aktuak_str:
                    try:
                        aktual = Decimal(aktuak_str)
                    except (InvalidOperation, ValueError):
                        pass

                existing = rates_map.get(cat.pk)
                if existing:
                    existing.estimasi_total = est_total
                    existing.estimasi_volume = est_vol
                    if cat.cost_driver == 'PERSEN_RM_COST' and rate_str:
                        try:
                            existing.rate_per_driver = Decimal(rate_str)
                        except (InvalidOperation, ValueError):
                            pass
                    if aktual is not None:
                        existing.aktual_total = aktual
                    existing.save()
                else:
                    rate_obj = OverheadRate(
                        overhead_category=cat,
                        periode_bulan=periode,
                        estimasi_total=est_total,
                        estimasi_volume=est_vol,
                        aktual_total=aktual,
                    )
                    if cat.cost_driver == 'PERSEN_RM_COST' and rate_str:
                        try:
                            rate_obj.rate_per_driver = Decimal(rate_str)
                        except (InvalidOperation, ValueError):
                            pass
                    rate_obj.save()

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            messages.success(request, f'Overhead rates untuk periode {periode} berhasil disimpan.')
        return redirect(f'{request.path}?periode={periode}')

    # Rebuild rates_map after GET
    rates_map = {r.overhead_category_id: r for r in OverheadRate.objects.filter(periode_bulan=periode)}

    year, month = map(int, periode.split('-'))
    prev_year = year if month > 1 else year - 1
    prev_month = month - 1 if month > 1 else 12
    prev_periode = f'{prev_year:04d}-{prev_month:02d}'
    prev_rates_map = {r.overhead_category_id: r for r in OverheadRate.objects.filter(periode_bulan=prev_periode)}

    def safe_div(value, divider):
        if value is None or divider in (None, 0):
            return None
        return value / divider

    rows = []
    for cat in prod_categories:
        rate = rates_map.get(cat.pk)
        prev_rate = prev_rates_map.get(cat.pk)

        est_total = None
        est_vol = None
        rate_value = None
        aktual = None

        if rate:
            est_total = rate.estimasi_total
            est_vol = rate.estimasi_volume
            aktual = rate.aktual_total
            rate_value = rate.rate_per_driver
        elif prev_rate:
            est_total = prev_rate.estimasi_total
            est_vol = prev_rate.estimasi_volume
            aktual = prev_rate.aktual_total
            rate_value = prev_rate.rate_per_driver

        avg_produksi = safe_div(est_total, est_vol)
        avg_aktual = safe_div(aktual, est_vol)

        rows.append({
            'cat': cat,
            'rate': rate,
            'prev_rate': prev_rate,
            'est_total': est_total,
            'est_vol': est_vol,
            'rate_value': rate_value,
            'aktual': aktual,
            'avg_produksi': avg_produksi,
            'avg_aktual': avg_aktual,
            'prev_periode': prev_periode,
        })

    return render(request, 'manufacturing/overhead_rate_setup.html', {
        'rows': rows,
        'periode': periode,
        'prev_periode': prev_periode,
    })


# ---------------------------------------------------------------------------
# Overhead Monitoring
# ---------------------------------------------------------------------------

@login_required
def overhead_monitoring(request):
    """Dashboard showing over/under absorbed overhead per period."""
    from datetime import date
    from django.db.models import Sum
    periode = request.GET.get('periode') or date.today().strftime('%Y-%m')

    rates = (
        OverheadRate.objects
        .filter(overhead_category__is_active=True)
        .select_related('overhead_category')
        .order_by('overhead_category__overhead_type', 'overhead_category__name')
    )

    # Get distinct periods
    periods = (
        OverheadRate.objects
        .values_list('periode_bulan', flat=True)
        .distinct()
        .order_by('-periode_bulan')
    )

    prod_rows = []
    period_rows = []
    for rate in rates.filter(periode_bulan=periode):
        cat = rate.overhead_category
        applied = (
            OverheadApplied.objects
            .filter(overhead_category=cat, periode_bulan=periode)
            .aggregate(total=Sum('amount_applied'))['total'] or Decimal('0')
        )
        row = {
            'category': cat,
            'rate': rate,
            'applied': applied,
            'actual': rate.aktual_total,
            'variance': (applied - rate.aktual_total) if rate.aktual_total is not None else None,
        }
        if cat.overhead_type == 'PRODUCTION':
            prod_rows.append(row)
        else:
            period_rows.append(row)

    return render(request, 'manufacturing/overhead_monitoring.html', {
        'prod_rows': prod_rows,
        'period_rows': period_rows,
        'periode': periode,
        'periods': periods,
    })


# ---------------------------------------------------------------------------
# Period-end closing
# ---------------------------------------------------------------------------

@login_required
def overhead_period_closing(request):
    """Period-end closing: compare applied vs actual, generate adjustment journals."""
    if request.method == 'POST':
        periode = request.POST.get('periode', '').strip()
        cogs_id = request.POST.get('coa_cogs_id', '').strip()
        if not periode or not cogs_id:
            messages.error(request, 'Periode dan Akun COGS wajib diisi.')
            return redirect('manufacturing:overhead_monitoring')
        try:
            cogs_id_int = int(cogs_id)
            results = period_end_closing(
                periode, cogs_id_int, closed_by=request.user,
            )
            messages.success(
                request,
                f'Period-end closing untuk periode {periode} selesai. '
                f'{len([r for r in results if r["journal_id"]])} jurnal dibuat.',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect(f"{__import__('django.urls', fromlist=['reverse']).reverse('manufacturing:overhead_monitoring')}?periode={periode}")

    # GET: show form
    from datetime import date
    periode = request.GET.get('periode') or date.today().strftime('%Y-%m')
    from apps.master_data.utils import akun_sorted_queryset
    cogs_accounts = akun_sorted_queryset({'kode_akun__startswith': '5'})
    closing = PeriodClosing.objects.filter(periode_bulan=periode).first()
    preview_results, missing_actual = get_period_closing_preview(periode)
    year, month = map(int, periode.split('-'))
    wip_count = ProductionOrder.objects.filter(
        tanggal__year=year,
        tanggal__month=month,
        status='in_progress',
        is_processed=True,
    ).count()
    return render(request, 'manufacturing/overhead_period_closing.html', {
        'periode': periode,
        'cogs_accounts': cogs_accounts,
        'closing': closing,
        'preview_results': preview_results,
        'missing_actual': missing_actual,
        'wip_count': wip_count,
    })
