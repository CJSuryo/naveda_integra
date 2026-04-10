"""EntitasBisnis views."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import EntitasBisnisForm
from .models import EntitasBisnis


@login_required
def list_view(request: HttpRequest) -> HttpResponse:
    queryset = EntitasBisnis.objects.all().order_by('nama')
    return render(request, 'entitas_bisnis/list.html', {'object_list': queryset})


@login_required
def detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    return render(request, 'entitas_bisnis/detail.html', {'object': obj})


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
