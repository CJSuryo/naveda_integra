"""Account views."""
from urllib.parse import urlparse

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, RegisterForm


def _get_safe_next(request: HttpRequest) -> str | None:
    """Return a validated, path-only next URL or None."""
    next_url = request.GET.get('next', '')
    if not next_url:
        return None
    if not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    # Extract only the path+query to avoid open-redirect via full URL
    parsed = urlparse(next_url)
    safe = parsed.path
    if parsed.query:
        safe += '?' + parsed.query
    return safe or None


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
