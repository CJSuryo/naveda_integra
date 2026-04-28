from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UtangHeaderForm, UtangPembayaranForm
from .models import UtangHeader
from .services import (
    create_manual_utang, create_utang_for_purchase,
    create_utang_payment, reverse_utang_header,
)


@login_required
def utang_list(request: HttpRequest) -> HttpResponse:
    utangs = UtangHeader.objects.select_related('entitas_bisnis').order_by('-tanggal', '-created_at')
    return render(request, 'utang/list.html', {'utangs': utangs})


@login_required
def utang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(
        UtangHeader.objects.select_related('entitas_bisnis').prefetch_related(
            'details__purchase_item__item', 'pembayaran__coa_account',
        ),
        pk=pk,
    )
    payment_form = UtangPembayaranForm(initial={'tanggal': utang.tanggal})
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': payment_form})


@login_required
def utang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST)
        if form.is_valid():
            utang = create_manual_utang(**form.cleaned_data)
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dibuat.')
            return redirect('utang:detail', pk=utang.pk)
    else:
        form = UtangHeaderForm()
    return render(request, 'utang/form.html', {'form': form, 'title': 'Tambah Utang'})


@login_required
def utang_update(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if request.method == 'POST':
        form = UtangHeaderForm(request.POST, instance=utang)
        if form.is_valid():
            form.save()
            dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil diperbarui.')
            return redirect('utang:detail', pk=utang.pk)
    else:
        form = UtangHeaderForm(instance=utang)
    return render(request, 'utang/form.html', {'form': form, 'title': 'Edit Utang'})


@login_required
def utang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if request.method == 'POST':
        reverse_utang_header(utang, request.user)
        dj_messages.success(request, f'Utang {utang.nomor_utang} berhasil dihapus.')
        return redirect('utang:list')
    return render(request, 'utang/delete.html', {'utang': utang})


@login_required
def utang_pay(request: HttpRequest, pk: int) -> HttpResponse:
    utang = get_object_or_404(UtangHeader, pk=pk)
    if request.method != 'POST':
        return redirect('utang:detail', pk=pk)

    form = UtangPembayaranForm(request.POST)
    if form.is_valid():
        try:
            create_utang_payment(utang, **form.cleaned_data)
            dj_messages.success(request, f'Pembayaran untuk {utang.nomor_utang} berhasil dicatat.')
            return redirect('utang:detail', pk=pk)
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(request, 'utang/detail.html', {'utang': utang, 'payment_form': form})
