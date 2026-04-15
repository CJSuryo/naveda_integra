"""Sales services — FIFO outflow, automated journal generation, and inventory updates."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.purchase.models import FIFOBatch
from apps.inventory.models import InventoryRecord

from .models import SalesHeader, SalesEntitasBisnis, SalesItem


def get_available_stock(item_id: int) -> Decimal:
    """Return current available stock for an item from FIFO batches."""
    from django.db.models import Sum
    result = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .aggregate(total=Sum('remaining_qty'))
    )
    return result['total'] or Decimal('0')


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


def create_sales_automated_journals(sales_header: SalesHeader) -> list[JurnalHeader]:
    """Generate automated journal entries for a sales transaction.

    Per EB group, one journal header with detail lines for all items.
    """
    created_headers: list[JurnalHeader] = []

    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.select_related(
            'entitas_bisnis', 'payment_account',
        ).all():
            items = eb_group.items.select_related(
                'item', 'offset_coa_account', 'revenue_account',
                'inventory_account', 'tax_account', 'tax_payment_account',
                'sub_transaction_type',
            ).all()

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
                # 1. COGS entry: Debit HPP, Credit Persediaan
                if si.cogs_amount > 0:
                    detail_lines.append(JurnalDetail(
                        jurnal_header=header,
                        akun=si.offset_coa_account,
                        debit=si.cogs_amount,
                        kredit=Decimal('0'),
                    ))
                    if si.inventory_account:
                        detail_lines.append(JurnalDetail(
                            jurnal_header=header,
                            akun=si.inventory_account,
                            debit=Decimal('0'),
                            kredit=si.cogs_amount,
                        ))

                # 2. Revenue entry: Debit Kas/Piutang, Credit Pendapatan
                detail_lines.append(JurnalDetail(
                    jurnal_header=header,
                    akun=eb_group.payment_account,
                    debit=si.total_sales,
                    kredit=Decimal('0'),
                ))
                detail_lines.append(JurnalDetail(
                    jurnal_header=header,
                    akun=si.revenue_account,
                    debit=Decimal('0'),
                    kredit=si.total_sales,
                ))

                # 3. Tax entry (if applicable)
                if si.tax and si.tax > 0:
                    tax_liability_account = si.tax_payment_account or si.tax_account
                    if tax_liability_account:
                        detail_lines.append(JurnalDetail(
                            jurnal_header=header,
                            akun=eb_group.payment_account,
                            debit=si.tax,
                            kredit=Decimal('0'),
                        ))
                        detail_lines.append(JurnalDetail(
                            jurnal_header=header,
                            akun=tax_liability_account,
                            debit=Decimal('0'),
                            kredit=si.tax,
                        ))

            JurnalDetail.objects.bulk_create(detail_lines)
            created_headers.append(header)

    return created_headers


def process_sales_fifo(sales_header: SalesHeader) -> None:
    """Process FIFO outflow for all items in a sales transaction.

    Updates cogs_amount and inventory_account on each SalesItem.
    Also updates InventoryRecord quantities based on FIFO consumption.
    """
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.select_related('item').all():
                # Only process inventory items (RM/FG/ITM)
                if si.item.tipe_item not in ('RM', 'FG', 'ITM'):
                    continue

                total_cogs, consumed = consume_fifo(si.item_id, si.quantity)
                si.cogs_amount = total_cogs
                si.inventory_account = si.item.coa_account
                si.save()

                # Update InventoryRecord quantities based on FIFO consumption
                for batch, qty_consumed in consumed:
                    if batch.purchase_item_id:
                        inv_records = InventoryRecord.objects.filter(
                            purchase_item=batch.purchase_item,
                            item=si.item,
                        ).order_by('tanggal', 'created_at')
                        remaining_to_reduce = qty_consumed
                        for inv_rec in inv_records:
                            if remaining_to_reduce <= 0:
                                break
                            reduce = min(inv_rec.quantity, remaining_to_reduce)
                            if reduce > 0:
                                inv_rec.quantity -= reduce
                                inv_rec.save()
                                remaining_to_reduce -= reduce


def reverse_sales_automated_journals(sales_header: SalesHeader) -> None:
    """Delete all automated journal entries linked to this sales transaction."""
    uraian_match = f'Penjualan {sales_header.transaction_id} —'
    JurnalHeader.objects.filter(
        uraian_transaksi__startswith=uraian_match,
        is_penyesuaian=False,
    ).delete()


def reverse_sales_fifo(sales_header: SalesHeader) -> None:
    """Reverse FIFO consumption for a sales transaction.

    Restores remaining_qty on FIFO batches and InventoryRecord quantities.
    """
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.select_related('item').all():
                if si.item.tipe_item not in ('RM', 'FG', 'ITM'):
                    continue
                if si.cogs_amount <= 0:
                    continue

                # Restore FIFO batches (reverse order)
                batches = (
                    FIFOBatch.objects
                    .filter(item_id=si.item_id)
                    .order_by('-tanggal', '-created_at')
                    .select_for_update()
                )
                remaining_to_restore = si.quantity
                for batch in batches:
                    if remaining_to_restore <= 0:
                        break
                    can_restore = batch.quantity_in - batch.remaining_qty
                    restore = min(can_restore, remaining_to_restore)
                    if restore > 0:
                        batch.remaining_qty += restore
                        batch.save()
                        remaining_to_restore -= restore

                        # Also restore the corresponding InventoryRecord
                        if batch.purchase_item_id:
                            inv_records = InventoryRecord.objects.filter(
                                purchase_item=batch.purchase_item,
                                item=si.item,
                            )
                            for inv_rec in inv_records:
                                inv_rec.quantity += restore
                                inv_rec.save()


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
