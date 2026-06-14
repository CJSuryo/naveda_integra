"""Master data views."""
import csv
import io
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

logger = logging.getLogger(__name__)

from .forms import (
    AsetLv1Form, AsetLv2Form,
    KewajibanLv1Form, KewajibanLv2Form,
    EkuitasLv1Form, EkuitasLv2Form,
    PendapatanLv1Form, PendapatanLv2Form,
    BebanLv1Form, BebanLv2Form,
)
from .models import (
    AsetLv1, AsetLv2,
    KewajibanLv1, KewajibanLv2,
    EkuitasLv1, EkuitasLv2,
    PendapatanLv1, PendapatanLv2,
    BebanLv1, BebanLv2,
    TipeTransaksi,
    Bukti,
)


# ── AJAX helpers ──────────────────────────────────────────────────────────────

def _is_ajax(request: HttpRequest) -> bool:
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _ajax_success() -> JsonResponse:
    return JsonResponse({'success': True})


def _ajax_error(form) -> JsonResponse:
    return JsonResponse({
        'success': False,
        'errors': {k: [str(e) for e in v] for k, v in form.errors.items()},
    })


# ── Kode auto-generation helpers ──────────────────────────────────────────────

def _next_lv1_kode(category_model, prefix: str) -> str:
    """Find max N in kodes '{prefix}.N' and return '{prefix}.{N+1}'."""
    max_n = 0
    for kode in category_model.objects.values_list('kode', flat=True):
        parts = kode.rsplit('.', 1)
        if len(parts) == 2 and parts[0] == prefix:
            try:
                n = int(parts[1])
                max_n = max(max_n, n)
            except ValueError:
                pass
    return f'{prefix}.{max_n + 1}'


def _next_lv2_kode(category_model, parent_kode: str) -> str:
    """Find max M in kodes '{parent_kode}.M' and return '{parent_kode}.{M+1}'."""
    max_m = 0
    prefix = parent_kode + '.'
    for kode in category_model.objects.filter(kode__startswith=prefix).values_list('kode', flat=True):
        rest = kode[len(prefix):]
        if '.' not in rest:
            try:
                m = int(rest)
                max_m = max(max_m, m)
            except ValueError:
                pass
    return f'{parent_kode}.{max_m + 1}'


def _cascade_lv2_kode(lv2_model, lv2_parent_field: str, lv1_instance, old_lv1_kode: str, new_lv1_kode: str) -> None:
    """Update all lv2 children kodes when their parent lv1 kode changes."""
    old_prefix = old_lv1_kode + '.'
    new_prefix = new_lv1_kode + '.'
    children = lv2_model.objects.filter(**{lv2_parent_field: lv1_instance})
    for child in children:
        if child.kode.startswith(old_prefix):
            rest = child.kode[len(old_prefix):]
            child.kode = new_prefix + rest
            child.save()  # triggers the post_save signal that syncs the Akun record


def _renumber_lv1_kode(lv1_model, lv2_model, lv2_parent_field: str, instance, old_kode: str, new_kode: str) -> None:
    """Renumber lv1 siblings when kode changes, and cascade lv2 children."""
    old_parts = old_kode.rsplit('.', 1)
    new_parts = new_kode.rsplit('.', 1)
    if len(old_parts) != 2 or len(new_parts) != 2 or old_parts[0] != new_parts[0]:
        return
    try:
        old_n = int(old_parts[1])
        new_n = int(new_parts[1])
    except ValueError:
        return
    if old_n == new_n:
        return

    prefix = old_parts[0]

    with transaction.atomic():
        all_siblings = list(lv1_model.objects.exclude(pk=instance.pk).select_for_update())
        siblings_in_range = {}
        for s in all_siblings:
            parts = s.kode.rsplit('.', 1)
            if len(parts) == 2 and parts[0] == prefix:
                try:
                    n = int(parts[1])
                    if new_n < old_n and new_n <= n <= old_n - 1:
                        siblings_in_range[n] = s
                    elif new_n > old_n and old_n + 1 <= n <= new_n:
                        siblings_in_range[n] = s
                except ValueError:
                    pass

        # Free the instance's current slot before shifting siblings into it.
        lv1_model.objects.filter(pk=instance.pk).update(kode=f'_tmp_{instance.pk}')

        if new_n < old_n:
            for n in sorted(siblings_in_range.keys(), reverse=True):
                s = siblings_in_range[n]
                old_s_kode = s.kode
                new_s_kode = f'{prefix}.{n + 1}'
                s.kode = new_s_kode
                s.save()
                _cascade_lv2_kode(lv2_model, lv2_parent_field, s, old_s_kode, new_s_kode)
        else:
            for n in sorted(siblings_in_range.keys()):
                s = siblings_in_range[n]
                old_s_kode = s.kode
                new_s_kode = f'{prefix}.{n - 1}'
                s.kode = new_s_kode
                s.save()
                _cascade_lv2_kode(lv2_model, lv2_parent_field, s, old_s_kode, new_s_kode)

        old_kode_actual = instance.kode
        instance.kode = new_kode
        instance.save()
        _cascade_lv2_kode(lv2_model, lv2_parent_field, instance, old_kode_actual, new_kode)


def _renumber_lv2_kode(lv2_model, lv2_parent_field: str, instance, old_kode: str, new_kode: str) -> None:
    """Renumber lv2 siblings when kode changes."""
    old_parts = old_kode.rsplit('.', 1)
    new_parts = new_kode.rsplit('.', 1)
    if len(old_parts) != 2 or len(new_parts) != 2 or old_parts[0] != new_parts[0]:
        return
    try:
        old_m = int(old_parts[1])
        new_m = int(new_parts[1])
    except ValueError:
        return
    if old_m == new_m:
        return

    prefix = old_parts[0]
    parent_val = getattr(instance, lv2_parent_field)

    with transaction.atomic():
        siblings = list(lv2_model.objects.exclude(pk=instance.pk).filter(
            **{lv2_parent_field: parent_val}
        ).select_for_update())

        siblings_in_range = {}
        for s in siblings:
            parts = s.kode.rsplit('.', 1)
            if len(parts) == 2 and parts[0] == prefix:
                try:
                    m = int(parts[1])
                    if new_m < old_m and new_m <= m <= old_m - 1:
                        siblings_in_range[m] = s
                    elif new_m > old_m and old_m + 1 <= m <= new_m:
                        siblings_in_range[m] = s
                except ValueError:
                    pass

        # Free the instance's current slot before shifting siblings into it.
        lv2_model.objects.filter(pk=instance.pk).update(kode=f'_tmp_{instance.pk}')

        if new_m < old_m:
            for m in sorted(siblings_in_range.keys(), reverse=True):
                s = siblings_in_range[m]
                s.kode = f'{prefix}.{m + 1}'
                s.save()
        else:
            for m in sorted(siblings_in_range.keys()):
                s = siblings_in_range[m]
                s.kode = f'{prefix}.{m - 1}'
                s.save()

        instance.kode = new_kode
        instance.save()


# ── Aset Level 1 ──────────────────────────────────────────────────────────────

@login_required
def aset_lv1_create(request: HttpRequest) -> HttpResponse:
    form = AsetLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.kode:
            obj.kode = _next_lv1_kode(AsetLv1, '1')
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv1_form.html', {'form': form, 'title': 'Tambah Aset Level 1'})


@login_required
def aset_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(AsetLv1, pk=pk)
    old_kode = obj.kode
    form = AsetLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            form.instance.kode = old_kode  # revert temporarily
            form.save(commit=False)
            _renumber_lv1_kode(AsetLv1, AsetLv2, 'aset', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv1_form.html', {'form': form, 'title': 'Edit Aset Level 1', 'object': obj})


@login_required
def aset_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(AsetLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


@login_required
def aset_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    form = AsetLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.aset = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(AsetLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Aset Level 2'})


@login_required
def aset_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    obj = get_object_or_404(AsetLv2, pk=pk, aset=parent)
    old_kode = obj.kode
    form = AsetLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(AsetLv2, 'aset', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Aset Level 2'})


@login_required
def aset_lv2_delete(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    obj = get_object_or_404(AsetLv2, pk=pk, aset=parent)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena akun ini masih digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


# ── Kewajiban Level 1 ─────────────────────────────────────────────────────────

@login_required
def kewajiban_lv1_create(request: HttpRequest) -> HttpResponse:
    form = KewajibanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.kode:
            obj.kode = _next_lv1_kode(KewajibanLv1, '2')
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/kewajiban/lv1_form.html', {'form': form, 'title': 'Tambah Kewajiban Level 1'})


@login_required
def kewajiban_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KewajibanLv1, pk=pk)
    old_kode = obj.kode
    form = KewajibanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            form.instance.kode = old_kode
            form.save(commit=False)
            _renumber_lv1_kode(KewajibanLv1, KewajibanLv2, 'kewajiban', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/kewajiban/lv1_form.html', {'form': form, 'title': 'Edit Kewajiban Level 1', 'object': obj})


@login_required
def kewajiban_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KewajibanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


@login_required
def kewajiban_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(KewajibanLv1, pk=lv1_pk)
    form = KewajibanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.kewajiban = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(KewajibanLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/kewajiban/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Kewajiban Level 2'})


@login_required
def kewajiban_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(KewajibanLv1, pk=lv1_pk)
    obj = get_object_or_404(KewajibanLv2, pk=pk, kewajiban=parent)
    old_kode = obj.kode
    form = KewajibanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(KewajibanLv2, 'kewajiban', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/kewajiban/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Kewajiban Level 2'})


@login_required
def kewajiban_lv2_delete(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(KewajibanLv1, pk=lv1_pk)
    obj = get_object_or_404(KewajibanLv2, pk=pk, kewajiban=parent)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena akun ini masih digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


# ── Ekuitas Level 1 ───────────────────────────────────────────────────────────

@login_required
def ekuitas_lv1_create(request: HttpRequest) -> HttpResponse:
    form = EkuitasLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.kode:
            obj.kode = _next_lv1_kode(EkuitasLv1, '3')
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/ekuitas/lv1_form.html', {'form': form, 'title': 'Tambah Ekuitas Level 1'})


@login_required
def ekuitas_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EkuitasLv1, pk=pk)
    old_kode = obj.kode
    form = EkuitasLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            form.instance.kode = old_kode
            form.save(commit=False)
            _renumber_lv1_kode(EkuitasLv1, EkuitasLv2, 'ekuitas', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/ekuitas/lv1_form.html', {'form': form, 'title': 'Edit Ekuitas Level 1', 'object': obj})


@login_required
def ekuitas_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EkuitasLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


@login_required
def ekuitas_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(EkuitasLv1, pk=lv1_pk)
    form = EkuitasLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.ekuitas = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(EkuitasLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/ekuitas/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Ekuitas Level 2'})


@login_required
def ekuitas_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EkuitasLv1, pk=lv1_pk)
    obj = get_object_or_404(EkuitasLv2, pk=pk, ekuitas=parent)
    old_kode = obj.kode
    form = EkuitasLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(EkuitasLv2, 'ekuitas', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/ekuitas/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Ekuitas Level 2'})


@login_required
def ekuitas_lv2_delete(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EkuitasLv1, pk=lv1_pk)
    obj = get_object_or_404(EkuitasLv2, pk=pk, ekuitas=parent)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena akun ini masih digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


# ── Pendapatan Level 1 ────────────────────────────────────────────────────────

@login_required
def pendapatan_lv1_create(request: HttpRequest) -> HttpResponse:
    form = PendapatanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.kode:
            obj.kode = _next_lv1_kode(PendapatanLv1, '4')
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/pendapatan/lv1_form.html', {'form': form, 'title': 'Tambah Pendapatan Level 1'})


@login_required
def pendapatan_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(PendapatanLv1, pk=pk)
    old_kode = obj.kode
    form = PendapatanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            form.instance.kode = old_kode
            form.save(commit=False)
            _renumber_lv1_kode(PendapatanLv1, PendapatanLv2, 'pendapatan', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/pendapatan/lv1_form.html', {'form': form, 'title': 'Edit Pendapatan Level 1', 'object': obj})


@login_required
def pendapatan_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(PendapatanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


@login_required
def pendapatan_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(PendapatanLv1, pk=lv1_pk)
    form = PendapatanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.pendapatan = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(PendapatanLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/pendapatan/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Pendapatan Level 2'})


@login_required
def pendapatan_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(PendapatanLv1, pk=lv1_pk)
    obj = get_object_or_404(PendapatanLv2, pk=pk, pendapatan=parent)
    old_kode = obj.kode
    form = PendapatanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(PendapatanLv2, 'pendapatan', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/pendapatan/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Pendapatan Level 2'})


@login_required
def pendapatan_lv2_delete(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(PendapatanLv1, pk=lv1_pk)
    obj = get_object_or_404(PendapatanLv2, pk=pk, pendapatan=parent)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena akun ini masih digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


# ── Beban Level 1 ────────────────────────────────────────────────────────────

@login_required
def beban_lv1_create(request: HttpRequest) -> HttpResponse:
    form = BebanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if not obj.kode:
            obj.kode = _next_lv1_kode(BebanLv1, '5')
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/beban/lv1_form.html', {'form': form, 'title': 'Tambah Beban Level 1'})


@login_required
def beban_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(BebanLv1, pk=pk)
    old_kode = obj.kode
    form = BebanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            form.instance.kode = old_kode
            form.save(commit=False)
            _renumber_lv1_kode(BebanLv1, BebanLv2, 'beban', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/beban/lv1_form.html', {'form': form, 'title': 'Edit Beban Level 1', 'object': obj})


@login_required
def beban_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(BebanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


@login_required
def beban_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(BebanLv1, pk=lv1_pk)
    form = BebanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.beban = parent
        if not obj.kode:
            obj.kode = _next_lv2_kode(BebanLv2, parent.kode)
        obj.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/beban/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Beban Level 2'})


@login_required
def beban_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(BebanLv1, pk=lv1_pk)
    obj = get_object_or_404(BebanLv2, pk=pk, beban=parent)
    old_kode = obj.kode
    form = BebanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        new_kode = form.cleaned_data.get('kode') or old_kode
        if new_kode != old_kode:
            _renumber_lv2_kode(BebanLv2, 'beban', obj, old_kode, new_kode)
        else:
            form.save()
        if _is_ajax(request):
            return _ajax_success()
        return redirect('master_data:chart_of_accounts')
    if _is_ajax(request):
        return _ajax_error(form)
    return render(request, 'master_data/beban/lv2_form.html', {'form': form, 'parent': parent, 'object': obj, 'title': 'Edit Beban Level 2'})


@login_required
def beban_lv2_delete(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(BebanLv1, pk=lv1_pk)
    obj = get_object_or_404(BebanLv2, pk=pk, beban=parent)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena akun ini masih digunakan dalam jurnal.')
            return redirect('master_data:chart_of_accounts')
        return redirect('master_data:chart_of_accounts')
    return redirect('master_data:chart_of_accounts')


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@login_required
def chart_of_accounts(request: HttpRequest) -> HttpResponse:
    """Chart of Accounts page - shows all account categories with nested hierarchy."""
    from .utils import natural_sort_key

    def _sorted_items(queryset):
        items = sorted(list(queryset.prefetch_related('children')), key=lambda x: natural_sort_key(x.kode))
        for item in items:
            item.sorted_children = sorted(list(item.children.all()), key=lambda c: natural_sort_key(c.kode))
        return items

    categories = [
        {
            'name': 'Aset', 'prefix': '1', 'slug': 'aset',
            'items': _sorted_items(AsetLv1.objects.all()),
            'lv1_create': 'master_data:aset_lv1_create',
            'lv1_update': 'master_data:aset_lv1_update',
            'lv1_delete': 'master_data:aset_lv1_delete',
            'lv2_create': 'master_data:aset_lv2_create',
            'lv2_update': 'master_data:aset_lv2_update',
            'lv2_delete': 'master_data:aset_lv2_delete',
        },
        {
            'name': 'Kewajiban', 'prefix': '2', 'slug': 'kewajiban',
            'items': _sorted_items(KewajibanLv1.objects.all()),
            'lv1_create': 'master_data:kewajiban_lv1_create',
            'lv1_update': 'master_data:kewajiban_lv1_update',
            'lv1_delete': 'master_data:kewajiban_lv1_delete',
            'lv2_create': 'master_data:kewajiban_lv2_create',
            'lv2_update': 'master_data:kewajiban_lv2_update',
            'lv2_delete': 'master_data:kewajiban_lv2_delete',
        },
        {
            'name': 'Ekuitas', 'prefix': '3', 'slug': 'ekuitas',
            'items': _sorted_items(EkuitasLv1.objects.all()),
            'lv1_create': 'master_data:ekuitas_lv1_create',
            'lv1_update': 'master_data:ekuitas_lv1_update',
            'lv1_delete': 'master_data:ekuitas_lv1_delete',
            'lv2_create': 'master_data:ekuitas_lv2_create',
            'lv2_update': 'master_data:ekuitas_lv2_update',
            'lv2_delete': 'master_data:ekuitas_lv2_delete',
        },
        {
            'name': 'Pendapatan', 'prefix': '4', 'slug': 'pendapatan',
            'items': _sorted_items(PendapatanLv1.objects.all()),
            'lv1_create': 'master_data:pendapatan_lv1_create',
            'lv1_update': 'master_data:pendapatan_lv1_update',
            'lv1_delete': 'master_data:pendapatan_lv1_delete',
            'lv2_create': 'master_data:pendapatan_lv2_create',
            'lv2_update': 'master_data:pendapatan_lv2_update',
            'lv2_delete': 'master_data:pendapatan_lv2_delete',
        },
        {
            'name': 'Beban', 'prefix': '5', 'slug': 'beban',
            'items': _sorted_items(BebanLv1.objects.all()),
            'lv1_create': 'master_data:beban_lv1_create',
            'lv1_update': 'master_data:beban_lv1_update',
            'lv1_delete': 'master_data:beban_lv1_delete',
            'lv2_create': 'master_data:beban_lv2_create',
            'lv2_update': 'master_data:beban_lv2_update',
            'lv2_delete': 'master_data:beban_lv2_delete',
        },
    ]
    return render(request, 'master_data/chart_of_accounts.html', {'categories': categories})


# ── TipeTransaksi ─────────────────────────────────────────────────────────────

@login_required
def tipe_transaksi_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/tipe_transaksi/list.html', {'object_list': TipeTransaksi.objects.all().order_by('kode_transaksi')})


# ── Prefiks Transaksi (read-only, model in jurnal app) ───────────────────────

@login_required
def prefix_list(request: HttpRequest) -> HttpResponse:
    from apps.jurnal.models import TransactionPrefix
    return render(request, 'master_data/prefix/list.html', {
        'object_list': TransactionPrefix.objects.all().order_by('kode'),
    })


# ── Bukti ─────────────────────────────────────────────────────────────────────

@login_required
def bukti_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Bukti, pk=pk)
    return render(request, 'master_data/bukti/detail.html', {'object': obj})


# ── Chart of Accounts: Export ─────────────────────────────────────────────────

# Category metadata used by both export and import views
_COA_CATEGORIES: list[dict] = [
    {
        'prefix': '1', 'name': 'ASET',
        'lv1_model': AsetLv1, 'lv2_model': AsetLv2,
        'lv1_fk': 'aset',
    },
    {
        'prefix': '2', 'name': 'KEWAJIBAN',
        'lv1_model': KewajibanLv1, 'lv2_model': KewajibanLv2,
        'lv1_fk': 'kewajiban',
    },
    {
        'prefix': '3', 'name': 'EKUITAS',
        'lv1_model': EkuitasLv1, 'lv2_model': EkuitasLv2,
        'lv1_fk': 'ekuitas',
    },
    {
        'prefix': '4', 'name': 'PENDAPATAN',
        'lv1_model': PendapatanLv1, 'lv2_model': PendapatanLv2,
        'lv1_fk': 'pendapatan',
    },
    {
        'prefix': '5', 'name': 'BEBAN',
        'lv1_model': BebanLv1, 'lv2_model': BebanLv2,
        'lv1_fk': 'beban',
    },
]

_COA_HEADERS = [
    'Kode Akun Lvl 1', 'Nama Akun Lvl 1',
    'Kode Akun Lvl 2', 'Nama Akun Lvl 2',
    'Kode Akun Lvl 3', 'Nama Akun',
]


@login_required
def coa_export(request: HttpRequest) -> HttpResponse:
    """Export Chart of Accounts as a CSV file."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="chart_of_accounts.csv"'
    response.write('\ufeff')  # UTF-8 BOM for Excel compatibility

    writer = csv.writer(response)
    writer.writerow(_COA_HEADERS)

    for cat in _COA_CATEGORIES:
        lv1_qs = cat['lv1_model'].objects.prefetch_related('children').order_by('kode')
        for lv1 in lv1_qs:
            lv2_qs = lv1.children.order_by('kode')
            if lv2_qs.exists():
                for lv2 in lv2_qs:
                    writer.writerow([
                        cat['prefix'], cat['name'],
                        lv1.kode, lv1.nama,
                        lv2.kode, lv2.nama,
                    ])
            else:
                writer.writerow([
                    cat['prefix'], cat['name'],
                    lv1.kode, lv1.nama,
                    '', '',
                ])

    return response


# ── Chart of Accounts: Import ─────────────────────────────────────────────────

def _get_category_by_prefix(prefix: str) -> dict | None:
    for cat in _COA_CATEGORIES:
        if cat['prefix'] == prefix:
            return cat
    return None


@login_required
def coa_import(request: HttpRequest) -> HttpResponse:
    """Import Chart of Accounts from a CSV file."""
    if request.method != 'POST':
        return redirect('master_data:chart_of_accounts')

    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        messages.error(request, 'Pilih file CSV terlebih dahulu.')
        return redirect('master_data:chart_of_accounts')

    if not csv_file.name.endswith('.csv'):
        messages.error(request, 'File harus berformat CSV.')
        return redirect('master_data:chart_of_accounts')

    try:
        raw = csv_file.read()
        # Strip UTF-8 BOM if present
        decoded = raw.decode('utf-8-sig').strip()
        reader = csv.DictReader(io.StringIO(decoded))

        # Validate headers
        required_headers = set(_COA_HEADERS)
        actual_headers = set(reader.fieldnames or [])
        missing = required_headers - actual_headers
        if missing:
            messages.error(request, f'Kolom tidak ditemukan: {", ".join(sorted(missing))}')
            return redirect('master_data:chart_of_accounts')

        created_lv1 = updated_lv1 = created_lv2 = updated_lv2 = 0
        errors: list[str] = []

        with transaction.atomic():
            for line_num, row in enumerate(reader, start=2):
                prefix = (row.get('Kode Akun Lvl 1') or '').strip()
                lv1_kode = (row.get('Kode Akun Lvl 2') or '').strip()
                lv1_nama = (row.get('Nama Akun Lvl 2') or '').strip()
                lv2_kode = (row.get('Kode Akun Lvl 3') or '').strip()
                lv2_nama = (row.get('Nama Akun') or '').strip()

                if not prefix or not lv1_kode or not lv1_nama:
                    errors.append(f'Baris {line_num}: kolom wajib kosong, dilewati.')
                    continue

                cat = _get_category_by_prefix(prefix)
                if not cat:
                    errors.append(f'Baris {line_num}: prefix "{prefix}" tidak dikenal.')
                    continue

                # Upsert Lv1 (e.g. AsetLv1)
                lv1_obj, lv1_created = cat['lv1_model'].objects.get_or_create(
                    kode=lv1_kode,
                    defaults={'nama': lv1_nama},
                )
                if not lv1_created and lv1_obj.nama != lv1_nama:
                    lv1_obj.nama = lv1_nama
                    lv1_obj.save()
                    updated_lv1 += 1
                elif lv1_created:
                    created_lv1 += 1

                # Upsert Lv2 (e.g. AsetLv2) only when kode provided
                if lv2_kode:
                    lv2_defaults = {cat['lv1_fk']: lv1_obj, 'nama': lv2_nama}
                    lv2_obj, lv2_created = cat['lv2_model'].objects.get_or_create(
                        kode=lv2_kode,
                        defaults=lv2_defaults,
                    )
                    if not lv2_created:
                        changed = False
                        if getattr(lv2_obj, cat['lv1_fk']).pk != lv1_obj.pk:
                            setattr(lv2_obj, cat['lv1_fk'], lv1_obj)
                            changed = True
                        if lv2_obj.nama != lv2_nama and lv2_nama:
                            lv2_obj.nama = lv2_nama
                            changed = True
                        if changed:
                            lv2_obj.save()
                            updated_lv2 += 1
                    else:
                        created_lv2 += 1

        parts = []
        if created_lv1:
            parts.append(f'{created_lv1} sub-kategori baru')
        if updated_lv1:
            parts.append(f'{updated_lv1} sub-kategori diperbarui')
        if created_lv2:
            parts.append(f'{created_lv2} akun baru')
        if updated_lv2:
            parts.append(f'{updated_lv2} akun diperbarui')

        if errors:
            extra = len(errors) - 5
            shown = '; '.join(errors[:5])
            suffix = f' (dan {extra} lainnya)' if extra > 0 else ''
            messages.warning(request, f'Import selesai dengan peringatan: {shown}{suffix}')

        summary = ', '.join(parts) if parts else 'Tidak ada perubahan.'
        messages.success(request, f'Import berhasil: {summary}')

    except Exception as exc:
        messages.error(request, f'Gagal memproses file: {exc}')

    return redirect('master_data:chart_of_accounts')


# ── Chart of Accounts: Preview (AJAX) ────────────────────────────────────────

@login_required
def coa_preview(request: HttpRequest) -> JsonResponse:
    """Parse an uploaded CSV and return rows with validation status (AJAX only).

    Each row in the response has:
      prefix, lv1_kode, lv1_nama, lv2_kode, lv2_nama,
      lv1_status ('new'|'update'|'error'), lv2_status ('new'|'update'|'skip'|'error'),
      error (human-readable message, empty when valid)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'Pilih file CSV terlebih dahulu.'})

    try:
        raw = csv_file.read()
        decoded = raw.decode('utf-8-sig').strip()
        reader = csv.DictReader(io.StringIO(decoded))

        required_headers = set(_COA_HEADERS)
        actual_headers = set(reader.fieldnames or [])
        missing = required_headers - actual_headers
        if missing:
            return JsonResponse({
                'success': False,
                'error': f'Kolom tidak ditemukan: {", ".join(sorted(missing))}',
            })

        # Pre-load all existing lv1 and lv2 kodes per category for O(1) lookup
        db_lv1: dict[str, set[str]] = {}
        db_lv2: dict[str, set[str]] = {}
        for cat in _COA_CATEGORIES:
            slug = cat['lv1_fk']
            db_lv1[slug] = set(cat['lv1_model'].objects.values_list('kode', flat=True))
            db_lv2[slug] = set(cat['lv2_model'].objects.values_list('kode', flat=True))

        rows_out = []
        seen_lv1_in_csv: dict[str, str] = {}  # kode → first-seen category slug
        seen_lv2_in_csv: set[str] = set()

        for row in reader:
            prefix = (row.get('Kode Akun Lvl 1') or '').strip()
            lv1_kode = (row.get('Kode Akun Lvl 2') or '').strip()
            lv1_nama = (row.get('Nama Akun Lvl 2') or '').strip()
            lv2_kode = (row.get('Kode Akun Lvl 3') or '').strip()
            lv2_nama = (row.get('Nama Akun') or '').strip()
            cat_early = _get_category_by_prefix(prefix)

            entry: dict = {
                'prefix': prefix,
                'category_name': cat_early['name'] if cat_early else '',
                'lv1_kode': lv1_kode,
                'lv1_nama': lv1_nama,
                'lv2_kode': lv2_kode,
                'lv2_nama': lv2_nama,
                'lv1_status': 'new',
                'lv2_status': 'skip',
                'error': '',
            }

            # ── Required fields ──────────────────────────────────────────────
            if not prefix or not lv1_kode or not lv1_nama:
                entry['lv1_status'] = 'error'
                entry['error'] = 'Kolom wajib (prefix / kode lvl2 / nama lvl2) kosong.'
                rows_out.append(entry)
                continue

            cat = _get_category_by_prefix(prefix)
            if not cat:
                entry['lv1_status'] = 'error'
                entry['error'] = f'Prefix "{prefix}" tidak dikenal (harus 1–5).'
                rows_out.append(entry)
                continue

            entry['category_name'] = cat['name']
            slug = cat['lv1_fk']

            # ── Lv1 validation ───────────────────────────────────────────────
            if lv1_kode in seen_lv1_in_csv and seen_lv1_in_csv[lv1_kode] == slug:
                entry['lv1_status'] = 'update'  # repeated in CSV → treated as update
            elif lv1_kode in seen_lv1_in_csv:
                entry['lv1_status'] = 'error'
                entry['error'] = f'Kode Lvl 2 "{lv1_kode}" muncul di kategori berbeda dalam file.'
                rows_out.append(entry)
                continue
            elif lv1_kode in db_lv1[slug]:
                entry['lv1_status'] = 'update'
                seen_lv1_in_csv[lv1_kode] = slug
            else:
                entry['lv1_status'] = 'new'
                seen_lv1_in_csv[lv1_kode] = slug

            # ── Lv2 validation ───────────────────────────────────────────────
            if lv2_kode:
                if lv2_kode in seen_lv2_in_csv:
                    entry['lv2_status'] = 'error'
                    entry['error'] = f'Kode Lvl 3 "{lv2_kode}" duplikat dalam file.'
                elif lv2_kode in db_lv2[slug]:
                    entry['lv2_status'] = 'update'
                    seen_lv2_in_csv.add(lv2_kode)
                else:
                    entry['lv2_status'] = 'new'
                    seen_lv2_in_csv.add(lv2_kode)
            else:
                entry['lv2_status'] = 'skip'

            rows_out.append(entry)

        return JsonResponse({'success': True, 'rows': rows_out})

    except Exception:
        logger.exception('coa_preview: error processing CSV')
        return JsonResponse({'success': False, 'error': 'Gagal memproses file. Periksa format CSV dan coba lagi.'})


# ── Chart of Accounts: Import from JSON (AJAX) ────────────────────────────────

@login_required
def coa_import_json(request: HttpRequest) -> JsonResponse:
    """Import rows submitted as JSON (from the preview modal)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
        rows = body.get('rows', [])
    except Exception:
        return JsonResponse({'success': False, 'error': 'Payload JSON tidak valid.'})

    if not rows:
        return JsonResponse({'success': False, 'error': 'Tidak ada baris untuk disimpan.'})

    created_lv1 = updated_lv1 = created_lv2 = updated_lv2 = 0

    try:
        with transaction.atomic():
            for row in rows:
                prefix = str(row.get('prefix', '')).strip()
                lv1_kode = str(row.get('lv1_kode', '')).strip()
                lv1_nama = str(row.get('lv1_nama', '')).strip()
                lv2_kode = str(row.get('lv2_kode', '')).strip()
                lv2_nama = str(row.get('lv2_nama', '')).strip()

                if not prefix or not lv1_kode or not lv1_nama:
                    continue

                cat = _get_category_by_prefix(prefix)
                if not cat:
                    continue

                lv1_obj, lv1_created = cat['lv1_model'].objects.get_or_create(
                    kode=lv1_kode,
                    defaults={'nama': lv1_nama},
                )
                if not lv1_created and lv1_obj.nama != lv1_nama:
                    lv1_obj.nama = lv1_nama
                    lv1_obj.save()
                    updated_lv1 += 1
                elif lv1_created:
                    created_lv1 += 1

                if lv2_kode:
                    lv2_defaults = {cat['lv1_fk']: lv1_obj, 'nama': lv2_nama}
                    lv2_obj, lv2_created = cat['lv2_model'].objects.get_or_create(
                        kode=lv2_kode,
                        defaults=lv2_defaults,
                    )
                    if not lv2_created:
                        changed = False
                        if getattr(lv2_obj, cat['lv1_fk']).pk != lv1_obj.pk:
                            setattr(lv2_obj, cat['lv1_fk'], lv1_obj)
                            changed = True
                        if lv2_obj.nama != lv2_nama and lv2_nama:
                            lv2_obj.nama = lv2_nama
                            changed = True
                        if changed:
                            lv2_obj.save()
                            updated_lv2 += 1
                    else:
                        created_lv2 += 1

        parts = []
        if created_lv1:
            parts.append(f'{created_lv1} sub-kategori baru')
        if updated_lv1:
            parts.append(f'{updated_lv1} sub-kategori diperbarui')
        if created_lv2:
            parts.append(f'{created_lv2} akun baru')
        if updated_lv2:
            parts.append(f'{updated_lv2} akun diperbarui')

        summary = ', '.join(parts) if parts else 'Tidak ada perubahan.'
        return JsonResponse({'success': True, 'summary': summary})

    except Exception:
        logger.exception('coa_import_json: error saving rows')
        return JsonResponse({'success': False, 'error': 'Gagal menyimpan data. Silakan coba lagi.'})
