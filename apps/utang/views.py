import json
from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection

from .forms import UtangHeaderForm, UtangPembayaranForm
from .models import UtangHeader, UtangPembayaran
from .services import (
    create_manual_utang,
    create_utang_payment,
    get_utang_aging,
    get_utang_jatuh_tempo,
    get_utang_per_group_akun,
    get_utang_per_subjek,
    reverse_utang_header,
    reverse_utang_payment,
)


def _utang_eb_filter_q(eb_selections: list[str]) -> Q | None:
    """Resolve hierarchical EB selections to a Q matching UtangHeader.entitas_bisnis (lv1).

    Utang only stores the lv1 EB, so lv2/lv3 selections collapse to their lv1 ancestor.
    Returns None when no valid selection is provided.
    """
    lv1_ids: set[int] = set()
    for sel in eb_selections:
        resolved = _resolve_eb_selection(sel)
        if not resolved:
            continue
        lv1_ids.add(resolved['lv1_id'])
    if not lv1_ids:
        return None
    return Q(entitas_bisnis_id__in=lv1_ids)


@login_required
def utang_list(request: HttpRequest) -> HttpResponse:
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    status_filter = request.GET.get('status', '')
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    eb_q = _utang_eb_filter_q(eb_filter_list)
    utangs: list[UtangHeader] = []

    if eb_q is not None:
        qs = (
            UtangHeader.objects
            .select_related('entitas_bisnis')
            .filter(eb_q)
            .order_by('-tanggal', '-created_at')
        )
        if tanggal_dari:
            qs = qs.filter(tanggal__gte=tanggal_dari)
        if tanggal_sampai:
            qs = qs.filter(tanggal__lte=tanggal_sampai)
        if status_filter:
            qs = qs.filter(status=status_filter)
        utangs = list(qs)

    return render(request, 'utang/list.html', {
        'utangs': utangs,
        'eb_options': _get_eb_dropdown_options(),
        'eb_filter_list': eb_filter_list,
        'eb_selected': eb_q is not None,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter,
        'status_choices': UtangHeader.STATUS_CHOICES,
    })


@login_required
def utang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(
        UtangHeader.objects.select_related('entitas_bisnis').prefetch_related(
            'details__purchase_item__item', 'pembayaran__coa_account',
        ),
        pk=pk,
    )
    payment_form = UtangPembayaranForm(utang_header=utang, initial={'tanggal': utang.tanggal})
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': payment_form})


@login_required
def utang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST)
        if form.is_valid():
            utang = create_manual_utang(**form.cleaned_data)
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dibuat.')
            return redirect('utang:detail', pk=utang.pk)
    else:
        form = UtangHeaderForm()
    return render(request, 'utang/form.html', {'form': form, 'title': 'Tambah Utang'})


@login_required
def utang_update(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.purchase_header_id:
        dj_messages.error(request, 'Utang dari pembelian tidak dapat diedit manual.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST, instance=utang)
        if form.is_valid():
            form.save()
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil diperbarui.')
            return redirect('utang:detail', pk=utang.pk)
    else:
        form = UtangHeaderForm(instance=utang)
    return render(request, 'utang/form.html', {'form': form, 'title': 'Edit Utang'})


@login_required
def utang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.is_locked:
        dj_messages.error(request, 'Utang ini terkunci dan tidak dapat dihapus.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        nomor = utang.nomor_utang
        reverse_utang_header(utang, request.user)
        dj_messages.success(request, f'Utang {nomor} berhasil dihapus.')
        return redirect('utang:list')
    return render(request, 'utang/delete.html', {'utang': utang})


@login_required
def utang_pay(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.is_locked:
        dj_messages.error(request, 'Utang ini terkunci dan tidak dapat dibayar.')
        return redirect('utang:detail', pk=pk)
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)

    form = UtangPembayaranForm(request.POST, utang_header=utang)
    if form.is_valid():
        try:
            create_utang_payment(utang, **form.cleaned_data)
            dj_messages.success(request, f'Pembayaran untuk {utang.nomor_utang} berhasil dicatat.')
            return redirect('utang:detail', pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': form})


@login_required
def utang_payment_cancel(request: HttpRequest, pk: int, payment_pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    payment = get_object_or_404(UtangPembayaran, pk=payment_pk, utang_header=utang)
    if utang.is_locked:
        dj_messages.error(request, 'Utang ini terkunci dan pembayarannya tidak dapat dibatalkan.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        reverse_utang_payment(payment, user=request.user)
        dj_messages.success(request, 'Pembayaran berhasil dibatalkan.')
        return redirect('utang:detail', pk=pk)
    return render(request, 'utang/payment_cancel.html', {'utang': utang, 'payment': payment})


@login_required
def utang_report_subjek(request: HttpRequest) -> HttpResponse:
    qs = list(get_utang_per_subjek())
    if request.GET.get('format') == 'json':
        data = [
            {
                'entitas_bisnis_id': r['entitas_bisnis__id'],
                'nama': r['entitas_bisnis__nama'],
                'total_utang': str(r['total_utang'] or '0'),
                'total_bayar': str(r['total_bayar'] or '0'),
                'jumlah_invoice': r['jumlah_invoice'],
            }
            for r in qs
        ]
        return JsonResponse({'results': data})
    return render(request, 'utang/report_subjek.html', {'rows': qs})


@login_required
def utang_report_akun(request: HttpRequest) -> HttpResponse:
    qs = list(get_utang_per_group_akun())
    if request.GET.get('format') == 'json':
        data = [
            {
                'kode_akun': r['coa_utang_account__kode_akun'],
                'nama': r['coa_utang_account__nama'],
                'total': str(r['total'] or '0'),
            }
            for r in qs
        ]
        return JsonResponse({'results': data})
    return render(request, 'utang/report_akun.html', {'rows': qs})


@login_required
def utang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_utang_aging()
    if request.GET.get('format') == 'json':
        def _serialize(entries):
            return [
                {
                    'nomor_utang': e['utang'].nomor_utang,
                    'entitas': str(e['utang'].entitas_bisnis or ''),
                    'outstanding': str(e['outstanding']),
                    'hari': e['hari'],
                }
                for e in entries
            ]
        return JsonResponse({k: _serialize(v) for k, v in buckets.items()})
    return render(request, 'utang/report_aging.html', {'buckets': buckets})


@login_required
def utang_report_jatuh_tempo(request: HttpRequest) -> HttpResponse:
    hari = int(request.GET.get('hari', 7))
    qs = list(get_utang_jatuh_tempo(hari_ke_depan=hari))
    if request.GET.get('format') == 'json':
        data = [
            {
                'nomor_utang': u.nomor_utang,
                'entitas': str(u.entitas_bisnis or ''),
                'tanggal_jatuh_tempo': str(u.tanggal_jatuh_tempo),
                'total_amount': str(u.total_amount),
                'status': u.status,
            }
            for u in qs
        ]
        return JsonResponse({'results': data})
    return render(request, 'utang/report_jatuh_tempo.html', {'utangs': qs, 'hari': hari})
