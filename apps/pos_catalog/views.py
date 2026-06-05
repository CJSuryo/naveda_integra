from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from apps.accounts.views import _check_perm
from pos_config.models import MerchantPOSConfig
from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase
from apps.inventory.models import InventoryRecord
from .models import ModifierGroup, ModifierOption, CatalogItem, CatalogItemLog
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


@login_required
def catalog_list(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    return render(request, 'pos_catalog/catalog_list.html', {'eb': eb})


@login_required
def catalog_items_ajax(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return JsonResponse({'error': 'forbidden'}, status=403)
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    tipe_item = request.GET.get('tipe_item', '')
    if not tipe_item:
        return JsonResponse({'html': ''})

    items = (
        ItemMasterPurchase.objects
        .filter(tipe_item=tipe_item, inventory_records__entitas_bisnis=eb)
        .distinct()
        .order_by('nama')
    )
    catalog_map = {
        ci.item_id: ci
        for ci in CatalogItem.objects.filter(entitas_bisnis=eb, item__in=items)
        .select_related('item')
    }
    rows = [{'item': item, 'catalog_item': catalog_map.get(item.pk)} for item in items]
    html = render_to_string(
        'pos_catalog/_catalog_rows.html',
        {'rows': rows, 'eb': eb},
        request=request,
    )
    return JsonResponse({'html': html})


@login_required
def catalog_upsert(request, eb_pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return JsonResponse({'error': 'forbidden'}, status=403)
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    item_id = request.POST.get('item_id')
    item = get_object_or_404(ItemMasterPurchase, pk=item_id)

    catalog_item, created = CatalogItem.objects.get_or_create(
        entitas_bisnis=eb, item=item,
        defaults={'selling_price': Decimal('0')},
    )

    TRACKED = ['selling_price', 'display_name', 'display_order', 'is_active']
    old_values = {f: str(getattr(catalog_item, f)) for f in TRACKED}

    try:
        catalog_item.selling_price = Decimal(request.POST.get('selling_price', '0'))
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Invalid selling_price'}, status=400)

    catalog_item.display_name = request.POST.get('display_name', '')

    try:
        catalog_item.display_order = int(request.POST.get('display_order', catalog_item.display_order))
    except (ValueError, TypeError):
        pass

    catalog_item.is_active = request.POST.get('is_active', 'true').lower() == 'true'

    if 'product_image' in request.FILES:
        catalog_item.product_image = request.FILES['product_image']

    logs = []
    if not created:
        for field in TRACKED:
            new_val = str(getattr(catalog_item, field))
            if old_values[field] != new_val:
                logs.append(CatalogItemLog(
                    catalog_item=catalog_item,
                    field_name=field,
                    old_value=old_values[field],
                    new_value=new_val,
                    changed_by=request.user,
                ))
        if 'product_image' in request.FILES:
            logs.append(CatalogItemLog(
                catalog_item=catalog_item,
                field_name='product_image',
                old_value='(previous)',
                new_value=request.FILES['product_image'].name,
                changed_by=request.user,
            ))

    catalog_item.save()
    if logs:
        CatalogItemLog.objects.bulk_create(logs)

    return JsonResponse({
        'success': True,
        'item': {
            'id': catalog_item.pk,
            'display_name': catalog_item.display_name or catalog_item.item.nama,
            'selling_price': str(catalog_item.selling_price),
            'is_active': catalog_item.is_active,
            'display_order': catalog_item.display_order,
            'image_url': catalog_item.product_image.url if catalog_item.product_image else '',
        },
    })


@login_required
def catalog_logs(request, eb_pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied
    eb = get_object_or_404(EntitasBisnis, pk=eb_pk)
    q = request.GET.get('q', '').strip()
    logs_qs = (
        CatalogItemLog.objects
        .filter(catalog_item__entitas_bisnis=eb)
        .select_related('catalog_item__item', 'changed_by')
        .order_by('-changed_at')
    )
    if q:
        logs_qs = logs_qs.filter(catalog_item__item__nama__icontains=q)
    paginator = Paginator(logs_qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'pos_catalog/catalog_logs.html', {
        'eb': eb, 'page': page, 'q': q,
    })
