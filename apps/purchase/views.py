"""Purchase views."""
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

from .forms import (
    ItemMasterPurchaseForm, KategoriItemForm, SubTransactionTypeForm,
)
from .models import (
    ItemMasterPurchase, KategoriItem, SubTransactionType,
    PurchaseHeader, PurchaseEntitasBisnis, PurchaseItem, FIFOBatch,
)
from .services import (
    create_automated_journals, create_fifo_batches,
    reverse_automated_journals, reverse_fifo_batches,
)


# ── Purchase List ────────────────────────────────────────────────────────────

@login_required
def purchase_list(request: HttpRequest) -> HttpResponse:
    """List all purchase transactions with filtering."""
    qs = (
        PurchaseHeader.objects
        .prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__items__item',
            'entitas_groups__items__sub_transaction_type',
        )
        .order_by('-tanggal', '-created_at')
    )

    # Filters
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
        qs = qs.filter(entitas_groups__items__item_id=item_filter).distinct()
    if stt_filter:
        qs = qs.filter(entitas_groups__items__sub_transaction_type_id=stt_filter).distinct()
    if eb_filter:
        qs = qs.filter(entitas_groups__entitas_bisnis_id=eb_filter).distinct()

    purchases = list(qs)

    # Build flat rows for the table
    rows = []
    for ph in purchases:
        for eg in ph.entitas_groups.all():
            for pi in eg.items.all():
                rows.append({
                    'purchase_header': ph,
                    'entitas_bisnis': eg.entitas_bisnis,
                    'item': pi,
                })

    return render(request, 'purchase/purchase_list.html', {
        'rows': rows,
        'purchases': purchases,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'items': ItemMasterPurchase.objects.all().order_by('nama'),
        'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'item_filter': item_filter,
        'stt_filter': stt_filter,
        'eb_filter': eb_filter,
    })


# ── Purchase Create ──────────────────────────────────────────────────────────

@login_required
def purchase_create(request: HttpRequest) -> HttpResponse:
    """Create a new purchase transaction with multiple EB groups and items."""
    if request.method == 'POST':
        return _handle_purchase_save(request)

    return render(request, 'purchase/purchase_form.html', {
        'title': 'Tambah Purchase',
        'today': timezone.now().date(),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
        'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
    })


# ── Purchase Update ──────────────────────────────────────────────────────────

@login_required
def purchase_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing purchase (only if not locked)."""
    purchase = get_object_or_404(
        PurchaseHeader.objects.prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__items__item',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__coa_account',
            'entitas_groups__items__offset_coa_account',
        ),
        pk=pk,
    )
    if purchase.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah terkunci (periode tutup buku).')
        return redirect('purchase:detail', pk=pk)

    if request.method == 'POST':
        return _handle_purchase_save(request, purchase)

    # Serialize existing data for the form
    eb_groups_data = []
    for eg in purchase.entitas_groups.all():
        items_data = []
        for pi in eg.items.all():
            items_data.append({
                'item_id': pi.item_id,
                'item_name': str(pi.item),
                'sub_transaction_type_id': pi.sub_transaction_type_id,
                'coa_account_id': pi.coa_account_id,
                'coa_account_text': str(pi.coa_account),
                'offset_coa_account_id': pi.offset_coa_account_id,
                'offset_coa_account_text': str(pi.offset_coa_account),
                'quantity': str(pi.quantity),
                'unit_price': str(pi.unit_price),
                'lead_time_days': pi.lead_time_days or '',
                'ordering_cost': str(pi.ordering_cost) if pi.ordering_cost else '',
                'holding_cost_pct': str(pi.holding_cost_pct) if pi.holding_cost_pct else '',
                'moq': str(pi.moq) if pi.moq else '',
                'target_turnover': str(pi.target_turnover) if pi.target_turnover else '',
            })
        eb_groups_data.append({
            'entitas_bisnis_id': eg.entitas_bisnis_id,
            'entitas_bisnis_name': eg.entitas_bisnis.nama,
            'items': items_data,
        })

    return render(request, 'purchase/purchase_form.html', {
        'title': 'Edit Purchase',
        'today': purchase.tanggal,
        'purchase': purchase,
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
        'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
        'eb_groups_json': json.dumps(eb_groups_data),
    })


# ── Purchase Detail ──────────────────────────────────────────────────────────

@login_required
def purchase_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show purchase detail with all EB groups and items."""
    purchase = get_object_or_404(
        PurchaseHeader.objects.prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__items__item',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__coa_account',
            'entitas_groups__items__offset_coa_account',
        ),
        pk=pk,
    )
    return render(request, 'purchase/purchase_detail.html', {'purchase': purchase})


# ── Purchase Delete ──────────────────────────────────────────────────────────

@login_required
def purchase_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a purchase and its associated journals/FIFO batches."""
    purchase = get_object_or_404(PurchaseHeader, pk=pk)
    if purchase.is_locked:
        dj_messages.error(request, 'Transaksi ini sudah terkunci (periode tutup buku).')
        return redirect('purchase:detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            reverse_fifo_batches(purchase)
            reverse_automated_journals(purchase)
            purchase.delete()
        dj_messages.success(request, f'Purchase {purchase.transaction_id} berhasil dihapus.')
        return redirect('purchase:list')

    return render(request, 'purchase/purchase_confirm_delete.html', {'object': purchase})


# ── Journal Preview API ──────────────────────────────────────────────────────

@login_required
def journal_preview(request: HttpRequest) -> JsonResponse:
    """Preview journal entries that would be created for the given purchase data."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    entries = []
    for group in data.get('eb_groups', []):
        eb_id = group.get('entitas_bisnis_id')
        eb_name = group.get('entitas_bisnis_name', f'EB {eb_id}')
        for item_data in group.get('items', []):
            try:
                qty = Decimal(str(item_data.get('quantity', 0)))
                price = Decimal(str(item_data.get('unit_price', 0)))
            except (InvalidOperation, TypeError):
                continue
            total = qty * price
            if total <= 0:
                continue
            coa_text = item_data.get('coa_account_text', '')
            offset_text = item_data.get('offset_coa_account_text', '')
            item_name = item_data.get('item_name', '')
            entries.append({
                'eb_name': eb_name,
                'item_name': item_name,
                'debit_account': coa_text,
                'credit_account': offset_text,
                'amount': str(total),
            })

    return JsonResponse({'entries': entries})


# ── Item Master CRUD ─────────────────────────────────────────────────────────

@login_required
def item_master_list(request: HttpRequest) -> HttpResponse:
    qs = ItemMasterPurchase.objects.select_related('kategori', 'coa_account').order_by('item_id')
    search = request.GET.get('q', '')
    if search:
        qs = qs.filter(Q(nama__icontains=search) | Q(item_id__icontains=search))
    return render(request, 'purchase/item_master_list.html', {'object_list': qs, 'search': search})


@login_required
def item_master_create(request: HttpRequest) -> HttpResponse:
    form = ItemMasterPurchaseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Item berhasil ditambahkan.')
        return redirect('purchase:item_master_list')
    return render(request, 'purchase/item_master_form.html', {'form': form, 'title': 'Tambah Item'})


@login_required
def item_master_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ItemMasterPurchase, pk=pk)
    form = ItemMasterPurchaseForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Item berhasil diperbarui.')
        return redirect('purchase:item_master_list')
    return render(request, 'purchase/item_master_form.html', {
        'form': form, 'title': 'Edit Item', 'object': obj,
    })


@login_required
def item_master_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ItemMasterPurchase, pk=pk)
    if request.method == 'POST':
        if obj.purchase_items.exists():
            dj_messages.error(request, 'Item tidak bisa dihapus karena sudah ada transaksi.')
            return redirect('purchase:item_master_list')
        obj.delete()
        dj_messages.success(request, 'Item berhasil dihapus.')
        return redirect('purchase:item_master_list')
    return render(request, 'purchase/item_master_confirm_delete.html', {'object': obj})


# ── Sub-Transaction Type (Settings) CRUD ─────────────────────────────────────

@login_required
def settings_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'purchase/settings_list.html', {
        'object_list': SubTransactionType.objects.select_related('default_offset_account').order_by('nama'),
    })


@login_required
def settings_create(request: HttpRequest) -> HttpResponse:
    form = SubTransactionTypeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Sub-Transaction Type berhasil ditambahkan.')
        return redirect('purchase:settings_list')
    return render(request, 'purchase/settings_form.html', {'form': form, 'title': 'Tambah Sub-Transaction Type'})


@login_required
def settings_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(SubTransactionType, pk=pk)
    form = SubTransactionTypeForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Sub-Transaction Type berhasil diperbarui.')
        return redirect('purchase:settings_list')
    return render(request, 'purchase/settings_form.html', {
        'form': form, 'title': 'Edit Sub-Transaction Type', 'object': obj,
    })


@login_required
def settings_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(SubTransactionType, pk=pk)
    if request.method == 'POST':
        obj.delete()
        dj_messages.success(request, 'Sub-Transaction Type berhasil dihapus.')
        return redirect('purchase:settings_list')
    return render(request, 'purchase/settings_confirm_delete.html', {'object': obj})


# ── Kategori Item CRUD ───────────────────────────────────────────────────────

@login_required
def kategori_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'purchase/kategori_list.html', {
        'object_list': KategoriItem.objects.order_by('nama'),
    })


@login_required
def kategori_create(request: HttpRequest) -> HttpResponse:
    form = KategoriItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Kategori berhasil ditambahkan.')
        return redirect('purchase:kategori_list')
    return render(request, 'purchase/kategori_form.html', {'form': form, 'title': 'Tambah Kategori'})


@login_required
def kategori_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KategoriItem, pk=pk)
    form = KategoriItemForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Kategori berhasil diperbarui.')
        return redirect('purchase:kategori_list')
    return render(request, 'purchase/kategori_form.html', {
        'form': form, 'title': 'Edit Kategori', 'object': obj,
    })


@login_required
def kategori_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KategoriItem, pk=pk)
    if request.method == 'POST':
        obj.delete()
        dj_messages.success(request, 'Kategori berhasil dihapus.')
        return redirect('purchase:kategori_list')
    return render(request, 'purchase/kategori_confirm_delete.html', {'object': obj})


# ── API endpoints ────────────────────────────────────────────────────────────

@login_required
def api_item_autocomplete(request: HttpRequest) -> JsonResponse:
    """Return item master options matching a search term."""
    term = request.GET.get('term', '')
    items = ItemMasterPurchase.objects.filter(
        Q(nama__icontains=term) | Q(item_id__icontains=term)
    ).select_related('kategori', 'coa_account').order_by('nama')[:50]
    results = [
        {
            'id': item.pk,
            'text': str(item),
            'item_id': item.item_id,
            'nama': item.nama,
            'kategori': item.kategori.nama if item.kategori else '',
            'coa_account_id': item.coa_account_id or '',
            'coa_account_text': str(item.coa_account) if item.coa_account else '',
        }
        for item in items
    ]
    return JsonResponse(results, safe=False)


@login_required
def api_item_create(request: HttpRequest) -> JsonResponse:
    """Create a new ItemMasterPurchase inline from the purchase form autocomplete.

    Accepts POST with JSON body: {"nama": "<item name>", "tipe_item": "<RM|FG|ITM>"}.
    Creates the item with default tipe_item='RM' and returns the new item's data.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    nama = (data.get('nama') or '').strip()
    if not nama:
        return JsonResponse({'error': 'nama wajib diisi'}, status=400)

    # Prevent duplicates — return existing item instead of error
    existing = ItemMasterPurchase.objects.filter(nama__iexact=nama).select_related('coa_account').first()
    if existing:
        return JsonResponse({
            'id': existing.pk,
            'text': str(existing),
            'item_id': existing.item_id,
            'nama': existing.nama,
            'tipe_item': existing.tipe_item,
            'coa_account_id': existing.coa_account_id or '',
            'coa_account_text': str(existing.coa_account) if existing.coa_account else '',
            'created': False,
        })

    tipe_item = data.get('tipe_item', 'RM')
    if tipe_item not in ('RM', 'FG', 'ITM'):
        tipe_item = 'RM'

    item = ItemMasterPurchase.objects.create(
        nama=nama,
        tipe_item=tipe_item,
    )
    return JsonResponse({
        'id': item.pk,
        'text': str(item),
        'item_id': item.item_id,
        'nama': item.nama,
        'tipe_item': item.tipe_item,
        'coa_account_id': '',
        'coa_account_text': '',
        'created': True,
    }, status=201)


@login_required
def api_stt_offset(request: HttpRequest) -> JsonResponse:
    """Return default offset account for a sub-transaction type."""
    stt_id = request.GET.get('stt_id', '')
    if not stt_id:
        return JsonResponse({'offset_account_id': '', 'offset_account_text': ''})
    try:
        stt = SubTransactionType.objects.select_related('default_offset_account').get(pk=stt_id)
        return JsonResponse({
            'offset_account_id': stt.default_offset_account_id,
            'offset_account_text': str(stt.default_offset_account),
        })
    except SubTransactionType.DoesNotExist:
        return JsonResponse({'offset_account_id': '', 'offset_account_text': ''})


# ── Internal helpers ─────────────────────────────────────────────────────────

def _handle_purchase_save(request: HttpRequest, existing: PurchaseHeader | None = None) -> HttpResponse:
    """Process purchase form POST data — create or update."""
    tanggal = request.POST.get('tanggal', '')
    deskripsi = request.POST.get('deskripsi', '').strip()
    groups_json = request.POST.get('eb_groups_data', '[]')

    errors: dict[str, str] = {}
    if not tanggal:
        errors['tanggal'] = 'Tanggal wajib diisi.'

    try:
        groups = json.loads(groups_json)
    except (ValueError, TypeError):
        groups = []

    if not groups:
        errors['groups'] = 'Minimal 1 entitas bisnis harus dipilih.'

    # Validate each group has items
    for i, group in enumerate(groups):
        if not group.get('entitas_bisnis_id'):
            errors[f'group_{i}'] = f'Entitas bisnis wajib dipilih untuk group {i + 1}.'
        if not group.get('items'):
            errors[f'group_{i}_items'] = f'Minimal 1 item wajib diisi untuk group {i + 1}.'
        for j, item_data in enumerate(group.get('items', [])):
            try:
                qty = Decimal(str(item_data.get('quantity', 0)))
                price = Decimal(str(item_data.get('unit_price', 0)))
            except (InvalidOperation, TypeError):
                errors[f'item_{i}_{j}'] = f'Quantity/price tidak valid untuk item {j + 1} group {i + 1}.'
                continue
            if qty <= 0:
                errors[f'item_{i}_{j}_qty'] = f'Quantity harus > 0 untuk item {j + 1} group {i + 1}.'
            if price <= 0:
                errors[f'item_{i}_{j}_price'] = f'Harga satuan harus > 0 untuk item {j + 1} group {i + 1}.'

    if errors:
        dj_messages.error(request, 'Terdapat kesalahan pada form. Silakan periksa kembali.')
        return render(request, 'purchase/purchase_form.html', {
            'title': 'Edit Purchase' if existing else 'Tambah Purchase',
            'today': tanggal or timezone.now().date(),
            'purchase': existing,
            'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
            'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
            'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
            'errors': errors,
            'eb_groups_json': json.dumps(groups),
        })

    with transaction.atomic():
        if existing:
            # Reverse old journals and FIFO before updating
            reverse_fifo_batches(existing)
            reverse_automated_journals(existing)
            existing.entitas_groups.all().delete()
            existing.tanggal = tanggal
            existing.deskripsi = deskripsi
            existing.save()
            purchase = existing
        else:
            purchase = PurchaseHeader.objects.create(
                tanggal=tanggal,
                deskripsi=deskripsi,
            )

        for group_data in groups:
            eb_id = group_data['entitas_bisnis_id']
            eb_group = PurchaseEntitasBisnis.objects.create(
                purchase_header=purchase,
                entitas_bisnis_id=eb_id,
            )
            for item_data in group_data.get('items', []):
                PurchaseItem.objects.create(
                    purchase_eb=eb_group,
                    item_id=item_data['item_id'],
                    sub_transaction_type_id=item_data['sub_transaction_type_id'],
                    coa_account_id=item_data['coa_account_id'],
                    offset_coa_account_id=item_data['offset_coa_account_id'],
                    quantity=Decimal(str(item_data['quantity'])),
                    unit_price=Decimal(str(item_data['unit_price'])),
                    lead_time_days=item_data.get('lead_time_days') or None,
                    ordering_cost=Decimal(str(item_data['ordering_cost'])) if item_data.get('ordering_cost') else None,
                    holding_cost_pct=Decimal(str(item_data['holding_cost_pct'])) if item_data.get('holding_cost_pct') else None,
                    moq=Decimal(str(item_data['moq'])) if item_data.get('moq') else None,
                    target_turnover=Decimal(str(item_data['target_turnover'])) if item_data.get('target_turnover') else None,
                )

        # Auto-generate journals and FIFO batches
        create_automated_journals(purchase)
        create_fifo_batches(purchase)

    action = 'diperbarui' if existing else 'dibuat'
    dj_messages.success(request, f'Purchase {purchase.transaction_id} berhasil {action}.')
    return redirect('purchase:detail', pk=purchase.pk)
