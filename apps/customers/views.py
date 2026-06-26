# apps/customers/views.py
import json
from django.contrib.auth.decorators import login_required

from naveda_integra.json_utils import safe_json
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Customer
from .forms import CustomerForm


def _resolve_eb(eb_selection: str, user):
    """Return resolved EB dict or None. Import here to avoid circular at module load."""
    from apps.purchase.views import _resolve_eb_selection
    return _resolve_eb_selection(eb_selection, user) if eb_selection else None


def _apply_eb_to_customer(customer: Customer, resolved: dict) -> None:
    """Populate all three EB FK fields from a resolved EB selection dict."""
    from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3
    customer.entitas_bisnis = EntitasBisnis.objects.filter(pk=resolved['lv1_id']).first()
    customer.entitas_bisnis_lv2 = (
        EntitasBisnisLv2.objects.filter(pk=resolved['lv2_id']).first() if resolved.get('lv2_id') else None
    )
    customer.entitas_bisnis_lv3 = (
        EntitasBisnisLv3.objects.filter(pk=resolved['lv3_id']).first() if resolved.get('lv3_id') else None
    )


@login_required
def customer_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q
    from apps.purchase.views import _get_eb_tree, _resolve_eb_selection

    search = request.GET.get('q', '').strip()
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    qs = Customer.objects.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3'
    ).order_by('nama')

    if search:
        qs = qs.filter(
            Q(nama__icontains=search) |
            Q(email__icontains=search) |
            Q(telepon__icontains=search)
        )
    if eb_filter_list:
        lv1_ids = set()
        for sel in eb_filter_list:
            resolved = _resolve_eb_selection(sel, request.user)
            if resolved:
                lv1_ids.add(resolved['lv1_id'])
        if lv1_ids:
            qs = qs.filter(entitas_bisnis_id__in=lv1_ids)

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'customers/list.html', {
        'page_obj': page,
        'search': search,
        'eb_filter_list': eb_filter_list,
        'eb_tree': _get_eb_tree(request.user),
    })


@login_required
def customer_create(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        eb_selection = request.POST.get('eb_selection', '')
        resolved = _resolve_eb(eb_selection, request.user)
        form_valid = form.is_valid()
        if not resolved:
            form.add_error(None, 'Pilih entitas bisnis.')
        if form_valid and resolved:
            customer = form.save(commit=False)
            _apply_eb_to_customer(customer, resolved)
            customer.save()
            return redirect('customers:list')
        eb_selected = eb_selection
    else:
        form = CustomerForm()
        eb_selected = ''

    return render(request, 'customers/form.html', {
        'form': form,
        'mode': 'create',
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
        'eb_selected': eb_selected,
    })


@login_required
def customer_update(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options

    customer = get_object_or_404(Customer, pk=pk)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        eb_selection = request.POST.get('eb_selection', '')
        resolved = _resolve_eb(eb_selection, request.user)
        form_valid = form.is_valid()
        if not resolved:
            form.add_error(None, 'Pilih entitas bisnis.')
        if form_valid and resolved:
            customer = form.save(commit=False)
            _apply_eb_to_customer(customer, resolved)
            customer.save()
            return redirect('customers:list')
        eb_selected = eb_selection
    else:
        form = CustomerForm(instance=customer)
        if customer.entitas_bisnis_lv3_id:
            eb_selected = f'lv3:{customer.entitas_bisnis_lv3_id}'
        elif customer.entitas_bisnis_lv2_id:
            eb_selected = f'lv2:{customer.entitas_bisnis_lv2_id}'
        else:
            eb_selected = f'lv1:{customer.entitas_bisnis_id}' if customer.entitas_bisnis_id else ''

    return render(request, 'customers/form.html', {
        'form': form,
        'mode': 'update',
        'object': customer,
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
        'eb_selected': eb_selected,
    })


@login_required
def customer_delete(request: HttpRequest, pk: int) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.delete()
        return redirect('customers:list')
    return render(request, 'customers/hapus_konfirmasi.html', {'object': customer})


@login_required
@require_POST
def customer_quick_create(request: HttpRequest) -> JsonResponse:
    form = CustomerForm(request.POST)
    eb_selection = request.POST.get('eb_selection', '')
    resolved = _resolve_eb(eb_selection, request.user)

    errors = {}
    if not resolved:
        errors['eb_selection'] = ['Pilih entitas bisnis.']

    if not form.is_valid():
        errors.update({k: [str(e) for e in v] for k, v in form.errors.items()})

    if errors:
        return JsonResponse({'success': False, 'errors': errors})

    customer = form.save(commit=False)
    _apply_eb_to_customer(customer, resolved)
    customer.save()
    return JsonResponse({'success': True, 'customer': {'id': customer.pk, 'nama': customer.nama}})
