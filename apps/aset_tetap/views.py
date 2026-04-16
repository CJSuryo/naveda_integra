"""Aset Tetap views — CRUD for AsetTetapRecord."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .forms import AsetTetapRecordForm
from .models import AsetTetapRecord


@login_required
def aset_tetap_list(request: HttpRequest) -> HttpResponse:
    """List all fixed asset records with optional filters."""
    qs = AsetTetapRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')
    kondisi_filter = request.GET.get('kondisi', '')

    if tanggal_dari:
        qs = qs.filter(tanggal_perolehan__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal_perolehan__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)
    if kondisi_filter:
        qs = qs.filter(kondisi=kondisi_filter)

    return render(request, 'aset_tetap/aset_tetap_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.filter(tipe_item='ATP').order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'kondisi_choices': AsetTetapRecord.KONDISI_CHOICES,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
        'kondisi_filter': kondisi_filter,
    })


@login_required
def aset_tetap_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show fixed asset record detail."""
    record = get_object_or_404(
        AsetTetapRecord.objects.select_related('item', 'entitas_bisnis', 'purchase_item'),
        pk=pk,
    )
    return render(request, 'aset_tetap/aset_tetap_detail.html', {'record': record})


@login_required
def aset_tetap_create(request: HttpRequest) -> HttpResponse:
    """Create a new fixed asset record."""
    if request.method == 'POST':
        form = AsetTetapRecordForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Aset tetap {record.aset_number} berhasil dibuat.')
            return redirect('aset_tetap:detail', pk=record.pk)
    else:
        form = AsetTetapRecordForm()
    return render(request, 'aset_tetap/aset_tetap_form.html', {'form': form, 'title': 'Tambah Aset Tetap'})


@login_required
def aset_tetap_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing fixed asset record."""
    record = get_object_or_404(AsetTetapRecord, pk=pk)
    if request.method == 'POST':
        form = AsetTetapRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, f'Aset tetap {record.aset_number} berhasil diperbarui.')
            return redirect('aset_tetap:detail', pk=record.pk)
    else:
        form = AsetTetapRecordForm(instance=record)
    return render(request, 'aset_tetap/aset_tetap_form.html', {
        'form': form,
        'record': record,
        'title': f'Edit {record.aset_number}',
    })


@login_required
def aset_tetap_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a fixed asset record."""
    record = get_object_or_404(AsetTetapRecord, pk=pk)
    if request.method == 'POST':
        number = record.aset_number
        record.delete()
        messages.success(request, f'Aset tetap {number} berhasil dihapus.')
        return redirect('aset_tetap:list')
    return render(request, 'aset_tetap/aset_tetap_confirm_delete.html', {'record': record})
