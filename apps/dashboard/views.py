"""Dashboard API views — isolated JSON endpoints per widget, EB-filtered."""
import json
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from apps.inventory.models import InventoryRecord
from apps.jurnal.models import JurnalDetail
from apps.purchase.models import ItemMasterPurchase
from apps.sales.models import SalesItem, SalesItemFIFOAllocation
from apps.utang.models import UtangHeader

from .models import DashboardInventoryTag


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_days(request: HttpRequest, default: int) -> int:
    try:
        days = int(request.GET.get('days', default))
        return days if days in (7, 30, 90) else default
    except (ValueError, TypeError):
        return default


def _parse_eb(request: HttpRequest):
    """Return (eb_id, eb_lv2_id, eb_lv3_id) from GET params."""
    def _int(key):
        try:
            v = int(request.GET.get(key, 0))
            return v if v > 0 else None
        except (ValueError, TypeError):
            return None
    return _int('eb_id'), _int('eb_lv2_id'), _int('eb_lv3_id')


def _date_range(days: int):
    end = timezone.now().date()
    start = end - timedelta(days=days - 1)
    return start, end


def _date_list(start, end) -> list:
    result, current = [], start
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def _sales_q(eb_id, eb_lv2_id, eb_lv3_id) -> Q:
    if eb_lv3_id:
        return Q(sales_eb__entitas_bisnis_lv3_id=eb_lv3_id)
    if eb_lv2_id:
        return Q(sales_eb__entitas_bisnis_lv2_id=eb_lv2_id)
    if eb_id:
        return Q(sales_eb__entitas_bisnis_id=eb_id)
    return Q()


def _jurnal_q(eb_id, *_) -> Q:
    """JurnalHeader only has Lv1 FK."""
    if eb_id:
        return Q(jurnal_header__entitas_bisnis_id=eb_id)
    return Q()


def _inventory_q(eb_id, eb_lv2_id, eb_lv3_id) -> Q:
    if eb_lv3_id:
        return Q(entitas_bisnis_lv3_id=eb_lv3_id)
    if eb_lv2_id:
        return Q(entitas_bisnis_lv2_id=eb_lv2_id)
    if eb_id:
        return Q(entitas_bisnis_id=eb_id)
    return Q()


def _utang_q(eb_id, *_) -> Q:
    """UtangHeader only has Lv1 FK."""
    if eb_id:
        return Q(entitas_bisnis_id=eb_id)
    return Q()


def _sales_q_fifo(eb_id, eb_lv2_id, eb_lv3_id) -> Q:
    """EB filter for SalesItemFIFOAllocation (path through sales_item__sales_eb)."""
    if eb_lv3_id:
        return Q(sales_item__sales_eb__entitas_bisnis_lv3_id=eb_lv3_id)
    if eb_lv2_id:
        return Q(sales_item__sales_eb__entitas_bisnis_lv2_id=eb_lv2_id)
    if eb_id:
        return Q(sales_item__sales_eb__entitas_bisnis_id=eb_id)
    return Q()


def _check_eb_access(request: HttpRequest, eb_id) -> bool:
    """Return True if the requesting user may access this EB."""
    if not eb_id:
        return True
    user = request.user
    if user.is_superuser or getattr(user, 'is_admin', False):
        return True
    from apps.accounts.models import UserEntitasBisnis
    return UserEntitasBisnis.objects.filter(user=user, entitas_bisnis_id=eb_id).exists()


# ── Penjualan Harian ─────────────────────────────────────────────────────────

@login_required
def api_penjualan(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 7)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        SalesItem.objects
        .filter(
            sales_eb__sales_header__tanggal__gte=start,
            sales_eb__sales_header__tanggal__lte=end,
        )
        .filter(_sales_q(eb_id, eb_lv2_id, eb_lv3_id))
        .annotate(tanggal=TruncDate('sales_eb__sales_header__tanggal'))
        .values('tanggal')
        .annotate(nilai_penjualan=Sum('total_sales'), cogs=Sum('cogs_amount'))
        .order_by('tanggal')
    )

    daily: dict = {}
    for row in qs:
        nilai = float(row['nilai_penjualan'] or 0)
        cogs = float(row['cogs'] or 0)
        daily[row['tanggal']] = {'nilai': nilai, 'kotor': nilai - cogs}

    date_list = _date_list(start, end)
    labels = [d.strftime('%d %b') for d in date_list]
    nilai_series = [daily.get(d, {}).get('nilai', 0) for d in date_list]
    kotor_series = [daily.get(d, {}).get('kotor', 0) for d in date_list]

    return JsonResponse({
        'labels': labels,
        'series': {'nilai_penjualan': nilai_series, 'pendapatan_kotor': kotor_series},
        'totals': {'nilai_penjualan': sum(nilai_series), 'pendapatan_kotor': sum(kotor_series)},
    })


# ── Profit Harian ─────────────────────────────────────────────────────────────

@login_required
def api_profit(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 7)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        SalesItem.objects
        .filter(
            sales_eb__sales_header__tanggal__gte=start,
            sales_eb__sales_header__tanggal__lte=end,
        )
        .filter(_sales_q(eb_id, eb_lv2_id, eb_lv3_id))
        .annotate(tanggal=TruncDate('sales_eb__sales_header__tanggal'))
        .values('tanggal')
        .annotate(nilai_penjualan=Sum('total_sales'), cogs=Sum('cogs_amount'))
        .order_by('tanggal')
    )

    daily: dict = {}
    for row in qs:
        nilai = float(row['nilai_penjualan'] or 0)
        cogs = float(row['cogs'] or 0)
        profit = nilai - cogs
        daily[row['tanggal']] = {'profit': profit, 'margin': round(profit / nilai * 100, 1) if nilai > 0 else 0}

    date_list = _date_list(start, end)
    labels = [d.strftime('%d %b') for d in date_list]
    profit_series = [daily.get(d, {}).get('profit', 0) for d in date_list]
    margin_series = [daily.get(d, {}).get('margin', 0) for d in date_list]

    non_zero = [m for m in margin_series if m > 0]
    return JsonResponse({
        'labels': labels,
        'series': {'profit': profit_series, 'margin': margin_series},
        'totals': {
            'total_profit': sum(profit_series),
            'avg_margin': round(sum(non_zero) / len(non_zero), 1) if non_zero else 0,
        },
    })


# ── Pengeluaran Kas Harian ────────────────────────────────────────────────────

@login_required
def api_pengeluaran(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 7)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        JurnalDetail.objects
        .filter(
            jurnal_header__tanggal__gte=start,
            jurnal_header__tanggal__lte=end,
            kredit__gt=0,
            akun__kategori_id='aset',
        )
        .filter(Q(akun__nama__icontains='kas') | Q(akun__nama__icontains='bank'))
        .filter(_jurnal_q(eb_id, eb_lv2_id, eb_lv3_id))
        .annotate(tanggal=TruncDate('jurnal_header__tanggal'))
        .values('tanggal')
        .annotate(total=Sum('kredit'))
        .order_by('tanggal')
    )

    daily = {row['tanggal']: float(row['total'] or 0) for row in qs}
    date_list = _date_list(start, end)
    labels = [d.strftime('%d %b') for d in date_list]
    series = [daily.get(d, 0) for d in date_list]
    total = sum(series)

    return JsonResponse({
        'labels': labels,
        'series': series,
        'totals': {'total': total, 'avg_harian': round(total / days, 2)},
    })


# ── Rata-rata Pengeluaran ─────────────────────────────────────────────────────

@login_required
def api_rata_pengeluaran(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 30)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        JurnalDetail.objects
        .filter(
            jurnal_header__tanggal__gte=start,
            jurnal_header__tanggal__lte=end,
            kredit__gt=0,
            akun__kategori_id='aset',
        )
        .filter(Q(akun__nama__icontains='kas') | Q(akun__nama__icontains='bank'))
        .filter(_jurnal_q(eb_id, eb_lv2_id, eb_lv3_id))
        .annotate(tanggal=TruncDate('jurnal_header__tanggal'))
        .values('tanggal')
        .annotate(total=Sum('kredit'))
        .order_by('tanggal')
    )

    daily_vals = [float(row['total'] or 0) for row in qs]
    total = sum(daily_vals)

    return JsonResponse({
        'avg_harian': round(total / days, 2),
        'total': total,
        'max_harian': max(daily_vals, default=0),
        'hari_aktif': len(daily_vals),
        'days': days,
    })


# ── Top 5 Persediaan Paling Laku ─────────────────────────────────────────────

@login_required
def api_top_persediaan(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 30)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        SalesItem.objects
        .filter(
            sales_eb__sales_header__tanggal__gte=start,
            sales_eb__sales_header__tanggal__lte=end,
        )
        .filter(_sales_q(eb_id, eb_lv2_id, eb_lv3_id))
        .values('item__item_id', 'item__nama')
        .annotate(total_qty=Sum('quantity'), total_nilai=Sum('total_sales'), jumlah_transaksi=Count('id'))
        .order_by('-total_qty')[:5]
    )

    return JsonResponse({'items': [
        {
            'item_id': r['item__item_id'],
            'nama': r['item__nama'],
            'total_qty': float(r['total_qty'] or 0),
            'total_nilai': float(r['total_nilai'] or 0),
            'jumlah_transaksi': r['jumlah_transaksi'],
        } for r in qs
    ]})


# ── Saldo Persediaan Bertag ───────────────────────────────────────────────────

@login_required
def api_saldo_persediaan(request: HttpRequest) -> JsonResponse:
    """Return current stock balance (running total up to today) for tagged items."""
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)
    today = timezone.now().date()

    tag_qs = DashboardInventoryTag.objects.select_related('item')
    if eb_id:
        tag_qs = tag_qs.filter(entitas_bisnis_id=eb_id)
    tagged = list(tag_qs)
    if not tagged:
        return JsonResponse({'rows': []})

    rows = []
    for tag in tagged:
        item = tag.item

        total_in = InventoryRecord.objects.filter(
            item=item,
            tanggal__lte=today,
        ).filter(_inventory_q(eb_id, eb_lv2_id, eb_lv3_id)).aggregate(
            qty=Sum('quantity'), nilai=Sum('total_value'),
        )

        total_out = (
            SalesItemFIFOAllocation.objects
            .filter(inventory_record__item=item)
            .filter(_sales_q_fifo(eb_id, eb_lv2_id, eb_lv3_id))
            .filter(sales_item__sales_eb__sales_header__tanggal__lte=today)
            .aggregate(qty=Sum('quantity_consumed'), nilai=Sum('cogs_amount'))
        )

        qty_saldo = round(max(float(total_in['qty'] or 0) - float(total_out['qty'] or 0), 0), 2)
        nilai_saldo = round(max(float(total_in['nilai'] or 0) - float(total_out['nilai'] or 0), 0), 2)

        rows.append({
            'item_id': item.item_id,
            'nama': item.nama,
            'nilai': nilai_saldo,
            'qty': qty_saldo,
        })

    rows.sort(key=lambda r: r['nilai'], reverse=True)
    return JsonResponse({'rows': rows})


# ── Utang Jatuh Tempo ────────────────────────────────────────────────────────

@login_required
def api_utang(request: HttpRequest) -> JsonResponse:
    page = max(1, int(request.GET.get('page', 1)))
    per_page = 10
    today = timezone.now().date()
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = (
        UtangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'), tanggal_jatuh_tempo__isnull=False)
        .filter(_utang_q(eb_id, eb_lv2_id, eb_lv3_id))
        .order_by('tanggal_jatuh_tempo')
    )

    total = qs.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    rows = []
    for u in qs[offset:offset + per_page]:
        jt = u.tanggal_jatuh_tempo
        days_to_due = (jt - today).days
        rows.append({
            'id': u.pk,
            'nomor_utang': u.nomor_utang,
            'kreditor': u.entitas_display,
            'total_amount': float(u.total_amount),
            'outstanding': float(u.outstanding_amount),
            'tanggal_jatuh_tempo': jt.strftime('%d %b %Y'),
            'days_to_due': days_to_due,
            'status': u.status,
            'is_overdue': days_to_due < 0,
            'due_soon': 0 <= days_to_due <= 7,
        })

    return JsonResponse({'rows': rows, 'pagination': {'page': page, 'total_pages': total_pages, 'total': total}})


# ── Tag Item ─────────────────────────────────────────────────────────────────

@login_required
def api_recent_sales(request: HttpRequest) -> JsonResponse:
    days = _parse_days(request, 7)
    start, end = _date_range(days)
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)
    page = max(1, int(request.GET.get('page', 1)))
    per_page = 10

    qs = (
        SalesItem.objects
        .select_related(
            'sales_eb__sales_header',
            'sales_eb__entitas_bisnis',
            'sales_eb__entitas_bisnis_lv2',
            'sales_eb__entitas_bisnis_lv3',
            'item',
        )
        .filter(
            sales_eb__sales_header__tanggal__gte=start,
            sales_eb__sales_header__tanggal__lte=end,
        )
        .filter(_sales_q(eb_id, eb_lv2_id, eb_lv3_id))
        .order_by('-sales_eb__sales_header__tanggal', '-id')
    )

    total = qs.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    rows = []
    for si in qs[offset:offset + per_page]:
        eb = si.sales_eb
        if eb.entitas_bisnis_lv3:
            eb_label = eb.entitas_bisnis_lv3.nama
        elif eb.entitas_bisnis_lv2:
            eb_label = f'{eb.entitas_bisnis.nama} / {eb.entitas_bisnis_lv2.nama}'
        else:
            eb_label = eb.entitas_bisnis.nama if eb.entitas_bisnis else '-'

        total_sales = float(si.total_sales or 0)
        cogs = float(si.cogs_amount or 0)
        rows.append({
            'tanggal': si.sales_eb.sales_header.tanggal.strftime('%d %b %Y'),
            'item': si.item.nama,
            'item_id': si.item.item_id,
            'qty': float(si.quantity),
            'total': total_sales,
            'hpp': cogs,
            'profit': total_sales - cogs,
            'entitas_bisnis': eb_label,
            'transaction_id': si.sales_eb.sales_header.transaction_id,
        })

    return JsonResponse({
        'rows': rows,
        'pagination': {'page': page, 'total_pages': total_pages, 'total': total},
    })


@login_required
def api_tag_item(request: HttpRequest) -> JsonResponse:
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Request tidak valid'}, status=400)

        eb_id_post = body.get('eb_id')
        eb_id_post = int(eb_id_post) if eb_id_post and str(eb_id_post).isdigit() else None
        from apps.entitas_bisnis.models import EntitasBisnis as _EB

        if body.get('action') == 'save_all':
            item_ids = [int(i) for i in body.get('item_ids', []) if str(i).isdigit()]
            eb_obj = _EB.objects.filter(pk=eb_id_post).first() if eb_id_post else None
            DashboardInventoryTag.objects.filter(entitas_bisnis=eb_obj).delete()
            for item_id in item_ids:
                try:
                    DashboardInventoryTag.objects.create(
                        item=ItemMasterPurchase.objects.get(pk=item_id),
                        entitas_bisnis=eb_obj,
                    )
                except ItemMasterPurchase.DoesNotExist:
                    pass
            return JsonResponse({'status': 'saved', 'count': len(item_ids)})

        try:
            item = ItemMasterPurchase.objects.get(pk=body.get('item_id'))
            eb_obj = _EB.objects.filter(pk=eb_id_post).first() if eb_id_post else None
            tag, created = DashboardInventoryTag.objects.get_or_create(
                item=item, entitas_bisnis=eb_obj
            )
            if not created:
                tag.delete()
                return JsonResponse({'status': 'untagged', 'item_id': item.pk})
            return JsonResponse({'status': 'tagged', 'item_id': item.pk})
        except ItemMasterPurchase.DoesNotExist:
            return JsonResponse({'error': 'Item tidak ditemukan'}, status=404)

    search = request.GET.get('q', '')
    eb_id, eb_lv2_id, eb_lv3_id = _parse_eb(request)

    qs = ItemMasterPurchase.objects.order_by('nama')

    if eb_lv3_id:
        qs = qs.filter(inventory_records__entitas_bisnis_lv3_id=eb_lv3_id)
    elif eb_lv2_id:
        qs = qs.filter(inventory_records__entitas_bisnis_lv2_id=eb_lv2_id)
    elif eb_id:
        qs = qs.filter(inventory_records__entitas_bisnis_id=eb_id)

    qs = qs.distinct()

    if search:
        qs = qs.filter(Q(nama__icontains=search) | Q(item_id__icontains=search))
    tagged_ids = set(
        DashboardInventoryTag.objects
        .filter(entitas_bisnis_id=eb_id)
        .values_list('item_id', flat=True)
    ) if eb_id else set(
        DashboardInventoryTag.objects.filter(entitas_bisnis__isnull=True)
        .values_list('item_id', flat=True)
    )
    return JsonResponse({'items': [
        {'id': i.pk, 'item_id': i.item_id, 'nama': i.nama, 'tipe': i.tipe_item, 'tagged': i.pk in tagged_ids}
        for i in qs[:50]
    ], 'tagged_count': len(tagged_ids)})


# ── Set EB in session ─────────────────────────────────────────────────────────

@login_required
def api_set_eb(request: HttpRequest) -> JsonResponse:
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    eb_id = body.get('eb_id') or None
    eb_lv2_id = body.get('eb_lv2_id') or None
    eb_lv3_id = body.get('eb_lv3_id') or None

    if eb_id and not _check_eb_access(request, eb_id):
        return JsonResponse({'error': 'Akses ditolak untuk entitas bisnis ini'}, status=403)

    request.session['dashboard_eb_id'] = eb_id
    request.session['dashboard_eb_lv2_id'] = eb_lv2_id
    request.session['dashboard_eb_lv3_id'] = eb_lv3_id

    return JsonResponse({'status': 'ok', 'eb_id': eb_id, 'eb_lv2_id': eb_lv2_id, 'eb_lv3_id': eb_lv3_id})


# ── EB cascade options ────────────────────────────────────────────────────────

@login_required
def api_eb_options(request: HttpRequest) -> JsonResponse:
    from apps.entitas_bisnis.models import EntitasBisnisLv2, EntitasBisnisLv3

    eb_id = request.GET.get('eb_id')
    eb_lv2_id = request.GET.get('eb_lv2_id')

    if eb_lv2_id:
        opts = list(
            EntitasBisnisLv3.objects.filter(parent_lv2_id=eb_lv2_id).order_by('nama').values('id', 'nama')
        )
        return JsonResponse({'lv3': opts})

    if eb_id:
        if not _check_eb_access(request, int(eb_id)):
            return JsonResponse({'error': 'Akses ditolak'}, status=403)
        opts = list(
            EntitasBisnisLv2.objects.filter(entitas_bisnis_id=eb_id).order_by('nama').values('id', 'nama')
        )
        return JsonResponse({'lv2': opts})

    return JsonResponse({'error': 'Missing params'}, status=400)
