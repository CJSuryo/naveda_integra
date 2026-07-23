from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from apps.accounts.views import _check_perm
from apps.entitas_bisnis.models import EntitasBisnisLv3
from .access import accessible_lv2_qs, accessible_merchant_qs, accessible_store_qs
from .models import MerchantPOSConfig, StorePOSConfig
from .forms import MerchantPOSConfigForm, StorePOSConfigForm, PaymentMethodForm, WorkShiftForm


def _safe_next(request):
    """Return ``?next=`` only when it is a local path, else ''."""
    nxt = request.GET.get('next', '')
    return nxt if nxt.startswith('/') and not nxt.startswith('//') else ''


@login_required
def merchant_config(request, lv2_pk):
    """POS configuration for an operating company (EntitasBisnis level 2)."""
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    lv2 = get_object_or_404(
        accessible_lv2_qs(request.user).select_related('entitas_bisnis'), pk=lv2_pk
    )
    config, _ = MerchantPOSConfig.objects.get_or_create(entitas_bisnis_lv2=lv2)
    next_url = _safe_next(request)
    if request.method == 'POST':
        form = MerchantPOSConfigForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Konfigurasi merchant POS disimpan.')
            if next_url:
                return redirect(next_url)
            return redirect('pos_config:merchant_config', lv2_pk=lv2_pk)
    else:
        form = MerchantPOSConfigForm(instance=config)
    return render(request, 'pos_config/merchant_config_form.html', {
        'form': form, 'lv2': lv2, 'entitas': lv2.entitas_bisnis, 'config': config,
        'next_url': next_url,
    })


@login_required
def store_list(request, merchant_pk):
    denied = _check_perm(request.user, 'pos_config_view')
    if denied:
        return denied
    merchant = get_object_or_404(accessible_merchant_qs(request.user), pk=merchant_pk)
    stores = merchant.stores.select_related('entitas_bisnis_lv3').order_by(
        'entitas_bisnis_lv3__nama'
    )
    linked_lv3_ids = stores.values_list('entitas_bisnis_lv3_id', flat=True)
    unlinked = merchant.entitas_bisnis_lv2.children_lv3.exclude(
        pk__in=linked_lv3_ids
    ).order_by('nama')
    return render(request, 'pos_config/store_list.html', {
        'merchant': merchant, 'stores': stores, 'unlinked_branches': unlinked,
    })


@login_required
def store_form(request, merchant_pk, lv3_pk):
    """POS configuration for a branch (EntitasBisnis level 3)."""
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    merchant = get_object_or_404(accessible_merchant_qs(request.user), pk=merchant_pk)
    lv3 = get_object_or_404(
        EntitasBisnisLv3.objects.select_related('parent_lv2'),
        pk=lv3_pk,
        parent_lv2=merchant.entitas_bisnis_lv2,
    )
    store, _ = StorePOSConfig.objects.get_or_create(
        entitas_bisnis_lv3=lv3, defaults={'merchant_config': merchant}
    )
    next_url = _safe_next(request)
    if request.method == 'POST':
        form = StorePOSConfigForm(request.POST, request.FILES, instance=store)
        if form.is_valid():
            form.save()
            messages.success(request, f'Konfigurasi cabang {lv3.nama} disimpan.')
            if next_url:
                return redirect(next_url)
            return redirect('pos_config:store_list', merchant_pk=merchant_pk)
    else:
        form = StorePOSConfigForm(instance=store)
    return render(request, 'pos_config/store_form.html', {
        'form': form, 'merchant': merchant, 'store': store, 'lv3': lv3,
        'next_url': next_url,
    })


@login_required
def payment_method_list(request, store_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    store = get_object_or_404(accessible_store_qs(request.user), pk=store_pk)
    form = PaymentMethodForm()
    if request.method == 'POST':
        form = PaymentMethodForm(request.POST)
        if form.is_valid():
            pm = form.save(commit=False)
            pm.merchant_config = store.merchant_config
            pm.store = store
            pm.save()
            messages.success(request, 'Metode pembayaran ditambahkan.')
            return redirect('pos_config:payment_method_list', store_pk=store_pk)
    return render(request, 'pos_config/payment_method_list.html', {
        'store': store,
        'methods': store.payment_methods.order_by('display_order'),
        'form': form,
    })


@login_required
def shift_list(request, store_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    store = get_object_or_404(accessible_store_qs(request.user), pk=store_pk)
    form = WorkShiftForm()
    if request.method == 'POST':
        form = WorkShiftForm(request.POST)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.store = store
            shift.save()
            messages.success(request, 'Shift kerja ditambahkan.')
            return redirect('pos_config:shift_list', store_pk=store_pk)
    return render(request, 'pos_config/shift_list.html', {
        'store': store, 'shifts': store.shifts.order_by('start_time'), 'form': form,
    })
