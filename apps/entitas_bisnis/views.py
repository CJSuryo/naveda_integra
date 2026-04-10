"""EntitasBisnis views."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TipeEntitasForm, EntitasBisnisForm, CabangEntitasBisnisForm
from .models import TipeEntitas, EntitasBisnis, CabangEntitasBisnis


# ── Tipe Entitas ──────────────────────────────────────────────────────────────

@login_required
def tipe_entitas_list(request: HttpRequest) -> HttpResponse:
    queryset = TipeEntitas.objects.all().order_by('nama')
    return render(request, 'entitas_bisnis/tipe_entitas/list.html', {'object_list': queryset})


@login_required
def tipe_entitas_create(request: HttpRequest) -> HttpResponse:
    form = TipeEntitasForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('entitas_bisnis:tipe_entitas_list')
    return render(request, 'entitas_bisnis/tipe_entitas/form.html', {'form': form, 'title': 'Tambah Tipe Entitas'})


@login_required
def tipe_entitas_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TipeEntitas, pk=pk)
    form = TipeEntitasForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('entitas_bisnis:tipe_entitas_list')
    return render(request, 'entitas_bisnis/tipe_entitas/form.html', {'form': form, 'title': 'Edit Tipe Entitas', 'object': obj})


@login_required
def tipe_entitas_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TipeEntitas, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:tipe_entitas_list')
    return render(request, 'entitas_bisnis/tipe_entitas/confirm_delete.html', {'object': obj})


# ── Entitas Bisnis ────────────────────────────────────────────────────────────

@login_required
def list_view(request: HttpRequest) -> HttpResponse:
    queryset = EntitasBisnis.objects.select_related('tipe_entitas').all().order_by('nama')
    return render(request, 'entitas_bisnis/list.html', {'object_list': queryset})


@login_required
def detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis.objects.select_related('tipe_entitas'), pk=pk)
    cabang_list = obj.cabang_set.all().order_by('nama')
    return render(request, 'entitas_bisnis/detail.html', {'object': obj, 'cabang_list': cabang_list})


@login_required
def create_view(request: HttpRequest) -> HttpResponse:
    form = EntitasBisnisForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('entitas_bisnis:list')
    return render(request, 'entitas_bisnis/form.html', {'form': form, 'title': 'Tambah Entitas Bisnis'})


@login_required
def update_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    form = EntitasBisnisForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('entitas_bisnis:list')
    return render(request, 'entitas_bisnis/form.html', {'form': form, 'title': 'Edit Entitas Bisnis'})


@login_required
def delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:list')
    return render(request, 'entitas_bisnis/confirm_delete.html', {'object': obj})


# ── Cabang Entitas Bisnis ─────────────────────────────────────────────────────

@login_required
def cabang_create(request: HttpRequest, eb_pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    form = CabangEntitasBisnisForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.entitas_bisnis = parent
        obj.save()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    return render(request, 'entitas_bisnis/cabang/form.html', {'form': form, 'parent': parent, 'title': 'Tambah Cabang'})


@login_required
def cabang_update(request: HttpRequest, eb_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    obj = get_object_or_404(CabangEntitasBisnis, pk=pk, entitas_bisnis=parent)
    form = CabangEntitasBisnisForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    return render(request, 'entitas_bisnis/cabang/form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Cabang'})


@login_required
def cabang_delete(request: HttpRequest, eb_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    obj = get_object_or_404(CabangEntitasBisnis, pk=pk, entitas_bisnis=parent)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    return render(request, 'entitas_bisnis/cabang/confirm_delete.html', {'object': obj, 'parent': parent})
