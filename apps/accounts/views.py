"""Account views."""
from urllib.parse import urlparse

from django.contrib import messages as dj_messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, RegisterForm, UserForm, UserPermissionForm
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


def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('accounts:login')


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
def home_view(request: HttpRequest) -> HttpResponse:
    return render(request, 'home.html')


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

    # User's entitas bisnis links
    user_ebs = UserEntitasBisnis.objects.filter(user=user_obj).select_related('entitas_bisnis')

    return render(request, 'accounts/user_detail.html', {
        'user_obj': user_obj,
        'perm_groups': perm_groups,
        'user_ebs': user_ebs,
    })


@login_required
def user_create(request: HttpRequest) -> HttpResponse:
    """Create a new user."""
    denied = _check_perm(request.user, 'user_create')
    if denied:
        return denied
    form = UserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user_obj = form.save()
        dj_messages.success(request, f'User {user_obj.email} berhasil dibuat.')
        return redirect('accounts:user_detail', pk=user_obj.pk)
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Tambah User'})


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
    return render(request, 'accounts/user_confirm_delete.html', {'user_obj': user_obj})


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
