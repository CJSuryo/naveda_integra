import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages as dj_messages
from django.utils import timezone
from .models import PendapatanHeader, PendapatanEventLog
from .services import confirm_pendapatan, create_pendapatan_header, void_pendapatan, get_pendapatan_dashboard_kpi
from .forms import PendapatanHeaderForm, PendapatanItemForm


@login_required
def stt_defaults(request: HttpRequest) -> JsonResponse:
    from apps.purchase.models import SubTransactionType
    stt_id = request.GET.get('stt_id')
    if not stt_id:
        return JsonResponse({'error': 'stt_id required'}, status=400)
    try:
        stt = SubTransactionType.objects.select_related(
            'default_offset_account'
        ).get(pk=stt_id, module='pendapatan')
    except SubTransactionType.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({
        'revenue_account_id': stt.default_offset_account_id,
        'revenue_account_nama': str(stt.default_offset_account) if stt.default_offset_account else '',
    })


@login_required
def pendapatan_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_pendapatan_dashboard_kpi()
    return render(request, 'pendapatan/dashboard.html', {'kpi': kpi})


@login_required
def pendapatan_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q
    qs = PendapatanHeader.objects.order_by('-tanggal', '-created_at')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(transaction_id__icontains=search) | Q(deskripsi__icontains=search))
    return render(request, 'pendapatan/list.html', {
        'pendapatans': list(qs),
        'status_filter': status_filter,
        'search': search,
        'status_choices': PendapatanHeader.STATUS_CHOICES,
    })


@login_required
def pendapatan_create(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    from apps.entitas_bisnis.models import EntitasBisnis

    if request.method == 'POST':
        form = PendapatanHeaderForm(request.POST)
        item_count = max(int(request.POST.get('item_count', '1')), 1)
        item_forms = [PendapatanItemForm(request.POST, prefix=f'item_{i}') for i in range(item_count)]
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None

        if form.is_valid() and all(f.is_valid() for f in item_forms):
            cd = form.cleaned_data
            items = [f.cleaned_data for f in item_forms]
            try:
                eb = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
                pay_acct = items[0].get('payment_account')
                header = create_pendapatan_header(
                    tanggal=cd['tanggal'],
                    deskripsi=cd.get('deskripsi', ''),
                    payment_type=cd['payment_type'],
                    entitas_bisnis=eb,
                    payment_account=pay_acct,
                    items=items,
                    user=request.user,
                )
                dj_messages.success(request, f'Pendapatan {header.transaction_id} berhasil dibuat.')
                return redirect('pendapatan:detail', pk=header.pk)
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        form = PendapatanHeaderForm()
        item_forms = [PendapatanItemForm(prefix='item_0')]

    return render(request, 'pendapatan/form.html', {
        'form': form,
        'item_forms': item_forms,
        'mode': 'create',
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
    })


@login_required
def pendapatan_detail(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(
        PendapatanHeader.objects
        .prefetch_related('entitas_groups__items', 'event_logs__actor'),
        pk=pk,
    )
    return render(request, 'pendapatan/detail.html', {'header': header})


@login_required
def pendapatan_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            confirm_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} berhasil dikonfirmasi.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)


@login_required
def pendapatan_void(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            void_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} dibatalkan.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)
