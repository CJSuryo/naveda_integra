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
    ItemForm,
    JurnalHeaderForm, JurnalDetailForm,
    JurnalAutomasiForm, JurnalAutomasiAkunForm,
    AutomasiEntryForm,
)
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)


def _parse_int_list(values: list[str]) -> list[int]:
    """Parse a list of string values into integers, ignoring non-digit values."""
    return [int(x) for x in values if x.isdigit()]


# ── Rekap Jurnal (replaces old index / header_list) ─────────────────────────

@login_required
def rekap_jurnal(request: HttpRequest) -> HttpResponse:
    """Read-only journal recap with date range and entitas bisnis filtering."""
    from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3

    qs = (
        JurnalHeader.objects
        .select_related('tipe_transaksi', 'entitas_bisnis', 'item', 'transaction_prefix', 'no_bukti')
        .prefetch_related('details__akun')
        .order_by('-tanggal', 'nomor_transaksi')
    )

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    eb_lv1_ids = request.GET.getlist('eb_lv1')
    eb_lv2_ids = request.GET.getlist('eb_lv2')
    eb_lv3_ids = request.GET.getlist('eb_lv3')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)

    # Build entitas bisnis filter: collect Lv1 IDs from all levels
    eb_filter_ids = set()
    if eb_lv1_ids:
        eb_filter_ids.update(_parse_int_list(eb_lv1_ids))
    if eb_lv2_ids:
        lv2_parent_ids = EntitasBisnisLv2.objects.filter(
            pk__in=_parse_int_list(eb_lv2_ids)
        ).values_list('entitas_bisnis_id', flat=True)
        eb_filter_ids.update(lv2_parent_ids)
    if eb_lv3_ids:
        lv3_parent_ids = EntitasBisnisLv3.objects.filter(
            pk__in=_parse_int_list(eb_lv3_ids)
        ).select_related('parent_lv2').values_list('parent_lv2__entitas_bisnis_id', flat=True)
        eb_filter_ids.update(lv3_parent_ids)

    if eb_filter_ids:
        qs = qs.filter(entitas_bisnis_id__in=eb_filter_ids)

    headers = list(qs)

    # Prepare entitas bisnis hierarchy for filter modal
    eb_lv1_all = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
    eb_lv2_all = EntitasBisnisLv2.objects.filter(status_aktif=True).select_related('entitas_bisnis').order_by('nama')
    eb_lv3_all = EntitasBisnisLv3.objects.filter(status_aktif=True).select_related('parent_lv2__entitas_bisnis').order_by('nama')

    return render(request, 'jurnal/rekap_jurnal.html', {
        'headers': headers,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'eb_lv1_all': eb_lv1_all,
        'eb_lv2_all': eb_lv2_all,
        'eb_lv3_all': eb_lv3_all,
        'selected_lv1': eb_lv1_ids,
        'selected_lv2': eb_lv2_ids,
        'selected_lv3': eb_lv3_ids,
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
                is_penyesuaian=True,
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
    """Trial balance with saldo awal, mutasi modul, sebelum & setelah penyesuaian."""
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')

    akun_list = Akun.objects.all().order_by('kode_akun')

    # Helper: aggregate debit/kredit for a queryset of JurnalDetail
    def _aggregate(qs):
        result = (
            qs.values('akun_id')
            .annotate(
                total_debit=Coalesce(Sum('debit'), Value(Decimal('0')), output_field=DecimalField()),
                total_kredit=Coalesce(Sum('kredit'), Value(Decimal('0')), output_field=DecimalField()),
            )
        )
        return {row['akun_id']: row for row in result}

    # Saldo Awal: all entries BEFORE tanggal_dari
    saldo_awal_map = {}
    if tanggal_dari:
        saldo_awal_map = _aggregate(
            JurnalDetail.objects.filter(jurnal_header__tanggal__lt=tanggal_dari)
        )

    # Period filter
    period_filter = {}
    if tanggal_dari:
        period_filter['jurnal_header__tanggal__gte'] = tanggal_dari
    if tanggal_sampai:
        period_filter['jurnal_header__tanggal__lte'] = tanggal_sampai

    # Mutasi Modul: automated entries within period (is_penyesuaian=False)
    modul_map = _aggregate(
        JurnalDetail.objects.filter(
            jurnal_header__is_penyesuaian=False, **period_filter
        )
    )

    # Penyesuaian: manual entries within period (is_penyesuaian=True)
    penyesuaian_map = _aggregate(
        JurnalDetail.objects.filter(
            jurnal_header__is_penyesuaian=True, **period_filter
        )
    )

    def _get(m, akun_id, field):
        return m.get(akun_id, {}).get(field, Decimal('0'))

    rows = []
    for akun in akun_list:
        sa_d = _get(saldo_awal_map, akun.pk, 'total_debit')
        sa_k = _get(saldo_awal_map, akun.pk, 'total_kredit')
        modul_d = _get(modul_map, akun.pk, 'total_debit')
        modul_k = _get(modul_map, akun.pk, 'total_kredit')
        peny_d = _get(penyesuaian_map, akun.pk, 'total_debit')
        peny_k = _get(penyesuaian_map, akun.pk, 'total_kredit')

        # Sebelum penyesuaian = saldo awal + mutasi modul
        sblm_d = sa_d + modul_d
        sblm_k = sa_k + modul_k

        # Setelah penyesuaian = sebelum + penyesuaian manual
        stlh_d = sblm_d + peny_d
        stlh_k = sblm_k + peny_k

        rows.append({
            'akun': akun,
            'sa_d': sa_d, 'sa_k': sa_k,
            'modul_d': modul_d, 'modul_k': modul_k,
            'sblm_d': sblm_d, 'sblm_k': sblm_k,
            'peny_d': peny_d, 'peny_k': peny_k,
            'stlh_d': stlh_d, 'stlh_k': stlh_k,
        })

    return render(request, 'jurnal/neraca_saldo.html', {
        'rows': rows,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
    })


# ── Akun autocomplete API ───────────────────────────────────────────────────

@login_required
def akun_autocomplete(request: HttpRequest) -> JsonResponse:
    """Return Akun options matching a search term, for autocomplete widgets."""
    term = request.GET.get('term', '')
    akuns = Akun.objects.filter(
        nama__icontains=term
    ).order_by('kategori_id', 'kategori_akun')[:20]
    results = [
        {
            'id': a.pk,
            'text': f'{a.kode_akun} - {a.nama}',
            'kode': a.kode_akun,
            'nama': a.nama,
        }
        for a in akuns
    ]
    return JsonResponse(results, safe=False)


@login_required
def manual_jurnal_create(request: HttpRequest) -> HttpResponse:
    """Spreadsheet-like direct manual journal entry form."""
    from apps.entitas_bisnis.models import EntitasBisnis as EBModel
    from django.utils import timezone
    import json

    if request.method == 'POST':
        tanggal = request.POST.get('tanggal')
        uraian = request.POST.get('uraian_transaksi', '').strip()
        eb_id = request.POST.get('entitas_bisnis') or None
        rows_json = request.POST.get('rows_data', '[]')

        errors = {}
        if not tanggal:
            errors['tanggal'] = 'Tanggal wajib diisi.'
        if not uraian:
            errors['uraian_transaksi'] = 'Deskripsi wajib diisi.'

        try:
            rows = json.loads(rows_json)
        except (ValueError, TypeError):
            rows = []

        rows = [r for r in rows if r.get('akun_id')]
        if not rows:
            errors['rows'] = 'Minimal 1 baris akun wajib diisi.'

        from decimal import Decimal as D
        total_debit = sum(D(str(r.get('debit') or 0)) for r in rows)
        total_kredit = sum(D(str(r.get('kredit') or 0)) for r in rows)

        if not errors and total_debit != total_kredit:
            errors['balance'] = f'Total Debit ({total_debit}) harus sama dengan Total Kredit ({total_kredit}).'

        if errors:
            eb_list = EBModel.objects.filter(status_aktif=True).order_by('nama')
            return render(request, 'jurnal/manual_jurnal.html', {
                'today': tanggal or timezone.now().date(),
                'eb_list': eb_list,
                'errors': errors,
                'posted': True,
            })

        nomor = _next_nomor_transaksi('TRX-MAN')
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=uraian,
            entitas_bisnis_id=eb_id,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(
                jurnal_header=header,
                akun_id=row['akun_id'],
                debit=Decimal(str(row.get('debit') or 0)),
                kredit=Decimal(str(row.get('kredit') or 0)),
            )
            for row in rows
        ])
        from django.contrib import messages as dj_messages
        dj_messages.success(request, f'Jurnal manual {nomor} berhasil dibuat.')
        return redirect('jurnal:header_detail', pk=header.pk)

    eb_list = EBModel.objects.filter(status_aktif=True).order_by('nama')
    from django.utils import timezone
    return render(request, 'jurnal/manual_jurnal.html', {
        'today': timezone.now().date(),
        'eb_list': eb_list,
        'errors': {},
    })
