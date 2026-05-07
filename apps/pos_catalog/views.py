from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from apps.accounts.views import _check_perm
from pos_config.models import MerchantPOSConfig
from .models import POSCategory, POSProduct, ModifierGroup, ModifierOption, ProductModifierGroup
from .forms import POSCategoryForm, POSProductForm, ModifierGroupForm, ModifierOptionForm


@login_required
def product_list(request, merchant_pk):
    denied = _check_perm(request.user, 'pos_catalog_view')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    products = merchant.products.select_related('category', 'item_master').order_by('display_order', 'pos_name')
    return render(request, 'pos_catalog/product_list.html', {'merchant': merchant, 'products': products})


@login_required
def product_create(request, merchant_pk):
    denied = _check_perm(request.user, 'pos_catalog_manage')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    if request.method == 'POST':
        form = POSProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.merchant_config = merchant
            product.save()
            group_ids = request.POST.getlist('modifier_groups')
            for i, gid in enumerate(group_ids):
                ProductModifierGroup.objects.get_or_create(
                    product=product,
                    modifier_group_id=int(gid),
                    defaults={'display_order': i},
                )
            messages.success(request, f'Produk "{product.pos_name}" berhasil ditambahkan.')
            return redirect('pos_catalog:product_list', merchant_pk=merchant_pk)
    else:
        form = POSProductForm()
    modifier_groups = merchant.modifier_groups.filter(is_active=True)
    return render(request, 'pos_catalog/product_form.html', {
        'form': form, 'merchant': merchant, 'modifier_groups': modifier_groups,
        'selected_group_ids': [],
    })


@login_required
def product_edit(request, merchant_pk, pk):
    denied = _check_perm(request.user, 'pos_catalog_manage')
    if denied:
        return denied
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_pk)
    product = get_object_or_404(POSProduct, pk=pk, merchant_config=merchant)
    selected_group_ids = list(product.modifier_links.values_list('modifier_group_id', flat=True))
    if request.method == 'POST':
        form = POSProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            new_group_ids = [int(gid) for gid in request.POST.getlist('modifier_groups')]
            product.modifier_links.exclude(modifier_group_id__in=new_group_ids).delete()
            for i, gid in enumerate(new_group_ids):
                ProductModifierGroup.objects.update_or_create(
                    product=product, modifier_group_id=gid,
                    defaults={'display_order': i},
                )
            messages.success(request, 'Produk diperbarui.')
            return redirect('pos_catalog:product_list', merchant_pk=merchant_pk)
    else:
        form = POSProductForm(instance=product)
    modifier_groups = merchant.modifier_groups.filter(is_active=True)
    return render(request, 'pos_catalog/product_form.html', {
        'form': form, 'merchant': merchant, 'product': product,
        'modifier_groups': modifier_groups, 'selected_group_ids': selected_group_ids,
    })


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
