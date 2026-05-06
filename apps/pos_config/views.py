from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from apps.accounts.views import _check_perm
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift, ShiftLog
from .forms import MerchantPOSConfigForm, StorePOSConfigForm, PaymentMethodForm, WorkShiftForm


@login_required
def merchant_config(request, pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    entitas = get_object_or_404(EntitasBisnis, pk=pk)
    config, _ = MerchantPOSConfig.objects.get_or_create(entitas_bisnis=entitas)
    if request.method == 'POST':
        form = MerchantPOSConfigForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Konfigurasi merchant POS disimpan.')
            return redirect('pos_config:merchant_config', pk=pk)
    else:
        form = MerchantPOSConfigForm(instance=config)
    return render(request, 'pos_config/merchant_config_form.html', {
        'form': form, 'entitas': entitas, 'config': config,
    })


@login_required
def store_list(request, merchant_pk):
    denied = _check_perm(request.user, 'pos_config_view')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    stores = merchant.stores.select_related('entitas_bisnis_lv2').order_by('entitas_bisnis_lv2__nama')
    return render(request, 'pos_config/store_list.html', {'merchant': merchant, 'stores': stores})


@login_required
def store_form(request, merchant_pk, lv2_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    lv2 = get_object_or_404(EntitasBisnisLv2, pk=lv2_pk, entitas_bisnis=merchant.entitas_bisnis)
    store, _ = StorePOSConfig.objects.get_or_create(entitas_bisnis_lv2=lv2, defaults={'merchant_config': merchant})
    if request.method == 'POST':
        form = StorePOSConfigForm(request.POST, instance=store)
        if form.is_valid():
            form.save()
            messages.success(request, 'Konfigurasi toko disimpan.')
            return redirect('pos_config:store_list', merchant_pk=merchant_pk)
    else:
        form = StorePOSConfigForm(instance=store)
    return render(request, 'pos_config/store_form.html', {
        'form': form, 'merchant': merchant, 'store': store, 'lv2': lv2,
    })


@login_required
def payment_method_list(request, store_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    store = get_object_or_404(StorePOSConfig, pk=store_pk)
    methods = store.payment_methods.order_by('display_order')
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
        'store': store, 'methods': methods, 'form': form,
    })


@login_required
def shift_list(request, store_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    store = get_object_or_404(StorePOSConfig, pk=store_pk)
    shifts = store.shifts.order_by('start_time')
    return render(request, 'pos_config/shift_list.html', {'store': store, 'shifts': shifts})
