"""Kasir POS views — full-screen cashier screen and its JSON APIs."""
import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.entitas_bisnis.models import EntitasBisnisLv3
from pos_catalog.models import ProductModifierGroup
from apps.inventory.models import InventoryRecord
from apps.purchase.models import ItemMasterPurchase, SubTransactionType

from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesEventLog
from .services import process_sales_fifo, create_sales_automated_journals


@login_required
def kasir_pos(request: HttpRequest) -> HttpResponse:
    """Full-screen standalone POS page at /kasir/."""
    stores = (
        EntitasBisnisLv3.objects
        .filter(status_aktif=True)
        .select_related('parent_lv2__entitas_bisnis')
        .order_by('nama')
    )
    return render(request, 'kasir/pos.html', {'stores': stores})


@login_required
def api_kasir_config(request: HttpRequest, lv3_pk: int) -> JsonResponse:
    """Return resolved POS config for a lv3 outlet."""
    try:
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=lv3_pk, status_aktif=True)
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Store not found'}, status=404)

    from apps.pos_config.utils import resolve_pos_config
    cfg = resolve_pos_config(lv3)

    brand_name = lv3.parent_lv2.entitas_bisnis.nama if lv3.parent_lv2 else 'Naveda'

    return JsonResponse({
        'ok': True,
        'lv3_pk': lv3.pk,
        'store_name': lv3.parent_lv2.nama if lv3.parent_lv2 else '',
        'outlet_name': lv3.nama,
        'brand_name': brand_name,
        'tax_pct': str(cfg['tax_pct']),
        'sub_transaction_type_id': cfg['sub_transaction_type_id'],
        'revenue_account_id': cfg['revenue_account_id'],
        'offset_coa_account_id': cfg['offset_coa_account_id'],
        'payment_account_id': cfg['payment_account_id'],
        'qris_image_url': cfg['qris_image_url'],
        'cashier_name': request.user.get_full_name() or request.user.username,
    })


@login_required
def api_kasir_catalog(request: HttpRequest) -> JsonResponse:
    """Return inventory items + modifier groups for a lv3 store."""
    try:
        lv3_pk = int(request.GET.get('lv3_pk', ''))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'items': []})

    try:
        lv3 = EntitasBisnisLv3.objects.select_related('parent_lv2__entitas_bisnis').get(
            pk=lv3_pk, status_aktif=True,
        )
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'items': []})

    inv_qs = (
        InventoryRecord.objects
        .filter(entitas_bisnis_lv3_id=lv3_pk, quantity__gt=0)
        .exclude(item__tipe_item__in=['RMB', 'FGB', 'ITMB'])
        .select_related('item__kategori')
        .order_by('item__kategori__nama', 'item__nama')
    )
    if not inv_qs.exists():
        lv1_id = lv3.parent_lv2.entitas_bisnis_id
        inv_qs = (
            InventoryRecord.objects
            .filter(entitas_bisnis_id=lv1_id, quantity__gt=0)
            .exclude(item__tipe_item__in=['RMB', 'FGB', 'ITMB'])
            .select_related('item__kategori')
            .order_by('item__kategori__nama', 'item__nama')
        )

    item_ids = list(inv_qs.values_list('item_id', flat=True).distinct())
    modifier_map: dict[int, list] = {}
    for pmg in (
        ProductModifierGroup.objects
        .filter(item_id__in=item_ids)
        .select_related('modifier_group')
        .prefetch_related('modifier_group__options')
    ):
        modifier_map.setdefault(pmg.item_id, []).append({
            'pk': pmg.modifier_group_id,
            'nama': pmg.modifier_group.name,
            'is_required': pmg.modifier_group.is_required,
            'min_selections': pmg.modifier_group.min_selections,
            'max_selections': pmg.modifier_group.max_selections,
            'options': [
                {
                    'pk': opt.pk,
                    'name': opt.name,
                    'additional_price': str(opt.additional_price),
                    'is_default': opt.is_default,
                }
                for opt in pmg.modifier_group.options.all()
                if opt.is_available
            ],
        })

    seen: set[int] = set()
    items_data = []
    for inv in inv_qs:
        if inv.item_id in seen:
            continue
        seen.add(inv.item_id)
        items_data.append({
            'item_pk': inv.item_id,
            'name': inv.item.nama,
            'kode_item': inv.item.item_id,
            'selling_price': str(inv.selling_price) if inv.selling_price is not None else '0',
            'category': inv.item.kategori.nama.lower().replace(' ', '') if inv.item.kategori else 'other',
            'category_label': inv.item.kategori.nama if inv.item.kategori else 'Lainnya',
            'modifier_groups': modifier_map.get(inv.item_id, []),
        })

    categories = []
    seen_cats: list[str] = []
    for it in items_data:
        if it['category'] not in seen_cats:
            seen_cats.append(it['category'])
            categories.append({'id': it['category'], 'label': it['category_label']})

    return JsonResponse({'ok': True, 'items': items_data, 'categories': categories})


@login_required
@require_POST
def api_kasir_submit(request: HttpRequest) -> JsonResponse:
    """Submit a POS sale. Creates SalesHeader + SalesItems, runs FIFO + journals."""
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    lv3_pk = body.get('lv3_pk')
    cart = body.get('cart', [])
    tender = body.get('tender', 'cash')
    tendered_amount = body.get('tendered_amount', 0)
    discount_data = body.get('discount')

    if not lv3_pk or not cart:
        return JsonResponse({'ok': False, 'error': 'lv3_pk and cart required'}, status=400)

    try:
        lv3 = EntitasBisnisLv3.objects.select_related(
            'parent_lv2__entitas_bisnis__pos_config',
            'parent_lv2__pos_config',
            'pos_config',
        ).get(pk=int(lv3_pk), status_aktif=True)
    except EntitasBisnisLv3.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Store not found'}, status=404)

    from apps.pos_config.utils import resolve_pos_config
    cfg = resolve_pos_config(lv3)

    stt_id = cfg['sub_transaction_type_id']
    revenue_id = cfg['revenue_account_id']
    offset_id = cfg['offset_coa_account_id']
    payment_id = cfg['payment_account_id']
    tax_pct = cfg['tax_pct']

    if not stt_id:
        return JsonResponse({'ok': False, 'error': 'Sub-Transaction Type belum dikonfigurasi untuk outlet ini.'}, status=400)
    if not revenue_id or not offset_id:
        return JsonResponse({'ok': False, 'error': 'Revenue atau HPP account belum dikonfigurasi.'}, status=400)

    subtotal = Decimal('0')
    for line in cart:
        try:
            unit_price = Decimal(str(line.get('unit_price', 0)))
            qty = Decimal(str(line.get('qty', 1)))
            subtotal += unit_price * qty
        except (InvalidOperation, ValueError):
            return JsonResponse({'ok': False, 'error': 'Invalid price in cart line'}, status=400)

    if discount_data:
        disc_type = discount_data.get('type')
        disc_val = Decimal(str(discount_data.get('val', 0)))
        if disc_type == 'pct':
            disc_amt = round(subtotal * disc_val / 100)
        else:
            disc_amt = min(disc_val, subtotal)
    else:
        disc_amt = Decimal('0')

    taxed_base = max(Decimal('0'), subtotal - disc_amt)
    tax_amount = round(taxed_base * tax_pct / 100)
    grand_total = taxed_base + tax_amount
    change = Decimal(str(tendered_amount)) - grand_total if tender == 'cash' else Decimal('0')

    tanggal = timezone.now().date()

    try:
        with transaction.atomic():
            sales = SalesHeader.objects.create(
                tanggal=tanggal,
                deskripsi=f'POS — {lv3.nama} — {tender.upper()}',
                created_by=request.user,
            )

            lv1_id = lv3.parent_lv2.entitas_bisnis_id
            lv2_id = lv3.parent_lv2_id
            eb_group = SalesEntitasBisnis.objects.create(
                sales_header=sales,
                entitas_bisnis_id=lv1_id,
                entitas_bisnis_lv2_id=lv2_id,
                entitas_bisnis_lv3_id=lv3.pk,
                payment_account_id=None,
            )

            for line in cart:
                item_pk = line.get('item_pk')
                qty = Decimal(str(line.get('qty', 1)))
                unit_price = Decimal(str(line.get('unit_price', 0)))

                try:
                    item_obj = ItemMasterPurchase.objects.only('tipe_item', 'coa_account_id').get(pk=int(item_pk))
                except (ItemMasterPurchase.DoesNotExist, ValueError, TypeError):
                    raise ValueError(f'Item {item_pk} not found')

                SalesItem.objects.create(
                    sales_eb=eb_group,
                    item_id=int(item_pk),
                    sub_transaction_type_id=stt_id,
                    quantity=qty,
                    selling_price=unit_price,
                    offset_coa_account_id=offset_id,
                    revenue_account_id=revenue_id,
                    payment_account_id=payment_id,
                    inventory_account_id=item_obj.coa_account_id,
                    tax=tax_amount if tax_amount else None,
                    tax_type='ppn_keluaran' if tax_amount else '',
                )

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='CREATED',
                description=f'POS sale via {tender.upper()}',
                actor=request.user,
            )

            process_sales_fifo(sales)

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='FIFO_PROCESSED',
                actor=None,
            )

            create_sales_automated_journals(sales)

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='JOURNAL_CREATED',
                actor=None,
            )

            SalesEventLog.objects.create(
                sales_header=sales,
                event_type='PAYMENT_PROCESSED',
                description=f'Metode: {tender.upper()}, Bayar: {tendered_amount}, Kembalian: {change}',
                actor=request.user,
            )

    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'Server error: {str(e)}'}, status=500)

    return JsonResponse({
        'ok': True,
        'trx_id': sales.transaction_id,
        'grand_total': str(grand_total),
        'change': str(change),
    })
