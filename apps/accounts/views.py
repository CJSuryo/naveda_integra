"""Account views."""
from urllib.parse import urlparse

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, RegisterForm


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
