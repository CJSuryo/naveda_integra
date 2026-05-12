from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from apps.accounts.views import _check_perm
from pos_config.models import MerchantPOSConfig
from .models import ModifierGroup, ModifierOption
from .forms import ModifierGroupForm, ModifierOptionForm


@login_required
def modifier_group_list(request, merchant_pk):
    denied = _check_perm(request.user, 'pos_catalog_manage')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    groups = merchant.modifier_groups.prefetch_related('options').order_by('display_order', 'name')
    return render(request, 'pos_catalog/modifier_group_list.html', {'merchant': merchant, 'groups': groups})


@login_required
def modifier_group_form(request, merchant_pk, pk=None):
    denied = _check_perm(request.user, 'pos_catalog_manage')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    group = get_object_or_404(ModifierGroup, pk=pk, merchant_config=merchant) if pk else None
    if request.method == 'POST':
        form = ModifierGroupForm(request.POST, instance=group)
        if form.is_valid():
            mg = form.save(commit=False)
            mg.merchant_config = merchant
            mg.save()
            messages.success(request, 'Grup modifier disimpan.')
            return redirect('pos_catalog:modifier_group_list', merchant_pk=merchant_pk)
    else:
        form = ModifierGroupForm(instance=group)
    return render(request, 'pos_catalog/modifier_group_form.html', {
        'form': form, 'merchant': merchant, 'group': group,
    })


@login_required
def modifier_option_create(request, merchant_pk, group_pk):
    denied = _check_perm(request.user, 'pos_catalog_manage')
    if denied:
        return denied
    group = get_object_or_404(ModifierGroup, pk=group_pk, merchant_config__pk=merchant_pk)
    if request.method == 'POST':
        form = ModifierOptionForm(request.POST)
        if form.is_valid():
            opt = form.save(commit=False)
            opt.group = group
            opt.save()
            messages.success(request, f'Opsi "{opt.name}" ditambahkan.')
    return redirect('pos_catalog:modifier_group_list', merchant_pk=merchant_pk)
