"""Jurnal views."""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Max, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.master_data.models import Akun, AsetLv2, KewajibanLv2, EkuitasLv2

from .forms import (
    ItemForm, TransactionPrefixForm,
    JurnalHeaderForm, JurnalDetailForm,
    JurnalAutomasiForm, JurnalAutomasiAkunForm,
    AutomasiEntryForm,
)
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)


# ── Rekap Jurnal (replaces old index / header_list) ─────────────────────────

@login_required
def rekap_jurnal(request: HttpRequest) -> HttpResponse:
    """Read-only journal recap with date range filtering."""
    qs = (
        JurnalHeader.objects
        .select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix', 'no_bukti')
        .prefetch_related('details__akun')
        .order_by('-tanggal', 'nomor_transaksi')
    )

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)

    headers = list(qs)

    return render(request, 'jurnal/rekap_jurnal.html', {
        'headers': headers,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
    })


# ── JurnalHeader detail (read-only) ─────────────────────────────────────────

@login_required
def header_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(
        JurnalHeader.objects.select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix'),
        pk=pk,
    )
    details = obj.details.select_related('akun').order_by('pk')
    return render(request, 'jurnal/header_detail.html', {'object': obj, 'details': details})


# ── Item CRUD ─────────────────────────────────────────────────────────────────

@login_required
def item_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'jurnal/item_list.html', {'object_list': Item.objects.all().order_by('kode')})


@login_required
def item_create(request: HttpRequest) -> HttpResponse:
    form = ItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:item_list')
    return render(request, 'jurnal/item_form.html', {'form': form, 'title': 'Tambah Item'})


@login_required
def item_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Item, pk=pk)
    form = ItemForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:item_list')
    return render(request, 'jurnal/item_form.html', {'form': form, 'title': 'Edit Item', 'object': obj})


@login_required
def item_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Item, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('jurnal:item_list')
    return render(request, 'jurnal/item_confirm_delete.html', {'object': obj})


# ── TransactionPrefix CRUD ───────────────────────────────────────────────────

@login_required
def prefix_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'jurnal/prefix_list.html', {
        'object_list': TransactionPrefix.objects.all().order_by('kode'),
    })


@login_required
def prefix_create(request: HttpRequest) -> HttpResponse:
    form = TransactionPrefixForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:prefix_list')
    return render(request, 'jurnal/prefix_form.html', {'form': form, 'title': 'Tambah Prefiks Transaksi'})


@login_required
def prefix_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TransactionPrefix, pk=pk)
    form = TransactionPrefixForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:prefix_list')
    return render(request, 'jurnal/prefix_form.html', {'form': form, 'title': 'Edit Prefiks Transaksi', 'object': obj})


@login_required
def prefix_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TransactionPrefix, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('jurnal:prefix_list')
    return render(request, 'jurnal/prefix_confirm_delete.html', {'object': obj})


# ── Automasi / Jurnal Manual CRUD ────────────────────────────────────────────

@login_required
def automasi_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'jurnal/automasi_list.html', {
        'object_list': JurnalAutomasi.objects.all().order_by('nama'),
    })


@login_required
def automasi_create(request: HttpRequest) -> HttpResponse:
    form = JurnalAutomasiForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:automasi_list')
    return render(request, 'jurnal/automasi_form.html', {'form': form, 'title': 'Tambah Jurnal Manual'})


@login_required
def automasi_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    form = JurnalAutomasiForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:automasi_list')
    return render(request, 'jurnal/automasi_form.html', {'form': form, 'title': 'Edit Jurnal Manual', 'object': obj})


@login_required
def automasi_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('jurnal:automasi_list')
    return render(request, 'jurnal/automasi_confirm_delete.html', {'object': obj})


@login_required
def automasi_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    mappings = obj.akun_mappings.select_related('akun').order_by('pk')
    add_form = JurnalAutomasiAkunForm()
    return render(request, 'jurnal/automasi_detail.html', {
        'object': obj, 'mappings': mappings, 'add_form': add_form,
    })


@login_required
def automasi_add_akun(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    if request.method == 'POST':
        form = JurnalAutomasiAkunForm(request.POST)
        if form.is_valid():
            mapping = form.save(commit=False)
            mapping.automasi = obj
            mapping.save()
    return redirect('jurnal:automasi_detail', pk=pk)


@login_required
def automasi_remove_akun(request: HttpRequest, pk: int, mapping_pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    mapping = get_object_or_404(JurnalAutomasiAkun, pk=mapping_pk, automasi=obj)
    if request.method == 'POST':
        mapping.delete()
    return redirect('jurnal:automasi_detail', pk=pk)


def _next_nomor_transaksi(prefix_kode: str) -> str:
    """Generate the next sequential transaction number for a prefix.

    Uses database-level locking to avoid race conditions.
    """
    from django.db import transaction

    with transaction.atomic():
        last = (
            JurnalHeader.objects
            .select_for_update()
            .filter(nomor_transaksi__startswith=prefix_kode + '-')
            .order_by('-nomor_transaksi')
            .values_list('nomor_transaksi', flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit('-', 1)[1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'{prefix_kode}-{seq:03d}'


@login_required
def automasi_entry(request: HttpRequest, pk: int) -> HttpResponse:
    """Show the form to create an automated journal entry based on the mapping."""
    automasi = get_object_or_404(JurnalAutomasi, pk=pk)
    mappings = automasi.akun_mappings.select_related('akun').order_by('pk')

    if request.method == 'POST':
        form = AutomasiEntryForm(request.POST)
        if form.is_valid():
            tanggal = form.cleaned_data['tanggal']
            uraian = form.cleaned_data['uraian_transaksi']
            item = form.cleaned_data['item']
            prefix = form.cleaned_data['transaction_prefix']
            nomor = _next_nomor_transaksi(prefix.kode)

            header = JurnalHeader.objects.create(
                tanggal=tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=uraian,
                item=item,
                transaction_prefix=prefix,
            )

            # Create detail lines: read amounts from POST for each mapped akun
            for mapping in mappings:
                debit_key = f'debit_{mapping.pk}'
                kredit_key = f'kredit_{mapping.pk}'
                debit = Decimal(request.POST.get(debit_key, '0') or '0')
                kredit = Decimal(request.POST.get(kredit_key, '0') or '0')
                if debit or kredit:
                    JurnalDetail.objects.create(
                        jurnal_header=header,
                        akun=mapping.akun,
                        debit=debit,
                        kredit=kredit,
                    )
            return redirect('jurnal:header_detail', pk=header.pk)
    else:
        from django.utils import timezone
        form = AutomasiEntryForm(initial={'tanggal': timezone.now().date()})

    return render(request, 'jurnal/automasi_entry.html', {
        'automasi': automasi, 'mappings': mappings, 'form': form,
    })


# ── Neraca Saldo (Trial Balance) ────────────────────────────────────────────

@login_required
def neraca_saldo(request: HttpRequest) -> HttpResponse:
    """Trial balance showing all accounts with debit/credit totals."""
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')

    # Build filter for JurnalDetail based on date range
    detail_filter = {}
    if tanggal_dari:
        detail_filter['jurnal_header__tanggal__gte'] = tanggal_dari
    if tanggal_sampai:
        detail_filter['jurnal_header__tanggal__lte'] = tanggal_sampai

    # Aggregate debit/kredit per akun
    akun_totals = (
        JurnalDetail.objects
        .filter(**detail_filter)
        .values('akun_id')
        .annotate(
            total_debit=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField()),
            total_kredit=Coalesce(Sum('kredit'), Value(Decimal('0')), output_field=DecimalField()),
        )
    )
    totals_map = {row['akun_id']: row for row in akun_totals}

    # Get all akun records ordered by kode_akun
    akun_list = Akun.objects.all().order_by('kode_akun')

    rows = []
    grand_debit = Decimal('0')
    grand_kredit = Decimal('0')
    for akun in akun_list:
        t = totals_map.get(akun.pk, {})
        debit = t.get('total_debit', Decimal('0'))
        kredit = t.get('total_kredit', Decimal('0'))
        # Compute saldo (balance) - net debit or credit
        saldo_debit = Decimal('0')
        saldo_kredit = Decimal('0')
        if debit > kredit:
            saldo_debit = debit - kredit
        elif kredit > debit:
            saldo_kredit = kredit - debit
        grand_debit += saldo_debit
        grand_kredit += saldo_kredit
        rows.append({
            'akun': akun,
            'debit': debit,
            'kredit': kredit,
            'saldo_debit': saldo_debit,
            'saldo_kredit': saldo_kredit,
        })

    return render(request, 'jurnal/neraca_saldo.html', {
        'rows': rows,
        'grand_debit': grand_debit,
        'grand_kredit': grand_kredit,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
    })


# ── Akun autocomplete API ───────────────────────────────────────────────────

@login_required
def akun_autocomplete(request: HttpRequest) -> JsonResponse:
    """Return Akun options matching a search term, for autocomplete widgets."""
    term = request.GET.get('term', '')
    akuns = Akun.objects.filter(nama__icontains=term).order_by('kategori_id', 'kategori_akun')[:20]
    results = [{'id': a.pk, 'text': f'{a.kode_akun} - {a.nama}'} for a in akuns]
    return JsonResponse(results, safe=False)
