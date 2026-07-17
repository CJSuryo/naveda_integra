import itertools

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ItemUOMForm, UnitOfMeasureForm
from .models import ItemUOM, UnitOfMeasure


DIMENSION_ICONS = {
    'count': 'hash',
    'weight': 'scale',
    'volume': 'flask-conical',
    'length': 'ruler',
    'area': 'square',
}


def _base_by_dimension():
    return {
        u.dimension: u.kode
        for u in UnitOfMeasure.objects.filter(is_base=True)
    }


def _item_stock_uom_map():
    from apps.purchase.models import ItemMasterPurchase
    return {
        str(i.pk): (i.stock_uom.kode if i.stock_uom_id else '')
        for i in ItemMasterPurchase.objects.select_related('stock_uom').filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'])
    }


@login_required
def unit_list(request):
    units = list(UnitOfMeasure.objects.for_dropdown())
    groups = []
    for dimension, dim_units in itertools.groupby(units, key=lambda u: u.dimension):
        dim_units = list(dim_units)
        base_unit = next((u for u in dim_units if u.is_base), None)
        groups.append({
            'dimension_label': dim_units[0].get_dimension_display(),
            'icon': DIMENSION_ICONS.get(dimension, ''),
            'units': dim_units,
            'base_unit': base_unit,
        })
    return render(request, 'uom/unit_list.html', {'groups': groups, 'title': 'Master Satuan'})


@login_required
def unit_create(request):
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('uom:list')
    else:
        form = UnitOfMeasureForm()
    return render(request, 'uom/unit_form.html',
                  {'form': form, 'is_edit': False, 'title': 'Satuan Baru',
                   'base_by_dimension': _base_by_dimension()})


@login_required
def unit_update(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    if request.method == 'POST':
        form = UnitOfMeasureForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            return redirect('uom:list')
    else:
        form = UnitOfMeasureForm(instance=unit)
    return render(request, 'uom/unit_form.html',
                  {'form': form, 'is_edit': True, 'unit': unit, 'title': 'Edit Satuan',
                   'base_by_dimension': _base_by_dimension()})


@login_required
def conversion_list(request):
    item_filter = request.GET.get('item', '')
    qs = ItemUOM.objects.select_related('item', 'uom').order_by('item__nama', 'uom__kode')
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    from apps.purchase.models import ItemMasterPurchase
    items = ItemMasterPurchase.objects.filter(
        tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB']).order_by('item_id')
    return render(request, 'uom/item_conversion_list.html', {
        'conversions': qs, 'items': items, 'item_filter': item_filter,
        'title': 'Konversi Satuan Item',
    })


@login_required
def conversion_create(request):
    if request.method == 'POST':
        form = ItemUOMForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('uom:conversion_list')
    else:
        form = ItemUOMForm()
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Konversi Baru', 'is_edit': False,
                   'item_stock_uom_map': _item_stock_uom_map()})


@login_required
def conversion_update(request, pk):
    obj = get_object_or_404(ItemUOM, pk=pk)
    if request.method == 'POST':
        form = ItemUOMForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            return redirect('uom:conversion_list')
    else:
        form = ItemUOMForm(instance=obj)
    return render(request, 'uom/item_conversion_form.html',
                  {'form': form, 'title': 'Edit Konversi', 'is_edit': True,
                   'item_stock_uom_map': _item_stock_uom_map()})


@login_required
def conversion_delete(request, pk):
    obj = get_object_or_404(ItemUOM, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('uom:conversion_list')
    return render(request, 'uom/item_conversion_form.html',
                  {'delete_obj': obj, 'title': 'Hapus Konversi'})
