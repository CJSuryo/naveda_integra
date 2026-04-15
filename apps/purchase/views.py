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
    create_inventory_records, reverse_inventory_records,
)


def _get_eb_dropdown_options() -> list[dict[str, str]]:
    """Build hierarchical EntitasBisnis dropdown options (lv1/lv2/lv3)."""
    from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3

    lv1_list = list(EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'))
    lv2_list = list(
        EntitasBisnisLv2.objects.filter(status_aktif=True)
        .select_related('entitas_bisnis').order_by('nama')
    )
    lv3_list = list(
        EntitasBisnisLv3.objects.filter(status_aktif=True)
        .select_related('parent_lv2__entitas_bisnis').order_by('nama')
    )

    lv2_by_lv1: dict[int, list] = {}
    for lv2 in lv2_list:
        lv2_by_lv1.setdefault(lv2.entitas_bisnis_id, []).append(lv2)
    lv3_by_lv2: dict[int, list] = {}
    for lv3 in lv3_list:
        lv3_by_lv2.setdefault(lv3.parent_lv2_id, []).append(lv3)

    options: list[dict[str, str]] = []
    for eb in lv1_list:
        options.append({'value': f'lv1:{eb.pk}', 'label': eb.nama})
        for lv2 in lv2_by_lv1.get(eb.pk, []):
            options.append({'value': f'lv2:{lv2.pk}', 'label': f'\u00a0\u00a0\u00a0\u00a0↳ {lv2.nama}'})
            for lv3 in lv3_by_lv2.get(lv2.pk, []):
                options.append({'value': f'lv3:{lv3.pk}', 'label': f'\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0↳ {lv3.nama}'})
    return options


def _resolve_eb_selection(selection: str | int | None) -> dict | None:
    """Resolve a lv1:/lv2:/lv3: prefixed selection to a dict of all EB level ids.

    Returns ``{'lv1_id': X, 'lv2_id': Y_or_None, 'lv3_id': Z_or_None}`` or
    ``None`` if the selection is empty or invalid.

    Also accepts a bare integer (or integer-like string) as a direct lv1 pk
    for backward compatibility.
    """
    from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3

    if selection is None or selection == '':
        return None
    # Bare integer → treat as lv1 pk
    if isinstance(selection, int):
        return {'lv1_id': selection, 'lv2_id': None, 'lv3_id': None}
    selection = str(selection)
    if ':' not in selection:
        try:
            return {'lv1_id': int(selection), 'lv2_id': None, 'lv3_id': None}
        except (ValueError, TypeError):
            return None
    try:
        level, raw_pk = selection.split(':', 1)
        pk = int(raw_pk)
    except (ValueError, TypeError):
        return None

    if level == 'lv1':
        return {'lv1_id': pk, 'lv2_id': None, 'lv3_id': None}
    if level == 'lv2':
        lv2 = EntitasBisnisLv2.objects.filter(pk=pk).select_related('entitas_bisnis').first()
        if not lv2:
            return None
        return {'lv1_id': lv2.entitas_bisnis_id, 'lv2_id': lv2.pk, 'lv3_id': None}
    if level == 'lv3':
        lv3 = EntitasBisnisLv3.objects.filter(pk=pk).select_related('parent_lv2__entitas_bisnis').first()
        if not lv3:
            return None
        return {
            'lv1_id': lv3.parent_lv2.entitas_bisnis_id,
            'lv2_id': lv3.parent_lv2_id,
            'lv3_id': lv3.pk,
        }
    return None


# ── Purchase List ────────────────────────────────────────────────────────────

@login_required
def purchase_list(request: HttpRequest) -> HttpResponse:
    """List all purchase transactions with filtering."""
    qs = (
        PurchaseHeader.objects
        .prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__entitas_bisnis_lv2',
            'entitas_groups__entitas_bisnis_lv3',
            'entitas_groups__items__item',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__inventory_records',
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

    # Build flat rows for the table — apply item-level filters
    rows = []
    for ph in purchases:
        for eg in ph.entitas_groups.all():
            # Build display name at the most specific level
            if eg.entitas_bisnis_lv3_id:
                eb_display = (
                    f'{eg.entitas_bisnis.nama} / '
                    f'{eg.entitas_bisnis_lv2.nama} / '
                    f'{eg.entitas_bisnis_lv3.nama}'
                )
            elif eg.entitas_bisnis_lv2_id:
                eb_display = f'{eg.entitas_bisnis.nama} / {eg.entitas_bisnis_lv2.nama}'
            else:
                eb_display = eg.entitas_bisnis.nama
            for pi in eg.items.all():
                # Item-level row filtering
                if stt_filter and str(pi.sub_transaction_type_id) != str(stt_filter):
                    continue
                if item_filter and str(pi.item_id) != str(item_filter):
                    continue
                rows.append({
                    'purchase_header': ph,
                    'eb_display': eb_display,
                    'item': pi,
                })

    # Compute rowspan for merging Transaction ID cells
    trx_rowspan: dict[str, int] = {}
    trx_seen: dict[str, bool] = {}
    for row in rows:
        tid = row['purchase_header'].transaction_id
        trx_rowspan[tid] = trx_rowspan.get(tid, 0) + 1
    for row in rows:
        tid = row['purchase_header'].transaction_id
        if tid not in trx_seen:
            trx_seen[tid] = True
            row['show_trx_cell'] = True
            row['trx_rowspan'] = trx_rowspan[tid]
        else:
            row['show_trx_cell'] = False
            row['trx_rowspan'] = 0

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
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
        'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
        'kategori_items': KategoriItem.objects.all().order_by('nama'),
        'akun_list': Akun.objects.all().order_by('kode_akun'),
    })


# ── Purchase Update ──────────────────────────────────────────────────────────

@login_required
def purchase_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing purchase (only if not locked)."""
    purchase = get_object_or_404(
        PurchaseHeader.objects.prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__entitas_bisnis_lv2',
            'entitas_groups__entitas_bisnis_lv3',
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

    # Serialize existing data for the form — use the most specific level for the selector
    eb_groups_data = []
    for eg in purchase.entitas_groups.all():
        if eg.entitas_bisnis_lv3_id:
            eb_selection = f'lv3:{eg.entitas_bisnis_lv3_id}'
            eb_name = eg.entitas_bisnis_lv3.nama
        elif eg.entitas_bisnis_lv2_id:
            eb_selection = f'lv2:{eg.entitas_bisnis_lv2_id}'
            eb_name = eg.entitas_bisnis_lv2.nama
        else:
            eb_selection = f'lv1:{eg.entitas_bisnis_id}'
            eb_name = eg.entitas_bisnis.nama
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
                'metode_alokasi_biaya': pi.metode_alokasi_biaya or '',
                'tanggal_kadaluarsa': '',
                'lead_time_days': pi.lead_time_days or '',
                'ordering_cost': str(pi.ordering_cost) if pi.ordering_cost else '',
                'holding_cost_pct': str(pi.holding_cost_pct) if pi.holding_cost_pct else '',
                'moq': str(pi.moq) if pi.moq else '',
                'target_turnover': str(pi.target_turnover) if pi.target_turnover else '',
            })
        eb_groups_data.append({
            'entitas_bisnis_id': eb_selection,
            'entitas_bisnis_name': eb_name,
            'items': items_data,
        })

    return render(request, 'purchase/purchase_form.html', {
        'title': 'Edit Purchase',
        'today': purchase.tanggal,
        'purchase': purchase,
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
        'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
        'eb_groups_json': json.dumps(eb_groups_data),
        'kategori_items': KategoriItem.objects.all().order_by('nama'),
        'akun_list': Akun.objects.all().order_by('kode_akun'),
    })


# ── Purchase Detail ──────────────────────────────────────────────────────────

@login_required
def purchase_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show purchase detail with all EB groups, items, and journal preview."""
    purchase = get_object_or_404(
        PurchaseHeader.objects.prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__entitas_bisnis_lv2',
            'entitas_groups__entitas_bisnis_lv3',
            'entitas_groups__items__item',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__coa_account',
            'entitas_groups__items__offset_coa_account',
        ),
        pk=pk,
    )

    # Build journal preview entries
    journal_entries = []
    entry_no = 0
    for eg in purchase.entitas_groups.all():
        eb_name = eg.entitas_bisnis.nama
        if eg.entitas_bisnis_lv2:
            eb_name += f' / {eg.entitas_bisnis_lv2.nama}'
        if eg.entitas_bisnis_lv3:
            eb_name += f' / {eg.entitas_bisnis_lv3.nama}'
        for pi in eg.items.all():
            total = pi.total_value
            if total <= 0:
                continue
            entry_no += 1
            journal_entries.append({
                'no': entry_no,
                'entitas_bisnis': eb_name,
                'akun': str(pi.coa_account),
                'debit': total,
                'kredit': None,
            })
            journal_entries.append({
                'no': '',
                'entitas_bisnis': '',
                'akun': str(pi.offset_coa_account),
                'debit': None,
                'kredit': total,
            })

    return render(request, 'purchase/purchase_detail.html', {
        'purchase': purchase,
        'journal_entries': journal_entries,
    })


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
            reverse_inventory_records(purchase)
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
            entry_no = len(entries) // 2 + 1
            entries.append({
                'no': entry_no,
                'entitas_bisnis': eb_name,
                'akun': coa_text,
                'debit': str(total),
                'kredit': '',
            })
            entries.append({
                'no': '',
                'entitas_bisnis': '',
                'akun': offset_text,
                'debit': '',
                'kredit': str(total),
            })

    return JsonResponse({'entries': entries})


# ── Item Master CRUD ─────────────────────────────────────────────────────────

# Mapping of page slug → (title, subtitle, tipe_item filter values)
_ITEM_PAGE_MAP = {
    'persediaan': ('Persediaan (Inventory)', 'Raw Material, Finished Good, Item Lainnya', ['RM', 'FG', 'ITM']),
    'aset-tetap': ('Aset Tetap', 'Daftar aset tetap', ['ATP']),
    'aset-lainnya': ('Aset Lainnya', 'Daftar aset lainnya', ['ALL']),
}

_ITEM_PAGE_LIST_URL = {
    'persediaan': 'purchase:persediaan_list',
    'aset-tetap': 'purchase:aset_tetap_list',
    'aset-lainnya': 'purchase:aset_lainnya_list',
}


def _get_item_page(tipe_item: str) -> str:
    """Return the page slug for an item based on its tipe_item."""
    if tipe_item in ('RM', 'FG', 'ITM'):
        return 'persediaan'
    if tipe_item == 'ATP':
        return 'aset-tetap'
    if tipe_item == 'ALL':
        return 'aset-lainnya'
    return 'persediaan'


@login_required
def persediaan_list(request: HttpRequest) -> HttpResponse:
    return _item_master_list_page(request, 'persediaan')


@login_required
def aset_tetap_list(request: HttpRequest) -> HttpResponse:
    return _item_master_list_page(request, 'aset-tetap')


@login_required
def aset_lainnya_list(request: HttpRequest) -> HttpResponse:
    return _item_master_list_page(request, 'aset-lainnya')


def _item_master_list_page(request: HttpRequest, page: str) -> HttpResponse:
    title, subtitle, tipe_items = _ITEM_PAGE_MAP[page]
    qs = (
        ItemMasterPurchase.objects
        .filter(tipe_item__in=tipe_items)
        .select_related('kategori', 'coa_account')
        .prefetch_related('entitas_bisnis')
        .order_by('item_id')
    )
    search = request.GET.get('q', '')
    if search:
        qs = qs.filter(Q(nama__icontains=search) | Q(item_id__icontains=search))
    return render(request, 'purchase/item_master_list.html', {
        'object_list': qs,
        'search': search,
        'page_title': title,
        'page_subtitle': subtitle,
        'item_page': page,
        'list_url': _ITEM_PAGE_LIST_URL[page],
        'create_url': f'purchase:item_master_create',
    })


@login_required
def item_master_list(request: HttpRequest) -> HttpResponse:
    """Kept for backward compat — redirects to persediaan."""
    return redirect('purchase:persediaan_list')


@login_required
def item_master_create(request: HttpRequest) -> HttpResponse:
    page = request.GET.get('page', 'persediaan')
    _, _, valid_types = _ITEM_PAGE_MAP.get(page, _ITEM_PAGE_MAP['persediaan'])
    list_url = _ITEM_PAGE_LIST_URL.get(page, 'purchase:persediaan_list')

    form = ItemMasterPurchaseForm(request.POST or None, tipe_item_choices=valid_types)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Item berhasil ditambahkan.')
        return redirect(list_url)
    return render(request, 'purchase/item_master_form.html', {
        'form': form,
        'title': 'Tambah Item',
        'list_url': list_url,
        'item_page': page,
    })


@login_required
def item_master_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ItemMasterPurchase, pk=pk)
    page = _get_item_page(obj.tipe_item)
    _, _, valid_types = _ITEM_PAGE_MAP[page]
    list_url = _ITEM_PAGE_LIST_URL[page]

    form = ItemMasterPurchaseForm(request.POST or None, instance=obj, tipe_item_choices=valid_types)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, 'Item berhasil diperbarui.')
        return redirect(list_url)
    return render(request, 'purchase/item_master_form.html', {
        'form': form, 'title': 'Edit Item', 'object': obj,
        'list_url': list_url, 'item_page': page,
    })


@login_required
def item_master_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(ItemMasterPurchase, pk=pk)
    page = _get_item_page(obj.tipe_item)
    list_url = _ITEM_PAGE_LIST_URL[page]

    if request.method == 'POST':
        if obj.purchase_items.exists():
            dj_messages.error(request, 'Item tidak bisa dihapus karena sudah ada transaksi.')
            return redirect(list_url)
        obj.delete()
        dj_messages.success(request, 'Item berhasil dihapus.')
        return redirect(list_url)
    return render(request, 'purchase/item_master_confirm_delete.html', {
        'object': obj,
        'list_url': list_url,
    })


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
        'object_list': KategoriItem.objects.prefetch_related('entitas_bisnis').order_by('nama'),
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
    """Return item master options matching a search term, optionally filtered by EB."""
    term = request.GET.get('term', '')
    eb_lv1_id = request.GET.get('eb_lv1_id', '')
    qs = ItemMasterPurchase.objects.filter(
        Q(nama__icontains=term) | Q(item_id__icontains=term)
    ).select_related('kategori', 'coa_account').order_by('nama')

    if eb_lv1_id:
        # Filter to items linked to this entitas bisnis (lv1)
        qs = qs.filter(entitas_bisnis__pk=eb_lv1_id)

    items = qs[:50]
    results = [
        {
            'id': item.pk,
            'text': str(item),
            'item_id': item.item_id,
            'nama': item.nama,
            'tipe_item': item.tipe_item,
            'kategori': item.kategori.nama if item.kategori else '',
            'coa_account_id': item.coa_account_id or '',
            'coa_account_text': str(item.coa_account) if item.coa_account else '',
            'metode_biaya_persediaan': item.metode_biaya_persediaan or '',
            'lama_kadaluarsa': item.lama_kadaluarsa or '',
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
    if tipe_item not in ('RM', 'FG', 'ITM', 'ATP', 'ALL'):
        tipe_item = 'RM'

    kategori_id = data.get('kategori_id') or None
    coa_account_id = data.get('coa_account_id') or None
    eb_ids = data.get('entitas_bisnis_ids', [])

    create_kwargs: dict = {
        'nama': nama,
        'tipe_item': tipe_item,
        'kategori_id': kategori_id,
        'coa_account_id': coa_account_id,
    }

    # Fields for inventory items (RM/FG/ITM)
    if tipe_item in ('RM', 'FG', 'ITM'):
        create_kwargs['velocity_category'] = data.get('velocity_category', '')
        create_kwargs['lama_kadaluarsa'] = data.get('lama_kadaluarsa') or None
        create_kwargs['threshold_days_outstanding'] = data.get('threshold_days_outstanding') or None
        create_kwargs['metode_biaya_persediaan'] = data.get('metode_biaya_persediaan', '')
    # Fields for Aset Tetap (ATP)
    elif tipe_item == 'ATP':
        create_kwargs['masa_manfaat'] = data.get('masa_manfaat') or None
        create_kwargs['metode_penyusutan'] = data.get('metode_penyusutan', '')
    # Fields for Aset Lainnya (ALL)
    elif tipe_item == 'ALL':
        create_kwargs['masa_manfaat'] = data.get('masa_manfaat') or None
        create_kwargs['metode_amortisasi'] = data.get('metode_amortisasi', '')

    item = ItemMasterPurchase.objects.create(**create_kwargs)
    if eb_ids:
        item.entitas_bisnis.set(eb_ids)

    return JsonResponse({
        'id': item.pk,
        'text': str(item),
        'item_id': item.item_id,
        'nama': item.nama,
        'tipe_item': item.tipe_item,
        'coa_account_id': item.coa_account_id or '',
        'coa_account_text': str(item.coa_account) if item.coa_account else '',
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


@login_required
def api_kategori_filter(request: HttpRequest) -> JsonResponse:
    """Return KategoriItem options filtered by tipe_item and optionally entitas bisnis."""
    tipe_item = request.GET.get('tipe_item', '')
    eb_lv1_id = request.GET.get('eb_lv1_id', '')

    qs = KategoriItem.objects.all().order_by('nama')
    if tipe_item:
        qs = qs.filter(tipe_item=tipe_item)
    if eb_lv1_id:
        qs = qs.filter(entitas_bisnis__pk=eb_lv1_id)

    results = [{'id': k.pk, 'nama': k.nama} for k in qs]
    return JsonResponse(results, safe=False)


@login_required
def api_kategori_create(request: HttpRequest) -> JsonResponse:
    """Create a new KategoriItem inline from the purchase form modal."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    nama = (data.get('nama') or '').strip()
    tipe_item = data.get('tipe_item', 'RM')
    eb_ids = data.get('entitas_bisnis_ids', [])

    if not nama:
        return JsonResponse({'error': 'Nama kategori wajib diisi.'}, status=400)
    if tipe_item not in ('RM', 'FG', 'ITM', 'ATP', 'ALL'):
        tipe_item = 'RM'

    # Check for duplicate
    existing = KategoriItem.objects.filter(nama__iexact=nama, tipe_item=tipe_item).first()
    if existing:
        return JsonResponse({
            'id': existing.pk,
            'nama': existing.nama,
            'tipe_item': existing.tipe_item,
            'created': False,
        })

    kategori = KategoriItem.objects.create(nama=nama, tipe_item=tipe_item)
    if eb_ids:
        kategori.entitas_bisnis.set(eb_ids)

    return JsonResponse({
        'id': kategori.pk,
        'nama': kategori.nama,
        'tipe_item': kategori.tipe_item,
        'created': True,
    }, status=201)


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
        eb_raw = group.get('entitas_bisnis_id')
        if not eb_raw:
            errors[f'group_{i}'] = f'Entitas bisnis wajib dipilih untuk group {i + 1}.'
        elif _resolve_eb_selection(eb_raw) is None:
            errors[f'group_{i}'] = f'Entitas bisnis tidak valid untuk group {i + 1}.'
        if not group.get('items'):
            errors[f'group_{i}_items'] = f'Minimal 1 item wajib diisi untuk group {i + 1}.'
        for j, item_data in enumerate(group.get('items', [])):
            if not item_data.get('item_id'):
                errors[f'item_{i}_{j}_item'] = f'Item wajib dipilih untuk baris {j + 1} group {i + 1}.'
            if not item_data.get('sub_transaction_type_id'):
                errors[f'item_{i}_{j}_stt'] = f'Sub-transaction type wajib dipilih untuk baris {j + 1} group {i + 1}.'
            if not item_data.get('coa_account_id'):
                errors[f'item_{i}_{j}_coa'] = f'Akun CoA wajib diisi untuk baris {j + 1} group {i + 1}.'
            if not item_data.get('offset_coa_account_id'):
                errors[f'item_{i}_{j}_offset'] = f'Akun Offset CoA wajib diisi untuk baris {j + 1} group {i + 1}.'
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
            'eb_options_json': json.dumps(_get_eb_dropdown_options()),
            'items_master': ItemMasterPurchase.objects.all().order_by('nama'),
            'sub_transaction_types': SubTransactionType.objects.all().order_by('nama'),
            'errors': errors,
            'eb_groups_json': json.dumps(groups),
            'kategori_items': KategoriItem.objects.all().order_by('nama'),
            'akun_list': Akun.objects.all().order_by('kode_akun'),
        })

    # Determine the dominant tipe_item prefix for all items to decide the transaction ID prefix.
    # If items span multiple type-groups, we create separate PurchaseHeaders per group.
    # Group mapping: RM/FG/ITM → PUR-INV, ATP → PUR-ATP, ALL → PUR-ALL

    # Pre-fetch all item tipe_item values in one query to avoid N+1
    all_item_ids = []
    for group_data in groups:
        for item_data in group_data.get('items', []):
            iid = item_data.get('item_id', '')
            if iid:
                all_item_ids.append(iid)
    item_type_map = dict(
        ItemMasterPurchase.objects
        .filter(pk__in=all_item_ids)
        .values_list('pk', 'tipe_item')
    )

    def _item_prefix_group(item_pk: int | str) -> str:
        """Return the transaction prefix group for an item."""
        tipe = item_type_map.get(int(item_pk), 'RM') if item_pk else 'RM'
        return PurchaseHeader.ITEM_TYPE_PREFIX_MAP.get(tipe or 'RM', 'PUR-INV')

    # Collect all items across groups and determine which prefix groups are present
    prefix_groups: dict[str, list[tuple]] = {}  # prefix → [(group_data, [item_data, ...])]
    for group_data in groups:
        # Separate items per prefix within each EB group
        items_by_prefix: dict[str, list] = {}
        for item_data in group_data.get('items', []):
            pfx = _item_prefix_group(item_data.get('item_id', ''))
            items_by_prefix.setdefault(pfx, []).append(item_data)
        for pfx, items_list in items_by_prefix.items():
            prefix_groups.setdefault(pfx, []).append((group_data, items_list))

    with transaction.atomic():
        if existing:
            # Reverse old journals, FIFO, and inventory records before updating
            reverse_inventory_records(existing)
            reverse_fifo_batches(existing)
            reverse_automated_journals(existing)
            existing.entitas_groups.all().delete()

        created_purchases = []

        # If editing an existing purchase AND all items belong to the same prefix group
        # as the original, update in place. Otherwise create new headers.
        prefixes = list(prefix_groups.keys())

        if existing and len(prefixes) == 1:
            new_prefix = prefixes[0]
            existing_prefix = existing.transaction_id.rsplit('-', 1)[0]  # e.g. 'PUR-INV'
            if existing_prefix == new_prefix:
                # Same prefix — update existing header in place
                existing.tanggal = tanggal
                existing.deskripsi = deskripsi
                existing.save()
                purchase = existing
            else:
                # Prefix changed — delete old and create new
                existing.delete()
                purchase = PurchaseHeader(tanggal=tanggal, deskripsi=deskripsi)
                purchase.save(_trx_prefix=new_prefix)

            for group_data, items_list in prefix_groups[new_prefix]:
                eb_resolved = _resolve_eb_selection(group_data['entitas_bisnis_id'])
                eb_group = PurchaseEntitasBisnis.objects.create(
                    purchase_header=purchase,
                    entitas_bisnis_id=eb_resolved['lv1_id'],
                    entitas_bisnis_lv2_id=eb_resolved['lv2_id'],
                    entitas_bisnis_lv3_id=eb_resolved['lv3_id'],
                )
                for item_data in items_list:
                    PurchaseItem.objects.create(
                        purchase_eb=eb_group,
                        item_id=item_data['item_id'],
                        sub_transaction_type_id=item_data['sub_transaction_type_id'],
                        coa_account_id=item_data['coa_account_id'],
                        offset_coa_account_id=item_data['offset_coa_account_id'],
                        quantity=Decimal(str(item_data['quantity'])),
                        unit_price=Decimal(str(item_data['unit_price'])),
                        metode_alokasi_biaya=item_data.get('metode_alokasi_biaya', ''),
                        lead_time_days=item_data.get('lead_time_days') or None,
                        ordering_cost=Decimal(str(item_data['ordering_cost'])) if item_data.get('ordering_cost') else None,
                        holding_cost_pct=Decimal(str(item_data['holding_cost_pct'])) if item_data.get('holding_cost_pct') else None,
                        moq=Decimal(str(item_data['moq'])) if item_data.get('moq') else None,
                        target_turnover=Decimal(str(item_data['target_turnover'])) if item_data.get('target_turnover') else None,
                    )
            create_automated_journals(purchase)
            create_fifo_batches(purchase)
            create_inventory_records(purchase)
            created_purchases.append(purchase)
        else:
            # Delete existing if it exists (we're splitting into multiple)
            if existing:
                existing.delete()

            # Create one PurchaseHeader per prefix group
            for pfx, group_items_list in prefix_groups.items():
                purchase = PurchaseHeader(tanggal=tanggal, deskripsi=deskripsi)
                purchase.save(_trx_prefix=pfx)

                for group_data, items_list in group_items_list:
                    eb_resolved = _resolve_eb_selection(group_data['entitas_bisnis_id'])
                    eb_group = PurchaseEntitasBisnis.objects.create(
                        purchase_header=purchase,
                        entitas_bisnis_id=eb_resolved['lv1_id'],
                        entitas_bisnis_lv2_id=eb_resolved['lv2_id'],
                        entitas_bisnis_lv3_id=eb_resolved['lv3_id'],
                    )
                    for item_data in items_list:
                        PurchaseItem.objects.create(
                            purchase_eb=eb_group,
                            item_id=item_data['item_id'],
                            sub_transaction_type_id=item_data['sub_transaction_type_id'],
                            coa_account_id=item_data['coa_account_id'],
                            offset_coa_account_id=item_data['offset_coa_account_id'],
                            quantity=Decimal(str(item_data['quantity'])),
                            unit_price=Decimal(str(item_data['unit_price'])),
                            metode_alokasi_biaya=item_data.get('metode_alokasi_biaya', ''),
                            lead_time_days=item_data.get('lead_time_days') or None,
                            ordering_cost=Decimal(str(item_data['ordering_cost'])) if item_data.get('ordering_cost') else None,
                            holding_cost_pct=Decimal(str(item_data['holding_cost_pct'])) if item_data.get('holding_cost_pct') else None,
                            moq=Decimal(str(item_data['moq'])) if item_data.get('moq') else None,
                            target_turnover=Decimal(str(item_data['target_turnover'])) if item_data.get('target_turnover') else None,
                        )
                create_automated_journals(purchase)
                create_fifo_batches(purchase)
                create_inventory_records(purchase)
                created_purchases.append(purchase)

    if len(created_purchases) == 1:
        purchase = created_purchases[0]
        action = 'diperbarui' if existing else 'dibuat'
        dj_messages.success(request, f'Purchase {purchase.transaction_id} berhasil {action}.')
        return redirect('purchase:detail', pk=purchase.pk)
    else:
        trx_ids = ', '.join(p.transaction_id for p in created_purchases)
        dj_messages.success(request, f'Purchase berhasil dibuat: {trx_ids}')
        return redirect('purchase:list')
