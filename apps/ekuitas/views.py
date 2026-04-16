"""Ekuitas views — CRUD for ModalDisetor."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis

from .forms import ModalDisetorForm
from .models import ModalDisetor


@login_required
def ekuitas_list(request: HttpRequest) -> HttpResponse:
    """List all modal disetor records with optional filters."""
    qs = ModalDisetor.objects.select_related('entitas_bisnis').all()

    eb_filter = request.GET.get('entitas_bisnis', '')
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)

    return render(request, 'ekuitas/ekuitas_list.html', {
        'records': qs,
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'eb_filter': eb_filter,
    })


@login_required
def ekuitas_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show modal disetor detail."""
    record = get_object_or_404(
        ModalDisetor.objects.select_related('entitas_bisnis'),
        pk=pk,
    )
    return render(request, 'ekuitas/ekuitas_detail.html', {'record': record})


@login_required
def ekuitas_create(request: HttpRequest) -> HttpResponse:
    """Create a new modal disetor record."""
    if request.method == 'POST':
        form = ModalDisetorForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Modal disetor {record.nama_pemilik} berhasil dibuat.')
            return redirect('ekuitas:detail', pk=record.pk)
    else:
        form = ModalDisetorForm()
    return render(request, 'ekuitas/ekuitas_form.html', {'form': form, 'title': 'Tambah Modal Disetor'})


@login_required
def ekuitas_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing modal disetor record."""
    record = get_object_or_404(ModalDisetor, pk=pk)
    if request.method == 'POST':
        form = ModalDisetorForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, f'Modal disetor {record.nama_pemilik} berhasil diperbarui.')
            return redirect('ekuitas:detail', pk=record.pk)
    else:
        form = ModalDisetorForm(instance=record)
    return render(request, 'ekuitas/ekuitas_form.html', {
        'form': form,
        'record': record,
        'title': f'Edit Modal Disetor — {record.nama_pemilik}',
    })


@login_required
def ekuitas_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a modal disetor record."""
    record = get_object_or_404(ModalDisetor, pk=pk)
    if request.method == 'POST':
        nama = record.nama_pemilik
        record.delete()
        messages.success(request, f'Modal disetor {nama} berhasil dihapus.')
        return redirect('ekuitas:list')
    return redirect('ekuitas:list')
