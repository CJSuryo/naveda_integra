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
    return redirect('entitas_bisnis:tipe_entitas_list')


# ── Entitas Bisnis (Level 1) ─────────────────────────────────────────────────

@login_required
def list_view(request: HttpRequest) -> HttpResponse:
    lv1_list = (
        EntitasBisnis.objects
        .select_related('tipe_entitas', 'pos_config')
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
    return render(request, 'entitas_bisnis/form.html', {'form': form, 'title': 'Edit Entitas Bisnis Level 1', 'object': obj})


@login_required
def delete_view(request: HttpRequest, pk: int) -> HttpResponse:
    obj = get_object_or_404(EntitasBisnis, pk=pk)
    if request.method == 'POST':
        obj.delete()
        return redirect('entitas_bisnis:list')
    return redirect('entitas_bisnis:list')


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
    return redirect('entitas_bisnis:list')


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
    return redirect('entitas_bisnis:list')


# ── Setup Wizard ──────────────────────────────────────────────────────────────

def _compute_wizard_checks(eb) -> dict:
    """Compute completion status for all wizard checklist items.

    eb must be fetched with select_related('pos_config') and
    prefetch_related('children_lv2__children_lv3').
    """
    from apps.purchase.models import SubTransactionType
    from apps.accounts.models import UserEntitasBisnis

    lv2_list = [lv2 for lv2 in eb.children_lv2.all() if lv2.status_aktif]
    lv2_count = len(lv2_list)

    lv3_count = sum(
        lv3.status_aktif
        for lv2 in lv2_list
        for lv3 in lv2.children_lv3.all()
    )

    pos_cfg = getattr(eb, 'pos_config', None)
    pos_config_ok = bool(
        pos_cfg and
        pos_cfg.sub_transaction_type_id and
        pos_cfg.revenue_account_id and
        pos_cfg.offset_coa_account_id and
        pos_cfg.default_payment_account_id
    )

    stt_exists = SubTransactionType.objects.filter(module='sales').exists()
    stt_assigned = bool(pos_cfg and pos_cfg.sub_transaction_type_id)
    stt_ok = stt_exists and stt_assigned

    users = list(
        UserEntitasBisnis.objects.filter(
            entitas_bisnis=eb, user__is_active=True
        ).select_related('user')
    )
    users_ok = len(users) > 0

    qris_ok = bool(pos_cfg and pos_cfg.qris_image)

    pos_missing = []
    if pos_cfg:
        if not pos_cfg.sub_transaction_type_id:
            pos_missing.append('Sub-Transaction Type')
        if not pos_cfg.revenue_account_id:
            pos_missing.append('Revenue Account')
        if not pos_cfg.offset_coa_account_id:
            pos_missing.append('HPP Account')
        if not pos_cfg.default_payment_account_id:
            pos_missing.append('Payment Account')

    all_required_ok = lv2_count > 0 and lv3_count > 0 and pos_config_ok and stt_ok and users_ok
    required_done = sum([lv2_count > 0, lv3_count > 0, pos_config_ok, stt_ok, users_ok])

    return {
        'lv2_list': lv2_list,
        'lv2_count': lv2_count,
        'lv2_ok': lv2_count > 0,
        'lv3_count': lv3_count,
        'lv3_ok': lv3_count > 0,
        'pos_config_ok': pos_config_ok,
        'pos_cfg': pos_cfg,
        'pos_missing': pos_missing,
        'stt_ok': stt_ok,
        'stt_exists': stt_exists,
        'stt_assigned': stt_assigned,
        'users': users,
        'users_ok': users_ok,
        'qris_ok': qris_ok,
        'all_required_ok': all_required_ok,
        'required_done': required_done,
        'required_total': 5,
    }


@login_required
def setup_wizard(request: HttpRequest, pk: int) -> HttpResponse:
    """Checklist dashboard wizard for configuring an Entitas Bisnis for Kasir."""
    eb = get_object_or_404(
        EntitasBisnis.objects
        .select_related('pos_config', 'tipe_entitas')
        .prefetch_related('children_lv2__children_lv3'),
        pk=pk,
    )
    checks = _compute_wizard_checks(eb)
    add_lv2_form = EntitasBisnisLv2Form()
    add_lv3_form = EntitasBisnisLv3Form()
    return render(request, 'entitas_bisnis/setup_wizard.html', {
        'eb': eb,
        'checks': checks,
        'add_lv2_form': add_lv2_form,
        'add_lv3_form': add_lv3_form,
    })
