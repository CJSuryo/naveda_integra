from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages

from apps.accounts.views import _check_perm
from apps.pos_promotions.models import Campaign, Voucher, OrderPromotion
from apps.pos_promotions.forms import CampaignForm
from apps.pos_promotions.services.promotion_service import (
    generate_voucher_codes, validate_voucher, apply_voucher,
)


def campaign_list(request):
    denied = _check_perm(request.user, 'pos.manage_promotions')
    if denied:
        return denied
    merchant_id = request.GET.get('merchant')
    from django.db.models import Count
    campaigns = Campaign.objects.select_related('merchant_config').annotate(
        voucher_count=Count('vouchers')
    ).order_by('-id')
    if merchant_id:
        campaigns = campaigns.filter(merchant_config_id=merchant_id)
    return render(request, 'pos_promotions/campaign_list.html', {'campaigns': campaigns})


def campaign_form(request, pk=None):
    denied = _check_perm(request.user, 'pos.manage_promotions')
    if denied:
        return denied
    campaign = get_object_or_404(Campaign, pk=pk) if pk else None
    from pos_config.models import MerchantPOSConfig
    merchant_id = request.GET.get('merchant') or (campaign.merchant_config_id if campaign else None)
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_id) if merchant_id else None
    if request.method == 'POST':
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            c = form.save(commit=False)
            if not pk:
                c.merchant_config = merchant
            c.save()
            form.save_m2m()
            messages.success(request, 'Campaign berhasil disimpan.')
            return redirect('pos_campaign_list')
    else:
        form = CampaignForm(instance=campaign)
    return render(request, 'pos_promotions/campaign_form.html', {
        'form': form, 'campaign': campaign, 'merchant': merchant,
    })


def voucher_list(request, campaign_pk):
    denied = _check_perm(request.user, 'pos.manage_promotions')
    if denied:
        return denied
    campaign = get_object_or_404(Campaign, pk=campaign_pk)
    vouchers = campaign.vouchers.select_related('used_by').order_by('-created_at')
    return render(request, 'pos_promotions/voucher_list.html', {
        'campaign': campaign, 'vouchers': vouchers,
    })


def voucher_generate(request, campaign_pk):
    denied = _check_perm(request.user, 'pos.manage_promotions')
    if denied:
        return denied
    campaign = get_object_or_404(Campaign, pk=campaign_pk)
    if request.method == 'POST':
        try:
            count = int(request.POST.get('count', 1))
        except (ValueError, TypeError):
            count = 1
        prefix = request.POST.get('prefix', '').upper().strip()
        count = max(1, min(count, 500))
        generate_voucher_codes(campaign, count=count, prefix=prefix)
        messages.success(request, f'{count} kode voucher berhasil dibuat.')
    return redirect('pos_voucher_list', campaign_pk=campaign_pk)


def apply_voucher_ajax(request):
    """POST /pos/promotions/apply-voucher/ {order_pk, code}"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)
    denied = _check_perm(request.user, 'pos.manage_promotions')
    if denied:
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
    from pos_orders.models import Order
    order_pk = request.POST.get('order_pk')
    code = request.POST.get('code', '').strip()
    order = get_object_or_404(Order, pk=order_pk)
    try:
        promo = apply_voucher(code, order)
        order.recalculate_totals()
        return JsonResponse({
            'ok': True,
            'discount': str(promo.discount_amount),
            'description': promo.description,
        })
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)})
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Terjadi kesalahan. Silakan coba lagi.'}, status=500)
