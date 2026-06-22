"""Account views."""
from urllib.parse import urlparse

from django.contrib import messages as dj_messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    LoginForm, RegisterForm, UserForm, UserPermissionForm,
    CurrentPasswordForm, NamedSetPasswordForm,
)
from .emails import send_password_change_email
from .sessions import revoke_all_sessions
from .tokens import password_change_token
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from .models import NiPermission, UserEntitasBisnis

User = get_user_model()


def _check_perm(user, perm_code: str) -> HttpResponse | None:
    """Return HttpResponseForbidden if user lacks the given permission, else None."""
    if not user.has_ni_perm(perm_code):
        return HttpResponseForbidden('Anda tidak memiliki izin untuk mengakses halaman ini.')


def _get_safe_next(request: HttpRequest) -> str | None:
    """Validate the next parameter and reconstruct URL via Django's URL resolver.

    By resolving and then reversing the URL we break the user-input taint
    chain: the string passed to redirect() is produced by reverse(), not by
    any user-supplied value.
    """
    next_url = request.GET.get('next', '')
    if not next_url:
        return None
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    path = urlparse(next_url).path
    try:
        match = resolve(path)
    except Resolver404:
        return None
    # Reconstruct URL from the resolved match — this is NOT user input
    reconstructed = reverse(match.view_name, args=match.args, kwargs=match.kwargs)
    return reconstructed


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('home')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        safe_next = _get_safe_next(request)
        return redirect(safe_next) if safe_next else redirect('home')
    return render(request, 'accounts/login.html', {'form': form})


def landing_view(request: HttpRequest) -> HttpResponse:
    return render(request, 'landing.html')


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('login')


def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('home')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('home')
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def password_change_request(request: HttpRequest) -> HttpResponse:
    """Step 1: user re-enters current password; on success email a change link."""
    form = CurrentPasswordForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        send_password_change_email(request, request.user)
        return render(request, 'accounts/password_change_sent.html', {'email': request.user.email})
    return render(request, 'accounts/password_change_request.html', {'form': form})


def _get_user_from_uidb64(uidb64: str):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


@login_required
def password_change_confirm(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Step 2: validate the emailed link, set new password, revoke all sessions."""
    target = _get_user_from_uidb64(uidb64)
    valid = (
        target is not None
        and target.pk == request.user.pk
        and password_change_token.check_token(target, token)
    )
    if not valid:
        return render(request, 'accounts/password_change_invalid.html')

    form = NamedSetPasswordForm(target, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()                       # sets + saves new password
        revoke_all_sessions(target)       # logout from all devices
        logout(request)                   # clear current request session
        dj_messages.success(request, 'Kata sandi berhasil diubah. Silakan masuk kembali.')
        return redirect('login')
    return render(request, 'accounts/password_change_confirm.html', {'form': form})


@login_required
def home_view(request: HttpRequest) -> HttpResponse:
    from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3

    user = request.user

    if user.is_superuser or getattr(user, 'is_admin', False):
        eb_qs = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
    else:
        linked_ids = UserEntitasBisnis.objects.filter(user=user).values_list('entitas_bisnis_id', flat=True)
        eb_qs = EntitasBisnis.objects.filter(pk__in=linked_ids, status_aktif=True).order_by('nama')

    eb_list = list(eb_qs)

    if not eb_list:
        return render(request, 'home.html', {'no_eb_access': True})

    is_single_eb = len(eb_list) == 1

    if is_single_eb:
        selected_eb = eb_list[0]
        request.session['dashboard_eb_id'] = selected_eb.pk
        request.session['dashboard_eb_lv2_id'] = None
        request.session['dashboard_eb_lv3_id'] = None
    else:
        session_eb_id = request.session.get('dashboard_eb_id')
        valid_ids = {eb.pk for eb in eb_list}
        if session_eb_id not in valid_ids:
            request.session['dashboard_eb_id'] = eb_list[0].pk
            request.session['dashboard_eb_lv2_id'] = None
            request.session['dashboard_eb_lv3_id'] = None
        try:
            selected_eb = next(eb for eb in eb_list if eb.pk == request.session['dashboard_eb_id'])
        except StopIteration:
            selected_eb = eb_list[0]

    eb_lv2_id = request.session.get('dashboard_eb_lv2_id')
    eb_lv3_id = request.session.get('dashboard_eb_lv3_id')

    lv2_list = list(EntitasBisnisLv2.objects.filter(entitas_bisnis=selected_eb).order_by('nama'))
    lv3_list = list(
        EntitasBisnisLv3.objects.filter(parent_lv2_id=eb_lv2_id).order_by('nama')
    ) if eb_lv2_id else []

    return render(request, 'home.html', {
        'eb_list': eb_list,
        'selected_eb': selected_eb,
        'eb_lv2_id': eb_lv2_id,
        'eb_lv3_id': eb_lv3_id,
        'lv2_list': lv2_list,
        'lv3_list': lv3_list,
        'is_single_eb': is_single_eb,
    })


# ── User CRUD ────────────────────────────────────────────────────────────────

@login_required
def user_list(request: HttpRequest) -> HttpResponse:
    """List all users."""
    denied = _check_perm(request.user, 'user_view')
    if denied:
        return denied
    users = User.objects.select_related('role').all().order_by('email')
    return render(request, 'accounts/user_list.html', {'users': users})


@login_required
def user_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """User detail with permissions and entitas bisnis links."""
    denied = _check_perm(request.user, 'user_view')
    if denied:
        return denied
    user_obj = get_object_or_404(User.objects.select_related('role').prefetch_related('ni_permissions'), pk=pk)
    user_perms = set(user_obj.ni_permissions.values_list('code', flat=True))

    # Group permissions by module
    all_perms = NiPermission.objects.all().order_by('module', 'code')
    perm_groups: dict[str, list] = {}
    for perm in all_perms:
        perm_groups.setdefault(perm.module or 'General', []).append({
            'perm': perm,
            'has': perm.code in user_perms,
        })

    from apps.entitas_bisnis.models import EntitasBisnis

    user_ebs = UserEntitasBisnis.objects.filter(user=user_obj).select_related('entitas_bisnis')
    linked_eb_ids = set(user_ebs.values_list('entitas_bisnis_id', flat=True))
    all_ebs = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')

    return render(request, 'accounts/user_detail.html', {
        'user_obj': user_obj,
        'perm_groups': perm_groups,
        'user_ebs': user_ebs,
        'all_ebs': all_ebs,
        'linked_eb_ids': linked_eb_ids,
    })


@login_required
def user_create(request: HttpRequest) -> HttpResponse:
    """Create a new user."""
    denied = _check_perm(request.user, 'user_create')
    if denied:
        return denied
    form = UserForm(request.POST or None)
    next_url = request.GET.get('next', '')
    eb_pk = request.GET.get('eb', '')
    if request.method == 'POST' and form.is_valid():
        user_obj = form.save()
        if eb_pk:
            from apps.accounts.models import UserEntitasBisnis
            from apps.entitas_bisnis.models import EntitasBisnis
            try:
                eb = EntitasBisnis.objects.get(pk=int(eb_pk))
                UserEntitasBisnis.objects.get_or_create(user=user_obj, entitas_bisnis=eb)
            except (EntitasBisnis.DoesNotExist, ValueError, TypeError):
                pass
        dj_messages.success(request, f'User {user_obj.email} berhasil dibuat.')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('accounts:user_detail', pk=user_obj.pk)
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'title': 'Tambah User',
        'next_url': next_url,
        'eb_pk': eb_pk,
    })


@login_required
def user_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Update an existing user."""
    denied = _check_perm(request.user, 'user_update')
    if denied:
        return denied
    user_obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=user_obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        dj_messages.success(request, f'User {user_obj.email} berhasil diperbarui.')
        return redirect('accounts:user_detail', pk=user_obj.pk)
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Edit User', 'user_obj': user_obj})


@login_required
def user_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a user."""
    denied = _check_perm(request.user, 'user_delete')
    if denied:
        return denied
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        email = user_obj.email
        user_obj.delete()
        dj_messages.success(request, f'User {email} berhasil dihapus.')
        return redirect('accounts:user_list')
    return redirect('accounts:user_list')


@login_required
def user_permissions(request: HttpRequest, pk: int) -> HttpResponse:
    """Manage a user's permissions."""
    denied = _check_perm(request.user, 'user_manage_permissions')
    if denied:
        return denied
    user_obj = get_object_or_404(User.objects.prefetch_related('ni_permissions'), pk=pk)

    if request.method == 'POST':
        form = UserPermissionForm(request.POST)
        if form.is_valid():
            user_obj.ni_permissions.set(form.cleaned_data['permissions'])
            dj_messages.success(request, f'Permissions untuk {user_obj.email} berhasil diperbarui.')
            return redirect('accounts:user_detail', pk=user_obj.pk)
    else:
        form = UserPermissionForm(initial={'permissions': user_obj.ni_permissions.all()})

    # Group permissions by module for the template
    all_perms = NiPermission.objects.all().order_by('module', 'code')
    perm_groups: dict[str, list] = {}
    user_perm_ids = set(user_obj.ni_permissions.values_list('pk', flat=True))
    for perm in all_perms:
        perm_groups.setdefault(perm.module or 'General', []).append({
            'perm': perm,
            'checked': perm.pk in user_perm_ids,
        })

    return render(request, 'accounts/user_permissions.html', {
        'user_obj': user_obj,
        'perm_groups': perm_groups,
        'form': form,
    })


@login_required
def user_eb_access(request: HttpRequest, pk: int) -> HttpResponse:
    """Add or remove EntitasBisnis access for a user. POST only."""
    import json as _json
    from apps.entitas_bisnis.models import EntitasBisnis

    denied = _check_perm(request.user, 'user_manage_permissions')
    if denied:
        return denied
    if request.method != 'POST':
        return HttpResponseForbidden('Method not allowed')

    user_obj = get_object_or_404(User, pk=pk)

    try:
        body = _json.loads(request.body)
        action = body.get('action')
        eb_id = int(body.get('eb_id', 0))
    except (ValueError, TypeError, KeyError, _json.JSONDecodeError):
        from django.http import JsonResponse
        return JsonResponse({'error': 'Invalid request'}, status=400)

    from django.http import JsonResponse
    eb = get_object_or_404(EntitasBisnis, pk=eb_id)

    if action == 'add':
        UserEntitasBisnis.objects.get_or_create(user=user_obj, entitas_bisnis=eb)
        return JsonResponse({'status': 'added', 'eb_id': eb_id, 'eb_nama': eb.nama})

    if action == 'remove':
        UserEntitasBisnis.objects.filter(user=user_obj, entitas_bisnis=eb).delete()
        return JsonResponse({'status': 'removed', 'eb_id': eb_id})

    return JsonResponse({'error': 'Unknown action'}, status=400)
