"""Wizard and order-board views.

Every view resolves its objects through ``accessible_merchant_qs`` /
``accessible_store_qs`` so a user cannot reach another tenant's channel by
guessing an id.

Permission split, matching the risk of each action:

* ``pos_aggregators_manage`` — everyday operator steps: connect, link a branch,
  publish the menu, run checks, go live.
* ``pos_config_manage`` — additionally required to enter or rotate secrets.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.views import _check_perm
from pos_config.access import accessible_lv2_qs, accessible_merchant_qs, accessible_store_qs
from pos_config.models import MerchantPOSConfig, StorePOSConfig

from .constants import AggregatorType, OnboardingState, OrderStatus
from .forms import (
    ChannelSettingsForm, ConnectChannelForm, CredentialSecretsForm, ManualStoreLinkForm,
)
from .models import (
    AggregatorCredential, AggregatorOrder, AggregatorStoreLink, WebhookEvent,
)
from .services import onboarding

logger = logging.getLogger(__name__)


def _get_credential(request, pk) -> AggregatorCredential:
    return get_object_or_404(
        AggregatorCredential.objects.select_related(
            'merchant_config__entitas_bisnis_lv2', 'onboarding'
        ).filter(merchant_config__in=accessible_merchant_qs(request.user)),
        pk=pk,
    )


@login_required
def channel_list(request, lv2_pk):
    """All delivery channels for one operating company."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    lv2 = get_object_or_404(
        accessible_lv2_qs(request.user).select_related('entitas_bisnis'), pk=lv2_pk
    )
    # The channel list is the entry point before any config exists yet, so the
    # merchant row is created on first visit rather than 404ing for a company
    # that hasn't touched POS/aggregator setup before.
    merchant, _ = MerchantPOSConfig.objects.get_or_create(entitas_bisnis_lv2=lv2)

    existing = {c.aggregator: c for c in merchant.aggregator_credentials.select_related('onboarding')}
    channels = []
    for value, label in AggregatorType.choices:
        credential = existing.get(value)
        session = getattr(credential, 'onboarding', None) if credential else None
        channels.append({
            'value': value,
            'label': label,
            'credential': credential,
            'session': session,
            'state_label': session.get_state_display() if session else 'Belum Dimulai',
            'is_live': bool(session and session.state == OnboardingState.LIVE),
            'store_count': (
                credential.store_links.exclude(external_store_id='').count()
                if credential else 0
            ),
        })

    return render(request, 'pos_aggregator/channel_list.html', {
        'lv2': lv2, 'merchant': merchant, 'channels': channels,
    })


@login_required
def channel_connect(request, lv2_pk):
    """Create the credential row for a chosen channel, then open the wizard."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    lv2 = get_object_or_404(accessible_lv2_qs(request.user), pk=lv2_pk)
    merchant, _ = MerchantPOSConfig.objects.get_or_create(entitas_bisnis_lv2=lv2)

    if request.method == 'POST':
        form = ConnectChannelForm(request.POST)
        if form.is_valid():
            credential, _ = AggregatorCredential.objects.get_or_create(
                merchant_config=merchant,
                aggregator=form.cleaned_data['aggregator'],
                defaults={
                    'country': form.cleaned_data['country'],
                    'environment': form.cleaned_data['environment'],
                },
            )
            credential.country = form.cleaned_data['country']
            credential.environment = form.cleaned_data['environment']
            credential.save(update_fields=['country', 'environment', 'updated_at'])
            onboarding.get_or_create_session(credential, request.user)
            return redirect('pos_aggregator:wizard', pk=credential.pk)
    else:
        form = ConnectChannelForm()

    return render(request, 'pos_aggregator/channel_connect.html', {
        'lv2': lv2, 'merchant': merchant, 'form': form,
    })


@login_required
def wizard(request, pk):
    """The stepper. One decision per screen, state held server-side."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    merchant = credential.merchant_config
    lv2 = merchant.entitas_bisnis_lv2

    branches = list(
        StorePOSConfig.objects
        .filter(merchant_config=merchant)
        .select_related('entitas_bisnis_lv3')
        .order_by('entitas_bisnis_lv3__nama')
    )
    links = {
        link.store_config_id: link
        for link in credential.store_links.select_related('store_config')
    }

    template = None
    template_error = ''
    try:
        template = credential.template
    except Exception as exc:
        template_error = str(exc)

    return render(request, 'pos_aggregator/wizard.html', {
        'credential': credential,
        'session': session,
        'merchant': merchant,
        'lv2': lv2,
        'template': template,
        'template_error': template_error,
        'branches': [
            {'store': branch, 'link': links.get(branch.pk)} for branch in branches
        ],
        'settings_form': ChannelSettingsForm(instance=credential),
        'secrets_form': CredentialSecretsForm(),
        'manual_link_form': ManualStoreLinkForm(),
        'preflight': session.preflight_results or [],
        'states': OnboardingState,
        'can_manage_secrets': request.user.has_ni_perm('pos_config_manage'),
        'webhook_subscriptions': credential.webhook_subscriptions.all(),
    })


@login_required
@require_POST
def save_secrets(request, pk):
    """Restricted: enter or rotate the aggregator-issued secrets."""
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    form = CredentialSecretsForm(request.POST)
    if form.is_valid():
        form.apply_to(credential)
        messages.success(request, 'Kredensial tersimpan (terenkripsi).')
    else:
        messages.error(request, 'Kredensial tidak valid.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def save_settings(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    form = ChannelSettingsForm(request.POST, instance=credential)
    if form.is_valid():
        form.save()
        messages.success(request, 'Pengaturan channel disimpan.')
    else:
        messages.error(request, 'Pengaturan tidak valid.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def confirm_prerequisites(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied
    credential = _get_credential(request, pk)
    onboarding.confirm_prerequisites(onboarding.get_or_create_session(credential, request.user))
    messages.success(request, 'Prasyarat dikonfirmasi.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def begin_connect(request, pk):
    """Start account connection: redirect to the aggregator, or show a form."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    try:
        action = onboarding.begin_connect(session)
    except onboarding.OnboardingError as exc:
        messages.error(request, str(exc))
        return redirect('pos_aggregator:wizard', pk=pk)

    if action.kind == 'redirect' and action.redirect_url:
        request.session['aggregator_onboarding_pk'] = credential.pk
        return redirect(action.redirect_url)

    if action.kind == 'form':
        # No consent flow: connecting means validating stored credentials.
        try:
            onboarding.complete_connect(session, {})
            messages.success(request, 'Akun terhubung.')
        except Exception as exc:
            messages.error(request, f'Gagal menghubungkan: {exc}')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
def oauth_callback(request):
    """Return leg of the merchant-consent redirect.

    The ``state`` nonce is verified before the code is exchanged, so a captured
    or forged redirect cannot attach someone else's account.
    """
    credential_pk = request.session.get('aggregator_onboarding_pk')
    if not credential_pk:
        messages.error(request, 'Sesi menghubungkan akun sudah berakhir. Ulangi prosesnya.')
        return redirect('home')

    credential = _get_credential(request, credential_pk)
    session = onboarding.get_or_create_session(credential, request.user)

    error = request.GET.get('error')
    if error:
        messages.error(
            request,
            f'Aggregator menolak permintaan: {request.GET.get("error_description", error)}',
        )
        return redirect('pos_aggregator:wizard', pk=credential.pk)

    try:
        onboarding.verify_oauth_state(session, request.GET.get('state', ''))
        onboarding.complete_connect(session, {'code': request.GET.get('code', '')})
        messages.success(request, 'Akun berhasil terhubung.')
    except Exception as exc:
        session.last_error = str(exc)
        session.save(update_fields=['last_error', 'updated_at'])
        messages.error(request, f'Gagal menghubungkan akun: {exc}')
    finally:
        request.session.pop('aggregator_onboarding_pk', None)

    return redirect('pos_aggregator:wizard', pk=credential.pk)


@login_required
@require_POST
def register_webhooks(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    try:
        subs = onboarding.register_webhooks(session)
    except Exception as exc:
        messages.error(request, f'Pendaftaran webhook gagal: {exc}')
        return redirect('pos_aggregator:wizard', pk=pk)

    if not subs:
        messages.info(request, 'Channel ini tidak memerlukan pendaftaran webhook.')
    else:
        failed = [s for s in subs if s.status == 'FAILED']
        if failed:
            messages.warning(
                request,
                f'{len(subs) - len(failed)} dari {len(subs)} webhook terdaftar. '
                'Tekan "Daftarkan Ulang" sekali lagi untuk memperbaiki sisanya.',
            )
        else:
            messages.success(request, f'{len(subs)} webhook terdaftar.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
def outlet_picker(request, pk):
    """Outlets discovered on the merchant's account, for matching to branches."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    try:
        outlets = onboarding.discover_outlets(session)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    return JsonResponse({
        'ok': True,
        'outlets': [
            {
                'external_id': o.external_id, 'name': o.name,
                'address': o.address, 'phone': o.phone,
            }
            for o in outlets
        ],
    })


@login_required
@require_POST
def link_branch(request, pk, store_pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    store = get_object_or_404(
        accessible_store_qs(request.user), pk=store_pk, merchant_config=credential.merchant_config
    )
    session = onboarding.get_or_create_session(credential, request.user)

    try:
        onboarding.link_store(
            session, store,
            request.POST.get('external_store_id', ''),
            name=request.POST.get('external_store_name', ''),
            address=request.POST.get('external_store_address', ''),
        )
        messages.success(
            request, f'Cabang {store.entitas_bisnis_lv3.nama} terhubung.'
        )
    except onboarding.OnboardingError as exc:
        messages.error(request, str(exc))
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def activate_branch(request, pk, store_pk):
    """GrabFood self-activation: ask Grab for the merchant approval URL."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    store = get_object_or_404(
        accessible_store_qs(request.user), pk=store_pk, merchant_config=credential.merchant_config
    )
    from .adapters import get_adapter
    from .constants import LinkStatus

    link, _ = AggregatorStoreLink.objects.get_or_create(
        store_config=store, aggregator=credential.aggregator,
        defaults={'credential': credential, 'status': LinkStatus.PENDING},
    )
    try:
        result = get_adapter(credential).link_store(link)
    except Exception as exc:
        messages.error(request, f'Gagal meminta aktivasi: {exc}')
        return redirect('pos_aggregator:wizard', pk=pk)

    link.status = LinkStatus.PENDING
    link.save(update_fields=['status', 'updated_at'])
    url = result.get('activationURL') or result.get('url', '')
    if url:
        return redirect(url)
    messages.info(
        request,
        'Permintaan aktivasi dikirim. Status akan berubah otomatis setelah '
        'aggregator memproses — jangan tekan Aktifkan lagi.',
    )
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def unlink_branch(request, pk, link_pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied
    credential = _get_credential(request, pk)
    link = get_object_or_404(AggregatorStoreLink, pk=link_pk, credential=credential)
    onboarding.unlink_store(link)
    messages.success(request, 'Cabang diputus dari aggregator.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def sync_menus(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    results = onboarding.sync_menus(session)
    failures = [r for r in results.values() if not r['ok']]
    if not results:
        messages.warning(request, 'Belum ada cabang terhubung — hubungkan cabang dulu.')
    elif failures:
        messages.error(request, failures[0]['error'])
    else:
        messages.success(request, f'Menu {len(results)} cabang terkirim.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def run_checks(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    results = onboarding.run_checks(session)
    failed = [r for r in results if not r.passed]
    if failed:
        messages.warning(request, f'{len(failed)} pemeriksaan belum lolos.')
    else:
        messages.success(request, 'Semua pemeriksaan lolos. Channel siap go live.')
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def go_live(request, pk):
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    try:
        onboarding.go_live(session)
        messages.success(
            request,
            'Channel aktif. Lakukan satu pesanan uji dari aplikasi aggregator '
            'untuk memastikan pesanan benar-benar masuk.',
        )
    except onboarding.OnboardingError as exc:
        messages.error(request, str(exc))
    return redirect('pos_aggregator:wizard', pk=pk)


@login_required
@require_POST
def disconnect(request, pk):
    denied = _check_perm(request.user, 'pos_config_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    session = onboarding.get_or_create_session(credential, request.user)
    onboarding.disconnect(session)
    messages.success(request, 'Channel diputus. Pesanan baru tidak akan masuk lagi.')
    return redirect('pos_aggregator:wizard', pk=pk)


# ── Order board ─────────────────────────────────────────────────────────────

@login_required
def order_board(request, store_pk):
    """Live incoming orders for one branch."""
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied

    store = get_object_or_404(accessible_store_qs(request.user), pk=store_pk)
    orders = (
        AggregatorOrder.objects
        .filter(store_link__store_config=store)
        .exclude(status=OrderStatus.COMPLETED)
        .select_related('store_link')
        .prefetch_related('items')
        .order_by('-created_at')[:100]
    )
    return render(request, 'pos_aggregator/order_board.html', {
        'store': store, 'orders': orders,
    })


@login_required
def order_detail(request, order_pk):
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied

    order = get_object_or_404(
        AggregatorOrder.objects
        .filter(store_link__store_config__in=accessible_store_qs(request.user))
        .select_related('store_link__store_config__entitas_bisnis_lv3', 'sales_header')
        .prefetch_related('items__modifiers', 'logs'),
        pk=order_pk,
    )
    return render(request, 'pos_aggregator/order_detail.html', {'order': order})


@login_required
@require_POST
def mark_order_ready(request, order_pk):
    """Tell the aggregator the food is ready, where the channel supports it."""
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied

    order = get_object_or_404(
        AggregatorOrder.objects.filter(
            store_link__store_config__in=accessible_store_qs(request.user)
        ),
        pk=order_pk,
    )
    from .services.ingest import _transition
    from .tasks import push_order_status_task

    if order.can_advance_to(OrderStatus.READY):
        _transition(order, OrderStatus.READY, order.external_status, 'MARKED_READY')
        push_order_status_task.delay(order.pk, int(OrderStatus.READY))
        messages.success(request, 'Pesanan ditandai siap.')
    else:
        messages.info(request, 'Status pesanan tidak dapat diubah ke "siap".')
    return redirect('pos_aggregator:order_detail', order_pk=order_pk)


@login_required
@require_POST
def repost_order(request, order_pk):
    """Retry Sales posting after fixing whatever blocked it."""
    denied = _check_perm(request.user, 'pos_orders_manage')
    if denied:
        return denied

    order = get_object_or_404(
        AggregatorOrder.objects.filter(
            store_link__store_config__in=accessible_store_qs(request.user)
        ),
        pk=order_pk,
    )
    from .services.sales_posting import PostingError, post_order
    try:
        post_order(order, user=request.user)
        messages.success(request, 'Pesanan berhasil dibukukan ke penjualan.')
    except PostingError as exc:
        messages.error(request, str(exc))
    return redirect('pos_aggregator:order_detail', order_pk=order_pk)


@login_required
def webhook_log(request, pk):
    """Recent deliveries — the first place to look when orders stop arriving."""
    denied = _check_perm(request.user, 'pos_aggregators_manage')
    if denied:
        return denied

    credential = _get_credential(request, pk)
    events = WebhookEvent.objects.filter(aggregator=credential.aggregator)[:100]
    return render(request, 'pos_aggregator/webhook_log.html', {
        'credential': credential, 'events': events,
    })
