"""Post an aggregator order into the Sales ledger.

Mirrors the path ``apps/sales/kasir_views.py`` uses for a counter sale, so
delivery revenue lands in exactly the same place as in-store revenue: one
``SalesHeader``, one ``SalesEntitasBisnis`` scoped to lv1/lv2/lv3, one
``SalesItem`` per line, then FIFO allocation and automated journals.

Two deliberate differences from the cashier path:

* **Tax is allocated per line**, not repeated whole on every line. The cashier
  view writes the order-level tax amount onto each ``SalesItem``, which
  multiplies the tax by the number of lines. That is a bug; it is not
  reproduced here.
* **Only merchant-funded discounts reduce revenue.** Promotions funded by the
  aggregator are recorded on the order but do not shrink what the merchant
  earned.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.sales.models import SalesEntitasBisnis, SalesEventLog, SalesHeader, SalesItem
from apps.sales.services import create_sales_automated_journals, process_sales_fifo
from pos_config.utils import resolve_pos_config

from ..models import AggregatorOrder, AggregatorOrderLog

logger = logging.getLogger(__name__)

CENTS = Decimal('0.01')


class PostingError(Exception):
    """Raised when the order cannot be turned into a sale."""


def _allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split ``total`` across ``weights`` so the parts sum exactly to the total.

    Rounding each share independently loses or gains a cent; the remainder is
    pushed onto the largest line so the ledger always balances.
    """
    if total == 0 or not weights:
        return [Decimal('0')] * len(weights)
    weight_sum = sum(weights)
    if weight_sum == 0:
        return [Decimal('0')] * len(weights)

    shares = [
        (total * w / weight_sum).quantize(CENTS, rounding=ROUND_HALF_UP) for w in weights
    ]
    drift = total - sum(shares)
    if drift:
        biggest = max(range(len(shares)), key=lambda i: weights[i])
        shares[biggest] += drift
    return shares


@transaction.atomic
def post_order(order: AggregatorOrder, *, user=None) -> SalesHeader:
    """Create the Sales records for one aggregator order.

    Idempotent: an order already carrying a ``sales_header`` is returned
    untouched, so a retried task cannot double-book revenue.
    """
    order = AggregatorOrder.objects.select_for_update().select_related(
        'store_link__store_config__entitas_bisnis_lv3__parent_lv2',
        'store_link__credential__merchant_config',
    ).get(pk=order.pk)

    if order.sales_header_id:
        return order.sales_header

    if order.has_unmapped_items:
        raise PostingError(
            'Pesanan berisi item yang tidak cocok dengan katalog. Petakan item '
            'tersebut terlebih dahulu sebelum diposting ke penjualan.'
        )

    lines = list(order.items.select_related('item'))
    if not lines:
        raise PostingError('Pesanan tidak memiliki item.')
    if any(line.item_id is None for line in lines):
        raise PostingError('Sebagian item pesanan belum terhubung ke master item.')

    lv3 = order.store_link.store_config.entitas_bisnis_lv3
    cfg = resolve_pos_config(lv3)

    missing = [
        label for label, value in (
            ('Sub-Transaction Type', cfg['sub_transaction_type_id']),
            ('Revenue Account', cfg['revenue_account_id']),
            ('HPP Account', cfg['offset_coa_account_id']),
        ) if not value
    ]
    if missing:
        raise PostingError(
            'Konfigurasi POS belum lengkap untuk cabang '
            f'{lv3.nama}: {", ".join(missing)}.'
        )

    header = SalesHeader.objects.create(
        tanggal=(order.placed_at or timezone.now()).date(),
        deskripsi=(
            f'{order.get_aggregator_display()} — {lv3.nama} — '
            f'#{order.short_order_number or order.external_order_id}'
        ),
        created_by=user,
    )

    eb_group = SalesEntitasBisnis.objects.create(
        sales_header=header,
        entitas_bisnis_id=lv3.parent_lv2.entitas_bisnis_id,
        entitas_bisnis_lv2_id=lv3.parent_lv2_id,
        entitas_bisnis_lv3_id=lv3.pk,
        payment_account_id=cfg['payment_account_id'],
    )

    weights = [line.line_total for line in lines]
    tax_shares = _allocate(order.tax_amount, weights)
    discount_shares = _allocate(order.merchant_funded_discount, weights)

    for line, tax_share, discount_share in zip(lines, tax_shares, discount_shares):
        # Net the merchant-funded discount into the unit price so revenue
        # reflects what the merchant actually earned on this line.
        gross = line.unit_price + (
            line.modifier_total / line.quantity if line.quantity else Decimal('0')
        )
        net_unit = gross - (
            discount_share / line.quantity if line.quantity else Decimal('0')
        )
        SalesItem.objects.create(
            sales_eb=eb_group,
            item_id=line.item_id,
            sub_transaction_type_id=cfg['sub_transaction_type_id'],
            quantity=line.quantity,
            selling_price=max(Decimal('0'), net_unit).quantize(CENTS, rounding=ROUND_HALF_UP),
            offset_coa_account_id=cfg['offset_coa_account_id'],
            revenue_account_id=cfg['revenue_account_id'],
            payment_account_id=cfg['payment_account_id'],
            inventory_account_id=line.item.coa_account_id,
            tax=tax_share if tax_share else None,
            tax_type='ppn_keluaran' if tax_share else '',
        )

    SalesEventLog.objects.create(
        sales_header=header, event_type='CREATED',
        description=(
            f'Pesanan {order.get_aggregator_display()} '
            f'#{order.short_order_number or order.external_order_id}'
        ),
        actor=user,
    )

    process_sales_fifo(header)
    SalesEventLog.objects.create(sales_header=header, event_type='FIFO_PROCESSED', actor=None)

    create_sales_automated_journals(header, user=user)
    SalesEventLog.objects.create(sales_header=header, event_type='JOURNAL_CREATED', actor=None)

    order.sales_header = header
    order.posted_at = timezone.now()
    order.posting_error = ''
    order.save(update_fields=['sales_header', 'posted_at', 'posting_error', 'updated_at'])

    AggregatorOrderLog.objects.create(
        order=order, action='POSTED_TO_SALES',
        detail=f'SalesHeader #{header.pk}', actor=user,
    )
    return header
