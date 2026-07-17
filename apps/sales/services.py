"""Sales services — FIFO outflow, automated journal generation, and inventory updates."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.purchase.models import FIFOBatch
from apps.inventory.models import InventoryRecord
from apps.pajak.models import PajakTransaksi
from apps.pajak.services import (
    sync_pajak,
    confirm_pajak as confirm_pajak_trx,
    batal_pajak as batal_pajak_trx,
)

from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesTaxLine, SalesItemFIFOAllocation


TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23':       'pph_23_jasa',
    'pph_21':       'pph_21_bukan_pegawai',
    'pph_4_2':      'pph_4_2_sewa',
}

SIFAT_PAJAK_MAP = {
    'ppn_keluaran': 'potong_pungut',
    'pph_23':       'prepaid',
    'pph_21':       'prepaid',
    'pph_4_2':      'prepaid',
}


def get_available_stock(item_id: int) -> Decimal:
    """Return current available stock for an item from FIFO batches."""
    from django.db.models import Sum
    result = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .aggregate(total=Sum('remaining_qty'))
    )
    return result['total'] or Decimal('0')


def get_fifo_unit_cost(item_id: int) -> Decimal:
    """Weighted-average unit cost across remaining FIFO batches (display/estimation only)."""
    from django.db.models import F, Sum
    result = FIFOBatch.objects.filter(
        item_id=item_id, remaining_qty__gt=0,
    ).aggregate(
        total_qty=Sum('remaining_qty'),
        total_value=Sum(F('remaining_qty') * F('unit_price')),
    )
    total_qty = result['total_qty'] or Decimal('0')
    total_value = result['total_value'] or Decimal('0')
    if total_qty <= 0:
        return Decimal('0')
    return total_value / total_qty


def consume_fifo(item_id: int, quantity: Decimal) -> tuple[Decimal, list[tuple[FIFOBatch, Decimal]]]:
    """Consume inventory using FIFO method.

    Returns (total_cogs, [(batch, qty_consumed), ...]).
    Raises ValueError if insufficient stock.
    """
    batches = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .order_by('tanggal', 'created_at')
        .select_for_update()
    )

    remaining = quantity
    total_cogs = Decimal('0')
    consumed: list[tuple[FIFOBatch, Decimal]] = []

    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_qty, remaining)
        total_cogs += take * batch.unit_price
        batch.remaining_qty -= take
        batch.save()
        consumed.append((batch, take))
        remaining -= take

    if remaining > 0:
        raise ValueError(f'Stok tidak mencukupi. Stok tersedia: {quantity - remaining} unit.')

    return total_cogs, consumed


def _sync_confirm_sales_tax_line(
    si: SalesItem,
    sales_header: SalesHeader,
    tax_line: SalesTaxLine,
    entitas_bisnis=None,
) -> None:
    jenis_pajak = TAX_TYPE_MAP.get(tax_line.tax_type)
    if not jenis_pajak:
        return
    sifat_pajak = SIFAT_PAJAK_MAP.get(tax_line.tax_type, 'potong_pungut')
    override_amount = tax_line.tax if tax_line.is_manual else None
    # Guard: sync_pajak falls back to source_obj.tax when override_amount is None.
    # Clear si.tax in-memory so the deprecated field cannot silently override
    # tarif computation on non-manual tax lines.
    if not tax_line.is_manual and si.tax:
        si.tax = None
    pajak_trx = sync_pajak(
        source_type='sales_item',
        source_obj=si,
        dpp=si.total_sales,
        tanggal=sales_header.tanggal,
        jenis_pajak=jenis_pajak,
        akun_pajak=tax_line.tax_account,
        akun_lawan=tax_line.tax_payment_account,
        sifat_pajak=sifat_pajak,
        override_amount=override_amount,
        entitas_bisnis_override=entitas_bisnis,
    )
    confirm_pajak_trx(pajak_trx)


def _cancel_sales_pajak(sales_header: SalesHeader) -> None:
    si_ids = list(
        SalesItem.objects
        .filter(sales_eb__sales_header=sales_header)
        .values_list('id', flat=True)
    )
    qs = PajakTransaksi.objects.filter(
        source_type='sales_item',
        source_id__in=si_ids,
    ).exclude(status='dibatalkan')
    for pajak_trx in qs:
        batal_pajak_trx(pajak_trx)


def create_sales_automated_journals(sales_header: SalesHeader, user=None) -> list[JurnalHeader]:
    """Generate automated journal entries for a sales transaction.

    Per EB group, one journal header with detail lines for all items.
    """
    created_headers: list[JurnalHeader] = []

    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.select_related(
            'entitas_bisnis', 'payment_account',
        ).all():
            items = list(eb_group.items.select_related(
                'item', 'offset_coa_account', 'revenue_account',
                'inventory_account', 'tax_account', 'tax_payment_account',
                'sub_transaction_type',
            ).all())

            if not items:
                continue

            nomor = _next_sales_journal_number()
            header = JurnalHeader.objects.create(
                tanggal=sales_header.tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=f'Penjualan {sales_header.transaction_id} — {eb_group.entitas_bisnis.nama}',
                entitas_bisnis=eb_group.entitas_bisnis,
                is_penyesuaian=False,
            )

            detail_lines: list[JurnalDetail] = []

            for si in items:
                _payment_akun = si.payment_account or eb_group.payment_account

                # 1. COGS entry: Debit HPP, Credit Persediaan — both or neither
                if si.cogs_amount > 0 and si.inventory_account_id:
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.offset_coa_account,
                        debit=si.cogs_amount,
                        kredit=Decimal('0'),
                    ))
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.inventory_account,
                        debit=Decimal('0'),
                        kredit=si.cogs_amount,
                    ))

                # 2. Revenue entry: Debit Kas/Piutang, Credit Pendapatan
                if si.total_sales > 0 and _payment_akun:
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=_payment_akun,
                        debit=si.total_sales,
                        kredit=Decimal('0'),
                    ))
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.revenue_account,
                        debit=Decimal('0'),
                        kredit=si.total_sales,
                    ))

            JurnalDetail.objects.bulk_create(detail_lines)
            created_headers.append(header)

            # Tax lines via pajak module (jurnal pajak terpisah)
            for si in items:
                for tax_line in si.tax_lines.select_related(
                    'tax_account', 'tax_payment_account'
                ).all():
                    _sync_confirm_sales_tax_line(
                        si, sales_header, tax_line,
                        entitas_bisnis=eb_group.entitas_bisnis,
                    )

        if sales_header.payment_type == 'credit':
            from apps.piutang.services import create_piutang_from_sales
            create_piutang_from_sales(sales_header, user=user)

    return created_headers


def process_sales_fifo(sales_header: SalesHeader) -> list:
    """FIFO/value outflow for all sale items via the authoritative stock ledger.

    Returns a list of ConsumptionReport (for fallback UI notifications).
    Updates cogs_amount + inventory_account on each SalesItem, and mirrors to
    FIFOBatch / InventoryRecord automatically (via linked layers).
    """
    from apps.inventory.ledger import consume_stock
    from decimal import Decimal as _D

    reports = []
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.select_related(
            'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
        ).all():
            for si in eb_group.items.select_related('item').all():
                is_bulk = si.item.tipe_item in ('RMB', 'FGB', 'ITMB')
                if is_bulk:
                    amount = si.hpp_terpakai or _D('0')
                    if amount <= 0:
                        continue
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        amount, sales_header.tanggal, 'sale_out', source=si,
                        metode=si.item.metode_biaya_persediaan,
                        warehouse=si.warehouse)
                    si.cogs_amount = result.total_cost
                else:
                    result = consume_stock(
                        si.item, eb_group.entitas_bisnis,
                        eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                        si.quantity, sales_header.tanggal, 'sale_out', source=si,
                        metode=si.item.metode_biaya_persediaan,
                        warehouse=si.warehouse)
                    si.cogs_amount = result.total_cost
                si.inventory_account_id = si.item.coa_account_id
                si.save()
                _build_sales_allocations(si, result, is_bulk=is_bulk)
                reports.append(result.report)
    return reports


def _build_sales_allocations(si, result, is_bulk=False):
    """Rebuild SalesItemFIFOAllocation rows from StockConsumption for legacy display.

    Non-bulk: alloc.qty is a physical quantity, alloc.unit_cost is per-unit cost —
    quantity_consumed/cogs_amount are their natural product.
    Bulk: alloc.qty stores the VALUE taken from the layer (not a physical qty,
    see ledger.consume_stock's bulk branch), and alloc.unit_cost is the layer's
    own original unit cost — unrelated to the value taken. To preserve the
    legacy display convention (quantity_consumed~=0 for bulk, cogs_amount=value
    taken), quantity_consumed is left at 0 and cogs_amount is alloc.qty directly.
    """
    allocations_to_create = []
    for alloc in result.allocations:
        rec = alloc.in_movement.legacy_inventory_record
        if rec is None:
            continue
        if is_bulk:
            allocations_to_create.append(SalesItemFIFOAllocation(
                sales_item=si, inventory_record=rec,
                quantity_consumed=Decimal('0'),
                cogs_amount=alloc.qty,
            ))
        else:
            allocations_to_create.append(SalesItemFIFOAllocation(
                sales_item=si, inventory_record=rec,
                quantity_consumed=alloc.qty,
                cogs_amount=alloc.qty * alloc.unit_cost,
            ))
    if allocations_to_create:
        SalesItemFIFOAllocation.objects.bulk_create(allocations_to_create)


def reverse_sales_automated_journals(sales_header: SalesHeader) -> None:
    """Delete all automated journal entries linked to this sales transaction."""
    uraian_match = f'Penjualan {sales_header.transaction_id} —'
    JurnalHeader.objects.filter(
        uraian_transaksi__startswith=uraian_match,
        is_penyesuaian=False,
    ).delete()


def reverse_sales_fifo(sales_header: SalesHeader) -> None:
    """Reverse stock consumption for a sales transaction via the ledger engine."""
    from apps.inventory.ledger import reverse_movements
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.all():
                reverse_movements(si)
                si.fifo_allocations.all().delete()


def _next_sales_journal_number() -> str:
    """Generate sequential journal number for sales journals."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-SAL-')
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'TRX-SAL-{seq:03d}'
