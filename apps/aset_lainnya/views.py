"""Aset Lainnya views — CRUD for AsetLainnyaRecord."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .forms import AsetLainnyaRecordForm
from .models import AsetLainnyaRecord


@login_required
def aset_lainnya_list(request: HttpRequest) -> HttpResponse:
    """List all other asset records with optional filters."""
    qs = AsetLainnyaRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')

    if tanggal_dari:
        qs = qs.filter(tanggal_perolehan__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal_perolehan__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)

    return render(request, 'aset_lainnya/aset_lainnya_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.filter(tipe_item='ALL').order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
    })


@login_required
def aset_lainnya_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show other asset record detail."""
    record = get_object_or_404(
        AsetLainnyaRecord.objects.select_related('item', 'entitas_bisnis', 'purchase_item'),
        pk=pk,
    )
    return render(request, 'aset_lainnya/aset_lainnya_detail.html', {'record': record})


@login_required
def aset_lainnya_create(request: HttpRequest) -> HttpResponse:
    """Create a new other asset record."""
    if request.method == 'POST':
        form = AsetLainnyaRecordForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Aset lainnya {record.aset_number} berhasil dibuat.')
            return redirect('aset_lainnya:detail', pk=record.pk)
    else:
        form = AsetLainnyaRecordForm()
    return render(request, 'aset_lainnya/aset_lainnya_form.html', {'form': form, 'title': 'Tambah Aset Lainnya'})


@login_required
def aset_lainnya_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing other asset record."""
    record = get_object_or_404(AsetLainnyaRecord, pk=pk)
    if request.method == 'POST':
        form = AsetLainnyaRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, f'Aset lainnya {record.aset_number} berhasil diperbarui.')
            return redirect('aset_lainnya:detail', pk=record.pk)
    else:
        form = AsetLainnyaRecordForm(instance=record)
    return render(request, 'aset_lainnya/aset_lainnya_form.html', {
        'form': form,
        'record': record,
        'title': f'Edit {record.aset_number}',
    })


@login_required
def aset_lainnya_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete an other asset record."""
    record = get_object_or_404(AsetLainnyaRecord, pk=pk)
    if request.method == 'POST':
        number = record.aset_number
        record.delete()
        messages.success(request, f'Aset lainnya {number} berhasil dihapus.')
        return redirect('aset_lainnya:list')
    return render(request, 'aset_lainnya/aset_lainnya_confirm_delete.html', {'record': record})
