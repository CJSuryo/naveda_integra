import json
from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis as EntitasBisnisModel
from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection

from .forms import UtangAttachmentForm, UtangDetailFormSet, UtangHeaderForm, UtangPembayaranForm
from .models import UtangDetail, UtangHeader, UtangPembayaran, UtangAttachment
from .services import (
    approve_utang,
    compute_bagian_lancar,
    create_manual_utang,
    create_utang_payment,
    delete_utang_attachment,
    get_bagian_lancar_list,
    get_utang_aging,
    get_utang_dashboard_kpi,
    get_utang_jatuh_tempo,
    get_utang_per_group_akun,
    get_utang_per_subjek,
    reject_utang,
    reverse_utang_header,
    reverse_utang_payment,
    submit_utang_for_approval,
    upload_utang_attachment,
)


def _utang_eb_filter_q(eb_selections: list[str]) -> Q | None:
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
def utang_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_utang_dashboard_kpi()
    buckets = get_utang_aging()
    due_soon = list(get_utang_jatuh_tempo(hari_ke_depan=30))
    bagian_lancar_list = get_bagian_lancar_list()
    return render(request, 'utang/dashboard.html', {
        'kpi': kpi,
        'buckets': buckets,
        'due_soon': due_soon,
        'bagian_lancar_list': bagian_lancar_list,
    })


@login_required
def utang_list(request: HttpRequest) -> HttpResponse:
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    status_filter = request.GET.get('status', '')
    jenis_filter = request.GET.get('jenis_utang', '')
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]
    search = request.GET.get('q', '').strip()

    qs = UtangHeader.objects.select_related('entitas_bisnis').order_by('-tanggal', '-created_at')

    eb_q = _utang_eb_filter_q(eb_filter_list)
    if eb_q is not None:
        qs = qs.filter(eb_q)
    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if jenis_filter:
        qs = qs.filter(jenis_utang=jenis_filter)
    if search:
        qs = qs.filter(
            Q(nomor_utang__icontains=search) |
            Q(kreditor__icontains=search) |
            Q(nomor_referensi__icontains=search) |
            Q(deskripsi__icontains=search)
        )

    return render(request, 'utang/list.html', {
        'utangs': list(qs),
        'eb_options': _get_eb_dropdown_options(),
        'eb_filter_list': eb_filter_list,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter,
        'jenis_filter': jenis_filter,
        'search': search,
        'status_choices': UtangHeader.STATUS_CHOICES,
        'jenis_choices': UtangHeader._meta.get_field('jenis_utang').choices,
    })


@login_required
def utang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(
        UtangHeader.objects
        .select_related('entitas_bisnis', 'coa_source_account', 'jurnal_pembentukan', 'approved_by')
        .prefetch_related(
            'details__purchase_item__item', 'details__coa_utang_account',
            'pembayaran__coa_account', 'pembayaran__jurnal_header',
            'attachments__uploaded_by', 'audit_logs__user',
        ),
        pk=pk,
    )
    payment_form = UtangPembayaranForm(utang_header=utang, initial={'tanggal': utang.tanggal})
    attachment_form = UtangAttachmentForm()
    bagian_lancar = (
        compute_bagian_lancar(utang)
        if utang.status in ('open', 'partial', 'overdue') and utang.outstanding_amount > 0
        else None
    )
    return render(request, 'utang/detail.html', {
        'utang': utang,
        'payment_form': payment_form,
        'attachment_form': attachment_form,
        'bagian_lancar': bagian_lancar,
    })


@login_required
def utang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST)
        formset = UtangDetailFormSet(request.POST, prefix='details')
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None
        entitas_bisnis_obj = EntitasBisnisModel.objects.filter(pk=resolved_eb['lv1_id']).first() if resolved_eb else None
        if form.is_valid() and formset.is_valid():
            details = []
            for detail_form in formset:
                if detail_form.cleaned_data and not detail_form.cleaned_data.get('DELETE', False):
                    details.append({
                        'coa_utang_account': detail_form.cleaned_data['coa_utang_account'],
                        'description': detail_form.cleaned_data.get('description', ''),
                        'amount': detail_form.cleaned_data['amount'],
                    })
            if not details:
                form.add_error(None, 'Minimal satu detail utang diperlukan.')
            else:
                try:
                    cd = form.cleaned_data
                    utang = create_manual_utang(
                        tanggal=cd['tanggal'],
                        entitas_bisnis=entitas_bisnis_obj,
                        deskripsi=cd.get('deskripsi', ''),
                        jenis_utang=cd['jenis_utang'],
                        kreditor=cd.get('kreditor', ''),
                        nomor_referensi=cd.get('nomor_referensi', ''),
                        kategori_jangka_waktu=cd['kategori_jangka_waktu'],
                        coa_source_account=cd.get('coa_source_account'),
                        requires_approval=cd.get('requires_approval', False),
                        tanggal_jatuh_tempo=cd.get('tanggal_jatuh_tempo'),
                        details=details,
                        user=request.user,
                    )
                    dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dibuat.')
                    return redirect('utang:detail', pk=utang.pk)
                except ValueError as exc:
                    form.add_error(None, str(exc))
        return render(request, 'utang/form.html', {
            'form': form, 'formset': formset, 'title': 'Tambah Utang',
            'eb_options_json': json.dumps(_get_eb_dropdown_options()),
            'eb_selected': eb_selection,
        })
    else:
        form = UtangHeaderForm()
        formset = UtangDetailFormSet(prefix='details', queryset=UtangDetail.objects.none())
    return render(request, 'utang/form.html', {
        'form': form, 'formset': formset, 'title': 'Tambah Utang',
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': '',
    })


@login_required
def utang_update(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.purchase_header_id:
        dj_messages.error(request, 'Utang dari pembelian tidak dapat diedit manual.')
        return redirect('utang:detail', pk=pk)
    if not utang.can_edit:
        dj_messages.error(request, 'Utang ini tidak dapat diedit pada status saat ini.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST, instance=utang)
        formset = UtangDetailFormSet(request.POST, instance=utang, prefix='details')
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None
        entitas_bisnis_obj = EntitasBisnisModel.objects.filter(pk=resolved_eb['lv1_id']).first() if resolved_eb else None
        if form.is_valid() and formset.is_valid():
            saved_utang = form.save()
            saved_utang.entitas_bisnis = entitas_bisnis_obj
            saved_utang.save(update_fields=['entitas_bisnis'])
            formset.save()
            saved_utang.total_amount = sum(
                d.amount for d in saved_utang.details.all()
            )
            saved_utang.save(update_fields=['total_amount'])
            dj_messages.success(request, f'Utang {saved_utang.nomor_utang} berhasil diperbarui.')
            return redirect('utang:detail', pk=saved_utang.pk)
        return render(request, 'utang/form.html', {
            'form': form, 'formset': formset, 'title': 'Edit Utang', 'utang': utang,
            'eb_options_json': json.dumps(_get_eb_dropdown_options()),
            'eb_selected': eb_selection,
        })
    else:
        eb_selected = f'lv1:{utang.entitas_bisnis_id}' if utang.entitas_bisnis_id else ''
        form = UtangHeaderForm(instance=utang)
        formset = UtangDetailFormSet(instance=utang, prefix='details')
    return render(request, 'utang/form.html', {
        'form': form, 'formset': formset, 'title': 'Edit Utang', 'utang': utang,
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': eb_selected,
    })


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
def utang_submit_approval(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    utang = get_object_or_404(UtangHeader, pk=pk)
    try:
        submit_utang_for_approval(utang, user=request.user)
        dj_messages.success(request, f'{utang.nomor_utang} diajukan untuk persetujuan.')
    except ValueError as exc:
        dj_messages.error(request, str(exc))
    return redirect('utang:detail', pk=pk)


@login_required
def utang_approve(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    utang = get_object_or_404(UtangHeader, pk=pk)
    try:
        approve_utang(utang, user=request.user)
        dj_messages.success(request, f'{utang.nomor_utang} disetujui dan diposting.')
    except ValueError as exc:
        dj_messages.error(request, str(exc))
    return redirect('utang:detail', pk=pk)


@login_required
def utang_reject(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    utang = get_object_or_404(UtangHeader, pk=pk)
    notes = request.POST.get('notes', '')
    try:
        reject_utang(utang, user=request.user, notes=notes)
        dj_messages.success(request, f'{utang.nomor_utang} ditolak.')
    except ValueError as exc:
        dj_messages.error(request, str(exc))
    return redirect('utang:detail', pk=pk)


@login_required
def utang_pay(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if utang.is_locked:
        dj_messages.error(request, 'Utang ini terkunci.')
        return redirect('utang:detail', pk=pk)
    if not utang.can_pay:
        dj_messages.error(request, 'Utang ini belum dapat dibayar.')
        return redirect('utang:detail', pk=pk)
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    form = UtangPembayaranForm(request.POST, utang_header=utang)
    if form.is_valid():
        try:
            create_utang_payment(utang, user=request.user, **form.cleaned_data)
            dj_messages.success(request, f'Pembayaran untuk {utang.nomor_utang} berhasil dicatat.')
            return redirect('utang:detail', pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    bagian_lancar = (
        compute_bagian_lancar(utang)
        if utang.status in ('open', 'partial', 'overdue') and utang.outstanding_amount > 0
        else None
    )
    return render(request, 'utang/detail.html', {
        'utang': utang,
        'payment_form': form,
        'attachment_form': UtangAttachmentForm(),
        'bagian_lancar': bagian_lancar,
    })


@login_required
def utang_payment_cancel(request: HttpRequest, pk: int, payment_pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    payment = get_object_or_404(UtangPembayaran, pk=payment_pk, utang_header=utang)
    if utang.is_locked:
        dj_messages.error(request, 'Utang ini terkunci.')
        return redirect('utang:detail', pk=pk)
    if request.method == 'POST':
        reverse_utang_payment(payment, user=request.user)
        dj_messages.success(request, 'Pembayaran berhasil dibatalkan.')
        return redirect('utang:detail', pk=pk)
    return render(request, 'utang/payment_cancel.html', {'utang': utang, 'payment': payment})


@login_required
def utang_attachment_upload(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)
    utang = get_object_or_404(UtangHeader, pk=pk)
    form = UtangAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        upload_utang_attachment(
            utang=utang,
            file=form.cleaned_data['file'],
            jenis_dokumen=form.cleaned_data['jenis_dokumen'],
            user=request.user,
        )
        dj_messages.success(request, 'Dokumen berhasil diupload.')
    else:
        dj_messages.error(request, 'Gagal upload dokumen.')
    return redirect('utang:detail', pk=pk)


@login_required
def utang_attachment_delete(request: HttpRequest, pk: int, attachment_pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    attachment = get_object_or_404(UtangAttachment, pk=attachment_pk, utang_header=utang)
    if request.method == 'POST':
        delete_utang_attachment(attachment, user=request.user)
        dj_messages.success(request, 'Dokumen berhasil dihapus.')
    return redirect('utang:detail', pk=pk)


# ── Reports ───────────────────────────────────────────────────────────────────

@login_required
def utang_report_subjek(request: HttpRequest) -> HttpResponse:
    qs = list(get_utang_per_subjek())
    if request.GET.get('format') == 'json':
        return JsonResponse({'results': [
            {
                'entitas_bisnis_id': r['entitas_bisnis__id'],
                'nama': r['entitas_bisnis__nama'],
                'kreditor': r['kreditor'],
                'jenis_utang': r['jenis_utang'],
                'total_utang': str(r['total_utang'] or '0'),
                'total_bayar': str(r['total_bayar'] or '0'),
                'jumlah_invoice': r['jumlah_invoice'],
            }
            for r in qs
        ]})
    return render(request, 'utang/report_subjek.html', {'rows': qs})


@login_required
def utang_report_akun(request: HttpRequest) -> HttpResponse:
    qs = list(get_utang_per_group_akun())
    if request.GET.get('format') == 'json':
        return JsonResponse({'results': [
            {'kode_akun': r['coa_utang_account__kode_akun'], 'nama': r['coa_utang_account__nama'], 'total': str(r['total'] or '0')}
            for r in qs
        ]})
    return render(request, 'utang/report_akun.html', {'rows': qs})


@login_required
def utang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_utang_aging()
    if request.GET.get('format') == 'json':
        def _s(entries):
            return [{'nomor_utang': e['utang'].nomor_utang, 'entitas': str(e['utang'].entitas_bisnis or ''), 'outstanding': str(e['outstanding']), 'hari': e['hari']} for e in entries]
        return JsonResponse({k: _s(v) for k, v in buckets.items()})
    return render(request, 'utang/report_aging.html', {'buckets': buckets})


@login_required
def utang_report_jatuh_tempo(request: HttpRequest) -> HttpResponse:
    hari = int(request.GET.get('hari', 7))
    qs = list(get_utang_jatuh_tempo(hari_ke_depan=hari))
    if request.GET.get('format') == 'json':
        return JsonResponse({'results': [
            {'nomor_utang': u.nomor_utang, 'entitas': str(u.entitas_bisnis or ''), 'tanggal_jatuh_tempo': str(u.tanggal_jatuh_tempo), 'total_amount': str(u.total_amount), 'status': u.status}
            for u in qs
        ]})
    return render(request, 'utang/report_jatuh_tempo.html', {'utangs': qs, 'hari': hari})
