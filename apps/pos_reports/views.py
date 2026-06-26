import datetime
import json
from decimal import Decimal

from naveda_integra.json_utils import safe_json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse

from apps.accounts.views import _check_perm
from pos_config.models import StorePOSConfig
from apps.pos_reports.services.report_service import (
    get_sales_summary, get_top_products, get_payment_breakdown,
    get_laba_rugi, generate_daily_snapshot,
)
from apps.pos_reports.models import DailySalesSnapshot


def _parse_date_range(request, default_days=30):
    today = datetime.date.today()
    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')
    try:
        date_from = datetime.date.fromisoformat(date_from_str) if date_from_str else today - datetime.timedelta(days=default_days)
        date_to = datetime.date.fromisoformat(date_to_str) if date_to_str else today
    except ValueError:
        date_from = today - datetime.timedelta(days=default_days)
        date_to = today
    return date_from, date_to


def _dec(v):
    return float(v) if v is not None else 0.0


def dashboard(request):
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    store_id = request.GET.get('store')
    if not store_id:
        stores = StorePOSConfig.objects.select_related('entitas_bisnis_lv2').filter(is_active=True)
        return render(request, 'pos_reports/store_select.html', {'stores': stores})
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    today = datetime.date.today()
    date_from = today - datetime.timedelta(days=29)
    summary = get_sales_summary(store, date_from, today)
    top = get_top_products(store, date_from, today, limit=5)
    breakdown = get_payment_breakdown(store, date_from, today)
    laba = get_laba_rugi(store, date_from, today)

    snapshots = DailySalesSnapshot.objects.filter(
        store=store,
        date__gte=date_from,
        date__lte=today,
    ).order_by('date')
    chart_labels = [str(s.date) for s in snapshots]
    chart_net_sales = [_dec(s.net_sales) for s in snapshots]
    chart_orders = [s.total_orders for s in snapshots]

    return render(request, 'pos_reports/dashboard.html', {
        'store': store,
        'date_from': date_from,
        'date_to': today,
        'summary': summary,
        'top_products': top,
        'payment_breakdown': breakdown,
        'laba_rugi': laba,
        'chart_labels': safe_json(chart_labels),
        'chart_net_sales': safe_json(chart_net_sales),
        'chart_orders': safe_json(chart_orders),
        'chart_payment_labels': safe_json(list(breakdown.keys())),
        'chart_payment_amounts': safe_json([_dec(v) for v in breakdown.values()]),
    })


def daily_report(request):
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    store_id = request.GET.get('store')
    store = get_object_or_404(StorePOSConfig, pk=store_id) if store_id else None
    date_from, date_to = _parse_date_range(request, default_days=7)
    summary = get_sales_summary(store, date_from, date_to) if store else None
    snapshots = []
    if store:
        snapshots = DailySalesSnapshot.objects.filter(
            store=store, date__gte=date_from, date__lte=date_to,
        ).order_by('-date')
    return render(request, 'pos_reports/daily.html', {
        'store': store,
        'date_from': date_from,
        'date_to': date_to,
        'summary': summary,
        'snapshots': snapshots,
    })


def top_products_report(request):
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    store_id = request.GET.get('store')
    store = get_object_or_404(StorePOSConfig, pk=store_id) if store_id else None
    date_from, date_to = _parse_date_range(request, default_days=30)
    top = get_top_products(store, date_from, date_to, limit=20) if store else []
    chart_labels = safe_json([p.pos_name for p, _, _ in top])
    chart_revenue = safe_json([_dec(rev) for _, _, rev in top])
    return render(request, 'pos_reports/top_products.html', {
        'store': store,
        'date_from': date_from,
        'date_to': date_to,
        'top_products': top,
        'chart_labels': chart_labels,
        'chart_revenue': chart_revenue,
    })


def payment_breakdown_report(request):
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    store_id = request.GET.get('store')
    store = get_object_or_404(StorePOSConfig, pk=store_id) if store_id else None
    date_from, date_to = _parse_date_range(request, default_days=30)
    breakdown = get_payment_breakdown(store, date_from, date_to) if store else {}
    chart_labels = safe_json(list(breakdown.keys()))
    chart_amounts = safe_json([_dec(v) for v in breakdown.values()])
    return render(request, 'pos_reports/payment_breakdown.html', {
        'store': store,
        'date_from': date_from,
        'date_to': date_to,
        'breakdown': breakdown,
        'chart_labels': chart_labels,
        'chart_amounts': chart_amounts,
    })


def laba_rugi_report(request):
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    store_id = request.GET.get('store')
    store = get_object_or_404(StorePOSConfig, pk=store_id) if store_id else None
    date_from, date_to = _parse_date_range(request, default_days=30)
    laba = get_laba_rugi(store, date_from, date_to) if store else None
    return render(request, 'pos_reports/laba_rugi.html', {
        'store': store,
        'date_from': date_from,
        'date_to': date_to,
        'laba_rugi': laba,
    })


def snapshot_trigger(request):
    """POST — manually trigger daily snapshot for today."""
    denied = _check_perm(request.user, 'pos_reports_view')
    if denied:
        return denied
    if request.method != 'POST':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    store_id = request.POST.get('store')
    store = get_object_or_404(StorePOSConfig, pk=store_id)
    snap = generate_daily_snapshot(store, datetime.date.today())
    return JsonResponse({'ok': True, 'total_orders': snap.total_orders, 'net_sales': str(snap.net_sales)})
