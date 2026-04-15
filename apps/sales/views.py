"""Sales views."""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase, SubTransactionType

from .models import SalesHeader, SalesItem
from .services import (
    get_available_stock,
    process_sales_fifo,
    create_sales_automated_journals,
    reverse_sales_automated_journals,
    reverse_sales_fifo,
)


# ── Sales List ───────────────────────────────────────────────────────────────

@login_required
def sales_list(request: HttpRequest) -> HttpResponse:
    """List all sales transactions with filtering."""
    qs = (
        SalesHeader.objects
        .select_related('entitas_bisnis', 'payment_account')
        .prefetch_related(
            'items__item',
            'items__sub_transaction_type',
        )
        .order_by('-tanggal', '-created_at')
    )

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    stt_filter = request.GET.get('sub_transaction_type', '')
    eb_filter = request.GET.get('entitas_bisnis', '')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(items__item_id=item_filter).distinct()
    if stt_filter:
        qs = qs.filter(items__sub_transaction_type_id=stt_filter).distinct()
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter).distinct()

    # Build flat rows
    rows = []
    for sh in qs:
        for si in sh.items.all():
            if stt_filter and str(si.sub_transaction_type_id) != str(stt_filter):
                continue
            if item_filter and str(si.item_id) != str(item_filter):
                continue
            rows.append({
                'sales_header': sh,
                'item': si,
            })

    # Compute rowspan
    trx_rowspan: dict[str, int] = {}
    trx_seen: dict[str, bool] = {}
    for row in rows:
        tid = row['sales_header'].transaction_id
        trx_rowspan[tid] = trx_rowspan.get(tid, 0) + 1
    for row in rows:
        tid = row['sales_header'].transaction_id
        if tid not in trx_seen:
            trx_seen[tid] = True
            row['show_trx_cell'] = True
            row['trx_rowspan'] = trx_rowspan[tid]
        else:
            row['show_trx_cell'] = False
            row['trx_rowspan'] = 0

    # Inventory items for filter dropdown (RM/FG/ITM only)
    inventory_items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM']
    ).order_by('nama')

    return render(request, 'sales/sales_list.html', {
        'rows': rows,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'items': inventory_items,
        'sub_transaction_types': SubTransactionType.objects.filter(module='sales').order_by('nama'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'item_filter': item_filter,
        'stt_filter': stt_filter,
        'eb_filter': eb_filter,
    })


# ── Sales Create ─────────────────────────────────────────────────────────────

@login_required
def sales_create(request: HttpRequest) -> HttpResponse:
    """Create a new sales transaction."""
    if request.method == 'POST':
        return _handle_sales_save(request)

    inventory_items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM']
    ).select_related('coa_account').order_by('nama')

    return render(request, 'sales/sales_form.html', {
        'title': 'Tambah Penjualan',
        'today': timezone.now().date(),
        'items_master': inventory_items,
        'sub_transaction_types': SubTransactionType.objects.filter(module='sales').order_by('nama'),
        'akun_list': Akun.objects.all().order_by('kode_akun'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
    })


# ── Sales Update ─────────────────────────────────────────────────────────────

@login_required
def sales_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing sales transaction."""
    sales = get_object_or_404(SalesHeader, pk=pk)
    if sales.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah di-lock dan tidak bisa diedit.')
        return redirect('sales:detail', pk=pk)

    if request.method == 'POST':
        return _handle_sales_save(request, existing=sales)

    items_data = []
    for si in sales.items.select_related('item', 'sub_transaction_type', 'offset_coa_account',
                                          'revenue_account', 'tax_account', 'tax_payment_account'):
        items_data.append({
            'item_id': si.item_id,
            'item_name': str(si.item),
            'sub_transaction_type_id': si.sub_transaction_type_id,
            'quantity': str(si.quantity),
            'selling_price': str(si.selling_price),
            'offset_coa_account_id': si.offset_coa_account_id,
            'offset_coa_text': str(si.offset_coa_account),
            'revenue_account_id': si.revenue_account_id,
            'revenue_account_text': str(si.revenue_account),
            'tax': str(si.tax) if si.tax else '',
            'tax_type': si.tax_type or '',
            'tax_account_id': si.tax_account_id or '',
            'tax_account_text': str(si.tax_account) if si.tax_account else '',
            'tax_payment': si.tax_payment or '',
            'tax_payment_account_id': si.tax_payment_account_id or '',
            'tax_payment_account_text': str(si.tax_payment_account) if si.tax_payment_account else '',
        })

    inventory_items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM']
    ).select_related('coa_account').order_by('nama')

    return render(request, 'sales/sales_form.html', {
        'title': 'Edit Penjualan',
        'today': sales.tanggal,
        'sales': sales,
        'items_master': inventory_items,
        'sub_transaction_types': SubTransactionType.objects.filter(module='sales').order_by('nama'),
        'akun_list': Akun.objects.all().order_by('kode_akun'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'items_json': json.dumps(items_data),
    })


# ── Sales Detail ─────────────────────────────────────────────────────────────

@login_required
def sales_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """View sales transaction detail."""
    sales = get_object_or_404(
        SalesHeader.objects.select_related('entitas_bisnis', 'payment_account'),
        pk=pk,
    )
    items = sales.items.select_related(
        'item', 'sub_transaction_type', 'offset_coa_account',
        'revenue_account', 'tax_account', 'tax_payment_account',
    ).all()
    return render(request, 'sales/sales_detail.html', {
        'sales': sales,
        'items': items,
    })


# ── Sales Delete ─────────────────────────────────────────────────────────────

@login_required
def sales_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a sales transaction, reversing journals and FIFO."""
    sales = get_object_or_404(SalesHeader, pk=pk)
    if sales.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah di-lock dan tidak bisa dihapus.')
        return redirect('sales:detail', pk=pk)

    if request.method == 'POST':
        tid = sales.transaction_id
        with transaction.atomic():
            reverse_sales_automated_journals(sales)
            reverse_sales_fifo(sales)
            sales.delete()
        dj_messages.success(request, f'Sales {tid} berhasil dihapus.')
        return redirect('sales:list')

    return render(request, 'sales/sales_confirm_delete.html', {'object': sales})


# ── API Endpoints ────────────────────────────────────────────────────────────

@login_required
def api_stock_check(request: HttpRequest) -> JsonResponse:
    """Check available stock for an item."""
    item_id = request.GET.get('item_id', '')
    if not item_id:
        return JsonResponse({'available_stock': '0'})
    try:
        stock = get_available_stock(int(item_id))
        return JsonResponse({'available_stock': str(stock)})
    except (ValueError, TypeError):
        return JsonResponse({'available_stock': '0'})


@login_required
def api_stt_offset(request: HttpRequest) -> JsonResponse:
    """Return default offset account for a sales sub-transaction type."""
    stt_id = request.GET.get('stt_id', '')
    if not stt_id:
        return JsonResponse({'offset_account_id': '', 'offset_account_text': ''})
    try:
        stt = SubTransactionType.objects.select_related('default_offset_account').get(
            pk=stt_id, module='sales',
        )
        return JsonResponse({
            'offset_account_id': stt.default_offset_account_id,
            'offset_account_text': str(stt.default_offset_account),
        })
    except SubTransactionType.DoesNotExist:
        return JsonResponse({'offset_account_id': '', 'offset_account_text': ''})


# ── Internal Helpers ─────────────────────────────────────────────────────────

def _handle_sales_save(request: HttpRequest, existing: SalesHeader | None = None) -> HttpResponse:
    """Process the sales form submission (create or update)."""
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else None
    except (ValueError, TypeError):
        data = None

    if data is None:
        # Form-encoded data
        tanggal_str = request.POST.get('tanggal', '')
        eb_id = request.POST.get('entitas_bisnis', '')
        payment_account_id = request.POST.get('payment_account', '')
        deskripsi = request.POST.get('deskripsi', '')
        items_json = request.POST.get('items_data', '[]')
        try:
            items_list = json.loads(items_json)
        except (ValueError, TypeError):
            items_list = []
    else:
        tanggal_str = data.get('tanggal', '')
        eb_id = data.get('entitas_bisnis', '')
        payment_account_id = data.get('payment_account', '')
        deskripsi = data.get('deskripsi', '')
        items_list = data.get('items', [])

    # Validation
    errors: dict[str, str] = {}

    tanggal = None
    if tanggal_str:
        try:
            from datetime import date as dt_date
            tanggal = dt_date.fromisoformat(tanggal_str)
        except ValueError:
            errors['tanggal'] = 'Tanggal tidak valid.'
    else:
        errors['tanggal'] = 'Tanggal wajib diisi.'

    if not eb_id:
        errors['entitas_bisnis'] = 'Entitas Bisnis wajib dipilih.'

    if not payment_account_id:
        errors['payment_account'] = 'Payment Account wajib dipilih.'

    if not items_list:
        errors['items'] = 'Minimal satu item harus ditambahkan.'

    # Pre-compute total demand per item for cross-row stock validation
    item_demands: dict[int, Decimal] = {}
    for i, item_data in enumerate(items_list):
        item_id = item_data.get('item_id')
        if not item_id:
            continue
        try:
            qty = Decimal(str(item_data.get('quantity', 0)))
            if qty > 0:
                iid = int(item_id)
                item_demands[iid] = item_demands.get(iid, Decimal('0')) + qty
        except (InvalidOperation, ValueError):
            pass

    # Validate each item
    for i, item_data in enumerate(items_list):
        item_id = item_data.get('item_id')
        if not item_id:
            errors[f'item_{i}_id'] = f'Item {i + 1}: Item wajib dipilih.'
            continue

        try:
            qty = Decimal(str(item_data.get('quantity', 0)))
            if qty <= 0:
                errors[f'item_{i}_qty'] = f'Item {i + 1}: Quantity harus > 0.'
        except (InvalidOperation, ValueError):
            errors[f'item_{i}_qty'] = f'Item {i + 1}: Quantity tidak valid.'
            continue

        try:
            price = Decimal(str(item_data.get('selling_price', 0)))
            if price <= 0:
                errors[f'item_{i}_price'] = f'Item {i + 1}: Harga jual harus > 0.'
        except (InvalidOperation, ValueError):
            errors[f'item_{i}_price'] = f'Item {i + 1}: Harga jual tidak valid.'

        # Stock validation (check total demand for this item across all rows)
        iid = int(item_id)
        total_demand = item_demands.get(iid, Decimal('0'))
        available = get_available_stock(iid)
        # When editing, add back the existing consumed qty for this item
        if existing:
            for old_si in existing.items.filter(item_id=iid):
                available += old_si.quantity
        if total_demand > available:
            # Only show error on the first row for this item
            if f'item_stock_{iid}' not in errors:
                errors[f'item_stock_{iid}'] = (
                    f'Stok tidak mencukupi untuk item tersebut. '
                    f'Total permintaan: {total_demand} unit, Stok tersedia: {available} unit.'
                )

        # Tax validation
        tax_val = item_data.get('tax')
        if tax_val:
            try:
                tax_amount = Decimal(str(tax_val))
                if tax_amount > 0:
                    if not item_data.get('tax_type'):
                        errors[f'item_{i}_tax_type'] = f'Item {i + 1}: Tax Type wajib diisi jika ada pajak.'
                    if not item_data.get('tax_payment'):
                        errors[f'item_{i}_tax_payment'] = f'Item {i + 1}: Tax Payment Status wajib diisi jika ada pajak.'
            except (InvalidOperation, ValueError):
                errors[f'item_{i}_tax'] = f'Item {i + 1}: Nilai pajak tidak valid.'

        if not item_data.get('offset_coa_account_id'):
            errors[f'item_{i}_offset'] = f'Item {i + 1}: Offset CoA (HPP) wajib diisi.'
        if not item_data.get('revenue_account_id'):
            errors[f'item_{i}_revenue'] = f'Item {i + 1}: Revenue Account wajib diisi.'

    if errors:
        dj_messages.error(request, 'Terdapat kesalahan pada form. Silakan periksa kembali.')
        inventory_items = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM']
        ).select_related('coa_account').order_by('nama')
        return render(request, 'sales/sales_form.html', {
            'title': 'Edit Penjualan' if existing else 'Tambah Penjualan',
            'today': tanggal or timezone.now().date(),
            'sales': existing,
            'items_master': inventory_items,
            'sub_transaction_types': SubTransactionType.objects.filter(module='sales').order_by('nama'),
            'akun_list': Akun.objects.all().order_by('kode_akun'),
            'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
            'errors': errors,
            'items_json': json.dumps(items_list),
        })

    # Save
    with transaction.atomic():
        if existing:
            reverse_sales_automated_journals(existing)
            reverse_sales_fifo(existing)
            existing.items.all().delete()
            existing.tanggal = tanggal
            existing.entitas_bisnis_id = eb_id
            existing.payment_account_id = payment_account_id
            existing.deskripsi = deskripsi
            existing.save()
            sales = existing
        else:
            sales = SalesHeader.objects.create(
                tanggal=tanggal,
                entitas_bisnis_id=eb_id,
                payment_account_id=payment_account_id,
                deskripsi=deskripsi,
            )

        for item_data in items_list:
            tax_val = item_data.get('tax')
            tax_amount = Decimal(str(tax_val)) if tax_val else None

            SalesItem.objects.create(
                sales_header=sales,
                item_id=item_data['item_id'],
                sub_transaction_type_id=item_data['sub_transaction_type_id'],
                quantity=Decimal(str(item_data['quantity'])),
                selling_price=Decimal(str(item_data['selling_price'])),
                offset_coa_account_id=item_data['offset_coa_account_id'],
                revenue_account_id=item_data['revenue_account_id'],
                tax=tax_amount,
                tax_type=item_data.get('tax_type', ''),
                tax_account_id=item_data.get('tax_account_id') or None,
                tax_payment=item_data.get('tax_payment', ''),
                tax_payment_account_id=item_data.get('tax_payment_account_id') or None,
            )

        # Process FIFO outflow
        process_sales_fifo(sales)

        # Generate automated journals
        create_sales_automated_journals(sales)

    action = 'diperbarui' if existing else 'dibuat'
    dj_messages.success(request, f'Sales {sales.transaction_id} berhasil {action}.')
    return redirect('sales:detail', pk=sales.pk)
