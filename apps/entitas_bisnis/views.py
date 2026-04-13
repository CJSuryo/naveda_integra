"""EntitasBisnis views."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TipeEntitasForm, EntitasBisnisForm, EntitasBisnisLv2Form, EntitasBisnisLv3Form
from .models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3


def _is_ajax(request: HttpRequest) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _ajax_success() -> JsonResponse:
    return JsonResponse({'success': True})


def _ajax_error(form) -> JsonResponse:
    return JsonResponse({
        'success': False,
        'errors': {k: [str(e) for e in v] for k, v in form.errors.items()},
    })


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


# ── Entitas Bisnis (Level 1) ─────────────────────────────────────────────────

@login_required
def list_view(request: HttpRequest) -> HttpResponse:
    lv1_list = (
        EntitasBisnis.objects
        .select_related('tipe_entitas')
        .prefetch_related('children_lv2__children_lv3')
        .all()
        .order_by('nama')
    )
    add_lv1_form = EntitasBisnisForm()
    edit_lv1_form = EntitasBisnisForm()
    add_lv2_form = EntitasBisnisLv2Form()
    edit_lv2_form = EntitasBisnisLv2Form()
    add_lv3_form = EntitasBisnisLv3Form()
    edit_lv3_form = EntitasBisnisLv3Form()
    tipe_entitas_list = TipeEntitas.objects.all().order_by('nama')
    return render(request, 'entitas_bisnis/list.html', {
        'lv1_list': lv1_list,
        'object_list': lv1_list,  # backward compat
        'add_lv1_form': add_lv1_form,
        'edit_lv1_form': edit_lv1_form,
        'add_lv2_form': add_lv2_form,
        'edit_lv2_form': edit_lv2_form,
        'add_lv3_form': add_lv3_form,
        'edit_lv3_form': edit_lv3_form,
        'tipe_entitas_list': tipe_entitas_list,
    })


@login_required
def detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis.objects.select_related('tipe_entitas'), pk=pk)
    lv2_list = obj.children_lv2.all().order_by('nama')
    return render(request, 'entitas_bisnis/detail.html', {'object': obj, 'lv2_list': lv2_list})


@login_required
def create_view(request: HttpRequest) -> HttpResponse:
    form = EntitasBisnisForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:list')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/form.html', {'form': form, 'title': 'Tambah Entitas Bisnis Level 1'})


@login_required
def update_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    form = EntitasBisnisForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:list')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/form.html', {'form': form, 'title': 'Edit Entitas Bisnis Level 1'})


@login_required
def delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:list')
    return render(request, 'entitas_bisnis/confirm_delete.html', {'object': obj})


# ── Entitas Bisnis Level 2 ───────────────────────────────────────────────────

@login_required
def lv2_create(request: HttpRequest, eb_pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    form = EntitasBisnisLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.entitas_bisnis = parent
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/lv2/form.html', {'form': form, 'parent': parent, 'title': 'Tambah Entitas Bisnis Level 2'})


@login_required
def lv2_update(request: HttpRequest, eb_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    obj = get_object_or_404(EntitasBisnisLv2, pk=pk, entitas_bisnis=parent)
    form = EntitasBisnisLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/lv2/form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Entitas Bisnis Level 2'})


@login_required
def lv2_delete(request: HttpRequest, eb_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    obj = get_object_or_404(EntitasBisnisLv2, pk=pk, entitas_bisnis=parent)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:detail', pk=eb_pk)
    return render(request, 'entitas_bisnis/lv2/confirm_delete.html', {'object': obj, 'parent': parent})


@login_required
def lv2_detail(request: HttpRequest, eb_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EntitasBisnis, pk=eb_pk)
    obj = get_object_or_404(EntitasBisnisLv2.objects.select_related('entitas_bisnis'), pk=pk, entitas_bisnis=parent)
    lv3_list = obj.children_lv3.all().order_by('nama')
    return render(request, 'entitas_bisnis/lv2/detail.html', {'object': obj, 'parent': parent, 'lv3_list': lv3_list})


# ── Entitas Bisnis Level 3 ───────────────────────────────────────────────────

@login_required
def lv3_create(request: HttpRequest, eb_pk: int, lv2_pk: int) -> HttpResponse:
    parent_lv1 = get_object_or_404(EntitasBisnis, pk=eb_pk)
    parent_lv2 = get_object_or_404(EntitasBisnisLv2, pk=lv2_pk, entitas_bisnis=parent_lv1)
    form = EntitasBisnisLv3Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.parent_lv2 = parent_lv2
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:lv2_detail', eb_pk=eb_pk, pk=lv2_pk)
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/lv3/form.html', {'form': form, 'parent_lv2': parent_lv2, 'parent_lv1': parent_lv1, 'title': 'Tambah Entitas Bisnis Level 3'})


@login_required
def lv3_update(request: HttpRequest, eb_pk: int, lv2_pk: int, pk: int) -> HttpResponse:
    parent_lv1 = get_object_or_404(EntitasBisnis, pk=eb_pk)
    parent_lv2 = get_object_or_404(EntitasBisnisLv2, pk=lv2_pk, entitas_bisnis=parent_lv1)
    obj = get_object_or_404(EntitasBisnisLv3, pk=pk, parent_lv2=parent_lv2)
    form = EntitasBisnisLv3Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('entitas_bisnis:lv2_detail', eb_pk=eb_pk, pk=lv2_pk)
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'entitas_bisnis/lv3/form.html', {'form': form, 'parent_lv2': parent_lv2, 'parent_lv1': parent_lv1, 'object': obj, 'title': 'Edit Entitas Bisnis Level 3'})


@login_required
def lv3_delete(request: HttpRequest, eb_pk: int, lv2_pk: int, pk: int) -> HttpResponse:
    parent_lv1 = get_object_or_404(EntitasBisnis, pk=eb_pk)
    parent_lv2 = get_object_or_404(EntitasBisnisLv2, pk=lv2_pk, entitas_bisnis=parent_lv1)
    obj = get_object_or_404(EntitasBisnisLv3, pk=pk, parent_lv2=parent_lv2)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:lv2_detail', eb_pk=eb_pk, pk=lv2_pk)
    return render(request, 'entitas_bisnis/lv3/confirm_delete.html', {'object': obj, 'parent_lv2': parent_lv2, 'parent_lv1': parent_lv1})
