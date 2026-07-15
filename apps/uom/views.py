from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UnitOfMeasureForm
from .models import UnitOfMeasure


@login_required
def unit_list(request):
    units = UnitOfMeasure.objects.all().order_by('dimension', 'kode')
    return render(request, 'uom/unit_list.html', {'units': units, 'title': 'Master Satuan'})


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
                  {'form': form, 'is_edit': False, 'title': 'Satuan Baru'})


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
                  {'form': form, 'is_edit': True, 'unit': unit, 'title': 'Edit Satuan'})
