"""Master data views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models.deletion import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    AsetLv1Form, AsetLv2Form,
    KewajibanLv1Form, KewajibanLv2Form,
    EkuitasLv1Form, EkuitasLv2Form,
    PendapatanLv1Form, PendapatanLv2Form,
    BebanLv1Form, BebanLv2Form,
    TipeTransaksiForm,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _crud_views(model, form_class, list_template, form_template, delete_template, redirect_name, extra_context=None):
    """Factory returning (list, create, update, delete) view functions."""

    @login_required
    def list_view(request: HttpRequest, **kwargs) -> HttpResponse:
        ctx = {'object_list': model.objects.all().order_by('kode'), **(extra_context or {})}
        return render(request, list_template, ctx)

    @login_required
    def create_view(request: HttpRequest, **kwargs) -> HttpResponse:
        form = form_class(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            obj = form.save(commit=False)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.save()
            return redirect(redirect_name, **kwargs)
        ctx = {'form': form, 'title': f'Tambah {model._meta.verbose_name}', **(extra_context or {}), **kwargs}
        return render(request, form_template, ctx)

    @login_required
    def update_view(request: HttpRequest, pk: int, **kwargs) -> HttpResponse:
        obj = get_object_or_404(model, pk=pk)
        form = form_class(request.POST or None, instance=obj)
        if request.method == 'POST' and form.is_valid():
            form.save()
            return redirect(redirect_name, **kwargs)
        ctx = {'form': form, 'title': f'Edit {model._meta.verbose_name}', 'object': obj, **(extra_context or {}), **kwargs}
        return render(request, form_template, ctx)

    @login_required
    def delete_view(request: HttpRequest, pk: int, **kwargs) -> HttpResponse:
        obj = get_object_or_404(model, pk=pk)
        if request.method == 'POST':
            obj.delete()
            return redirect(redirect_name, **kwargs)
        ctx = {'object': obj, **(extra_context or {}), **kwargs}
        return render(request, delete_template, ctx)

    return list_view, create_view, update_view, delete_view


# ── Aset Level 1 ──────────────────────────────────────────────────────────────

@login_required
def aset_lv1_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/aset/lv1_list.html', {'object_list': AsetLv1.objects.all().order_by('kode')})


@login_required
def aset_lv1_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(AsetLv1, pk=pk)
    children = obj.children.all().order_by('kode')
    return render(request, 'master_data/aset/lv1_detail.html', {'object': obj, 'children': children})


@login_required
def aset_lv1_create(request: HttpRequest) -> HttpResponse:
    form = AsetLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:aset_lv1_list')
    return render(request, 'master_data/aset/lv1_form.html', {'form': form, 'title': 'Tambah Aset Level 1'})


@login_required
def aset_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(AsetLv1, pk=pk)
    form = AsetLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:aset_lv1_list')
    return render(request, 'master_data/aset/lv1_form.html', {'form': form, 'title': 'Edit Aset Level 1', 'object': obj})


@login_required
def aset_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(AsetLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:aset_lv1_list')
        return redirect('master_data:aset_lv1_list')
    return render(request, 'master_data/aset/lv1_confirm_delete.html', {'object': obj})


@login_required
def aset_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    form = AsetLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.aset = parent
        obj.save()
        return redirect('master_data:aset_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/aset/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Aset Level 2'})


@login_required
def aset_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(AsetLv1, pk=lv1_pk)
    obj = get_object_or_404(AsetLv2, pk=pk, aset=parent)
    form = AsetLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:aset_lv1_detail', pk=lv1_pk)
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
            return redirect('master_data:aset_lv1_detail', pk=lv1_pk)
        return redirect('master_data:aset_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/aset/lv2_confirm_delete.html', {'object': obj, 'parent': parent})


# ── Kewajiban Level 1 ─────────────────────────────────────────────────────────

@login_required
def kewajiban_lv1_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/kewajiban/lv1_list.html', {'object_list': KewajibanLv1.objects.all().order_by('kode')})


@login_required
def kewajiban_lv1_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KewajibanLv1, pk=pk)
    children = obj.children.all().order_by('kode')
    return render(request, 'master_data/kewajiban/lv1_detail.html', {'object': obj, 'children': children})


@login_required
def kewajiban_lv1_create(request: HttpRequest) -> HttpResponse:
    form = KewajibanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:kewajiban_lv1_list')
    return render(request, 'master_data/kewajiban/lv1_form.html', {'form': form, 'title': 'Tambah Kewajiban Level 1'})


@login_required
def kewajiban_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KewajibanLv1, pk=pk)
    form = KewajibanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:kewajiban_lv1_list')
    return render(request, 'master_data/kewajiban/lv1_form.html', {'form': form, 'title': 'Edit Kewajiban Level 1', 'object': obj})


@login_required
def kewajiban_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(KewajibanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:kewajiban_lv1_list')
        return redirect('master_data:kewajiban_lv1_list')
    return render(request, 'master_data/kewajiban/lv1_confirm_delete.html', {'object': obj})


@login_required
def kewajiban_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(KewajibanLv1, pk=lv1_pk)
    form = KewajibanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.kewajiban = parent
        obj.save()
        return redirect('master_data:kewajiban_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/kewajiban/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Kewajiban Level 2'})


@login_required
def kewajiban_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(KewajibanLv1, pk=lv1_pk)
    obj = get_object_or_404(KewajibanLv2, pk=pk, kewajiban=parent)
    form = KewajibanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:kewajiban_lv1_detail', pk=lv1_pk)
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
            return redirect('master_data:kewajiban_lv1_detail', pk=lv1_pk)
        return redirect('master_data:kewajiban_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/kewajiban/lv2_confirm_delete.html', {'object': obj, 'parent': parent})


# ── Ekuitas Level 1 ───────────────────────────────────────────────────────────

@login_required
def ekuitas_lv1_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/ekuitas/lv1_list.html', {'object_list': EkuitasLv1.objects.all().order_by('kode')})


@login_required
def ekuitas_lv1_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EkuitasLv1, pk=pk)
    children = obj.children.all().order_by('kode')
    return render(request, 'master_data/ekuitas/lv1_detail.html', {'object': obj, 'children': children})


@login_required
def ekuitas_lv1_create(request: HttpRequest) -> HttpResponse:
    form = EkuitasLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:ekuitas_lv1_list')
    return render(request, 'master_data/ekuitas/lv1_form.html', {'form': form, 'title': 'Tambah Ekuitas Level 1'})


@login_required
def ekuitas_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EkuitasLv1, pk=pk)
    form = EkuitasLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:ekuitas_lv1_list')
    return render(request, 'master_data/ekuitas/lv1_form.html', {'form': form, 'title': 'Edit Ekuitas Level 1', 'object': obj})


@login_required
def ekuitas_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EkuitasLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:ekuitas_lv1_list')
        return redirect('master_data:ekuitas_lv1_list')
    return render(request, 'master_data/ekuitas/lv1_confirm_delete.html', {'object': obj})


@login_required
def ekuitas_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(EkuitasLv1, pk=lv1_pk)
    form = EkuitasLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.ekuitas = parent
        obj.save()
        return redirect('master_data:ekuitas_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/ekuitas/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Ekuitas Level 2'})


@login_required
def ekuitas_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(EkuitasLv1, pk=lv1_pk)
    obj = get_object_or_404(EkuitasLv2, pk=pk, ekuitas=parent)
    form = EkuitasLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:ekuitas_lv1_detail', pk=lv1_pk)
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
            return redirect('master_data:ekuitas_lv1_detail', pk=lv1_pk)
        return redirect('master_data:ekuitas_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/ekuitas/lv2_confirm_delete.html', {'object': obj, 'parent': parent})


# ── Pendapatan Level 1 ────────────────────────────────────────────────────────

@login_required
def pendapatan_lv1_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/pendapatan/lv1_list.html', {'object_list': PendapatanLv1.objects.all().order_by('kode')})


@login_required
def pendapatan_lv1_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(PendapatanLv1, pk=pk)
    children = obj.children.all().order_by('kode')
    return render(request, 'master_data/pendapatan/lv1_detail.html', {'object': obj, 'children': children})


@login_required
def pendapatan_lv1_create(request: HttpRequest) -> HttpResponse:
    form = PendapatanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:pendapatan_lv1_list')
    return render(request, 'master_data/pendapatan/lv1_form.html', {'form': form, 'title': 'Tambah Pendapatan Level 1'})


@login_required
def pendapatan_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(PendapatanLv1, pk=pk)
    form = PendapatanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:pendapatan_lv1_list')
    return render(request, 'master_data/pendapatan/lv1_form.html', {'form': form, 'title': 'Edit Pendapatan Level 1', 'object': obj})


@login_required
def pendapatan_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(PendapatanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:pendapatan_lv1_list')
        return redirect('master_data:pendapatan_lv1_list')
    return render(request, 'master_data/pendapatan/lv1_confirm_delete.html', {'object': obj})


@login_required
def pendapatan_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(PendapatanLv1, pk=lv1_pk)
    form = PendapatanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.pendapatan = parent
        obj.save()
        return redirect('master_data:pendapatan_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/pendapatan/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Pendapatan Level 2'})


@login_required
def pendapatan_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(PendapatanLv1, pk=lv1_pk)
    obj = get_object_or_404(PendapatanLv2, pk=pk, pendapatan=parent)
    form = PendapatanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:pendapatan_lv1_detail', pk=lv1_pk)
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
            return redirect('master_data:pendapatan_lv1_detail', pk=lv1_pk)
        return redirect('master_data:pendapatan_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/pendapatan/lv2_confirm_delete.html', {'object': obj, 'parent': parent})


# ── Beban Level 1 ────────────────────────────────────────────────────────────

@login_required
def beban_lv1_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/beban/lv1_list.html', {'object_list': BebanLv1.objects.all().order_by('kode')})


@login_required
def beban_lv1_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(BebanLv1, pk=pk)
    children = obj.children.all().order_by('kode')
    return render(request, 'master_data/beban/lv1_detail.html', {'object': obj, 'children': children})


@login_required
def beban_lv1_create(request: HttpRequest) -> HttpResponse:
    form = BebanLv1Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:beban_lv1_list')
    return render(request, 'master_data/beban/lv1_form.html', {'form': form, 'title': 'Tambah Beban Level 1'})


@login_required
def beban_lv1_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(BebanLv1, pk=pk)
    form = BebanLv1Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:beban_lv1_list')
    return render(request, 'master_data/beban/lv1_form.html', {'form': form, 'title': 'Edit Beban Level 1', 'object': obj})


@login_required
def beban_lv1_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(BebanLv1, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena masih ada akun yang digunakan dalam jurnal.')
            return redirect('master_data:beban_lv1_list')
        return redirect('master_data:beban_lv1_list')
    return render(request, 'master_data/beban/lv1_confirm_delete.html', {'object': obj})


@login_required
def beban_lv2_create(request: HttpRequest, lv1_pk: int) -> HttpResponse:
    parent = get_object_or_404(BebanLv1, pk=lv1_pk)
    form = BebanLv2Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.beban = parent
        obj.save()
        return redirect('master_data:beban_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/beban/lv2_form.html', {'form': form, 'parent': parent, 'title': 'Tambah Beban Level 2'})


@login_required
def beban_lv2_update(request: HttpRequest, lv1_pk: int, pk: int) -> HttpResponse:
    parent = get_object_or_404(BebanLv1, pk=lv1_pk)
    obj = get_object_or_404(BebanLv2, pk=pk, beban=parent)
    form = BebanLv2Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:beban_lv1_detail', pk=lv1_pk)
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
            return redirect('master_data:beban_lv1_detail', pk=lv1_pk)
        return redirect('master_data:beban_lv1_detail', pk=lv1_pk)
    return render(request, 'master_data/beban/lv2_confirm_delete.html', {'object': obj, 'parent': parent})


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@login_required
def chart_of_accounts(request: HttpRequest) -> HttpResponse:
    """Chart of Accounts page - shows all account categories with nested hierarchy."""
    categories = [
        {'name': 'Aset', 'prefix': '1', 'items': AsetLv1.objects.prefetch_related('children').order_by('kode')},
        {'name': 'Kewajiban', 'prefix': '2', 'items': KewajibanLv1.objects.prefetch_related('children').order_by('kode')},
        {'name': 'Ekuitas', 'prefix': '3', 'items': EkuitasLv1.objects.prefetch_related('children').order_by('kode')},
        {'name': 'Pendapatan', 'prefix': '4', 'items': PendapatanLv1.objects.prefetch_related('children').order_by('kode')},
        {'name': 'Beban', 'prefix': '5', 'items': BebanLv1.objects.prefetch_related('children').order_by('kode')},
    ]
    return render(request, 'master_data/chart_of_accounts.html', {'categories': categories})


# ── TipeTransaksi ─────────────────────────────────────────────────────────────

@login_required
def tipe_transaksi_list(request: HttpRequest) -> HttpResponse:
    return render(request, 'master_data/tipe_transaksi/list.html', {'object_list': TipeTransaksi.objects.all().order_by('kode_transaksi')})


@login_required
def tipe_transaksi_create(request: HttpRequest) -> HttpResponse:
    form = TipeTransaksiForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:tipe_transaksi_list')
    return render(request, 'master_data/tipe_transaksi/form.html', {'form': form, 'title': 'Tambah Tipe Transaksi'})


@login_required
def tipe_transaksi_update(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TipeTransaksi, pk=pk)
    form = TipeTransaksiForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('master_data:tipe_transaksi_list')
    return render(request, 'master_data/tipe_transaksi/form.html', {'form': form, 'title': 'Edit Tipe Transaksi', 'object': obj})


@login_required
def tipe_transaksi_delete(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(TipeTransaksi, pk=pk)
    if request.method == 'POST':
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Tidak dapat dihapus karena tipe transaksi ini masih digunakan dalam jurnal.')
            return redirect('master_data:tipe_transaksi_list')
        return redirect('master_data:tipe_transaksi_list')
    return render(request, 'master_data/tipe_transaksi/confirm_delete.html', {'object': obj})


# ── Bukti ─────────────────────────────────────────────────────────────────────

@login_required
def bukti_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(Bukti, pk=pk)
    return render(request, 'master_data/bukti/detail.html', {'object': obj})
