"""Jurnal views."""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.master_data.models import Akun

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


# ── Index ─────────────────────────────────────────────────────────────────────

@login_required
def index(request: HttpRequest) -> HttpResponse:
    """Combined jurnal index showing headers with their details."""
    headers = (
        JurnalHeader.objects
        .select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix')
        .prefetch_related('details__akun')
        .order_by('-tanggal', 'nomor_transaksi')
    )
    return render(request, 'jurnal/index.html', {'headers': headers})


# ── JurnalHeader CRUD ─────────────────────────────────────────────────────────

@login_required
def header_list(request: HttpRequest) -> HttpResponse:
    headers = (
        JurnalHeader.objects
        .select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix')
        .order_by('-tanggal', 'nomor_transaksi')
    )
    return render(request, 'jurnal/header_list.html', {'object_list': headers})


@login_required
def header_create(request: HttpRequest) -> HttpResponse:
    form = JurnalHeaderForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:header_list')
    return render(request, 'jurnal/header_form.html', {'form': form, 'title': 'Tambah Jurnal Header'})


@login_required
def header_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalHeader, pk=pk)
    form = JurnalHeaderForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:header_list')
    return render(request, 'jurnal/header_form.html', {'form': form, 'title': 'Edit Jurnal Header', 'object': obj})


@login_required
def header_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalHeader, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('jurnal:header_list')
    return render(request, 'jurnal/header_confirm_delete.html', {'object': obj})


@login_required
def header_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(
        JurnalHeader.objects.select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix'),
        pk=pk,
    )
    details = obj.details.select_related('akun').order_by('pk')
    return render(request, 'jurnal/header_detail.html', {'object': obj, 'details': details})


# ── JurnalDetail CRUD ─────────────────────────────────────────────────────────

@login_required
def detail_create(request: HttpRequest, header_pk: int) -> HttpResponse:
    header = get_object_or_404(JurnalHeader, pk=header_pk)
    form = JurnalDetailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.jurnal_header = header
        obj.save()
        return redirect('jurnal:header_detail', pk=header_pk)
    return render(request, 'jurnal/detail_form.html', {
        'form': form, 'header': header, 'title': 'Tambah Jurnal Detail',
    })


@login_required
def detail_update(request: HttpRequest, header_pk: int, pk: int) -> HttpResponse:
    header = get_object_or_404(JurnalHeader, pk=header_pk)
    obj = get_object_or_404(JurnalDetail, pk=pk, jurnal_header=header)
    form = JurnalDetailForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:header_detail', pk=header_pk)
    return render(request, 'jurnal/detail_form.html', {
        'form': form, 'header': header, 'object': obj, 'title': 'Edit Jurnal Detail',
    })


@login_required
def detail_delete(request: HttpRequest, header_pk: int, pk: int) -> HttpResponse:
    header = get_object_or_404(JurnalHeader, pk=header_pk)
    obj = get_object_or_404(JurnalDetail, pk=pk, jurnal_header=header)
    if request.method == 'POST':
        obj.delete()
        return redirect('jurnal:header_detail', pk=header_pk)
    return render(request, 'jurnal/detail_confirm_delete.html', {'object': obj, 'header': header})


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


# ── Automasi CRUD ────────────────────────────────────────────────────────────

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
    return render(request, 'jurnal/automasi_form.html', {'form': form, 'title': 'Tambah Automasi Jurnal'})


@login_required
def automasi_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(JurnalAutomasi, pk=pk)
    form = JurnalAutomasiForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('jurnal:automasi_list')
    return render(request, 'jurnal/automasi_form.html', {'form': form, 'title': 'Edit Automasi Jurnal', 'object': obj})


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


# ── Akun autocomplete API ───────────────────────────────────────────────────

@login_required
def akun_autocomplete(request: HttpRequest) -> JsonResponse:
    """Return Akun options matching a search term, for autocomplete widgets."""
    term = request.GET.get('term', '')
    akuns = Akun.objects.filter(nama__icontains=term).order_by('kategori_id', 'kategori_akun')[:20]
    results = [{'id': a.pk, 'text': f'{a.kode_akun} - {a.nama}'} for a in akuns]
    return JsonResponse(results, safe=False)
