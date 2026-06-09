"""Sales services — FIFO outflow, automated journal generation, and inventory updates."""
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.purchase.models import FIFOBatch
from apps.inventory.models import InventoryRecord

from .models import SalesHeader, SalesEntitasBisnis, SalesItem, SalesItemFIFOAllocation


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


def create_sales_automated_journals(sales_header: SalesHeader, user=None) -> list[JurnalHeader]:
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

                # 3. Tax entry (if applicable)
                if si.tax and si.tax > 0:
                    tax_liability_account = si.tax_payment_account or si.tax_account
                    if tax_liability_account:
                        detail_lines.append(JurnalDetail(
                            jurnal_header=header,
                            akun=_payment_akun or eb_group.payment_account,
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

        if sales_header.payment_type == 'credit':
            from apps.piutang.services import create_piutang_from_sales
            create_piutang_from_sales(sales_header, user=user)

    return created_headers


def process_sales_fifo(sales_header: SalesHeader) -> None:
    """Process FIFO outflow for all items in a sales transaction.

    Updates cogs_amount and inventory_account on each SalesItem.
    Also updates InventoryRecord quantities based on FIFO consumption.
    """
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.select_related('item').all():
                BULK_TYPES = ('RMB', 'FGB', 'ITMB')
                SATUAN_TYPES = ('RM', 'FG', 'ITM')

                if si.item.tipe_item in SATUAN_TYPES:
                    # Standard FIFO quantity-based consumption
                    total_cogs, consumed = consume_fifo(si.item_id, si.quantity)
                    si.cogs_amount = total_cogs
                    si.inventory_account_id = si.item.coa_account_id
                    si.save()

                    # Update InventoryRecord quantities based on FIFO consumption
                    records_to_update = []
                    allocations_to_create = []
                    for batch, qty_consumed in consumed:
                        if batch.purchase_item_id:
                            inv_records = InventoryRecord.objects.filter(
                                purchase_item=batch.purchase_item,
                                item=si.item,
                            ).order_by('tanggal', 'created_at')
                        else:
                            inv_records = InventoryRecord.objects.filter(
                                purchase_item__isnull=True,
                                item=si.item,
                                tanggal=batch.tanggal,
                                unit_price=batch.unit_price,
                            ).order_by('tanggal', 'created_at')

                        remaining_to_reduce = qty_consumed
                        for inv_rec in inv_records:
                            if remaining_to_reduce <= 0:
                                break
                            reduce = min(inv_rec.quantity, remaining_to_reduce)
                            if reduce > 0:
                                inv_rec.quantity -= reduce
                                inv_rec.total_value = inv_rec.quantity * inv_rec.unit_price
                                records_to_update.append(inv_rec)
                                allocations_to_create.append(SalesItemFIFOAllocation(
                                    sales_item=si,
                                    inventory_record=inv_rec,
                                    quantity_consumed=reduce,
                                    cogs_amount=reduce * batch.unit_price,
                                ))
                                remaining_to_reduce -= reduce
                    if records_to_update:
                        InventoryRecord.objects.bulk_update(records_to_update, ['quantity', 'total_value'])
                    if allocations_to_create:
                        SalesItemFIFOAllocation.objects.bulk_create(allocations_to_create)

                elif si.item.tipe_item in BULK_TYPES:
                    # Bulk: value-based deduction using hpp_terpakai
                    hpp = si.hpp_terpakai or Decimal('0')
                    if hpp <= 0:
                        continue

                    si.cogs_amount = hpp
                    si.inventory_account_id = si.item.coa_account_id
                    si.save()

                    # Reduce InventoryRecord total_value (bulk has qty=1, value tracks worth)
                    inv_records = InventoryRecord.objects.filter(
                        item=si.item,
                        entitas_bisnis=eb_group.entitas_bisnis,
                        total_value__gt=0,
                    ).order_by('tanggal', 'created_at').select_for_update()

                    remaining_value = hpp
                    records_to_update = []
                    allocations_to_create = []
                    for inv_rec in inv_records:
                        if remaining_value <= 0:
                            break
                        deduct = min(inv_rec.total_value, remaining_value)
                        if deduct > 0:
                            inv_rec.total_value -= deduct
                            inv_rec.unit_price = inv_rec.total_value  # bulk: unit_price = total_value
                            records_to_update.append(inv_rec)
                            allocations_to_create.append(SalesItemFIFOAllocation(
                                sales_item=si,
                                inventory_record=inv_rec,
                                quantity_consumed=Decimal('0'),
                                cogs_amount=deduct,
                            ))
                            remaining_value -= deduct

                    if records_to_update:
                        InventoryRecord.objects.bulk_update(records_to_update, ['total_value', 'unit_price'])
                    if allocations_to_create:
                        SalesItemFIFOAllocation.objects.bulk_create(allocations_to_create)

                    # Also reduce FIFO batch values for bulk
                    fifo_batches = (
                        FIFOBatch.objects
                        .filter(item=si.item, remaining_qty__gt=0)
                        .order_by('tanggal', 'created_at')
                        .select_for_update()
                    )
                    remaining_fifo = hpp
                    for batch in fifo_batches:
                        if remaining_fifo <= 0:
                            break
                        batch_value = batch.remaining_qty * batch.unit_price
                        deduct = min(batch_value, remaining_fifo)
                        if deduct > 0:
                            batch.remaining_qty = (batch_value - deduct) / batch.unit_price if batch.unit_price else Decimal('0')
                            batch.save()
                            remaining_fifo -= deduct


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
    Uses SalesItemFIFOAllocation records to precisely restore inventory,
    handling both purchase-sourced and saldo-awal-sourced batches.
    """
    with transaction.atomic():
        for eb_group in sales_header.entitas_groups.all():
            for si in eb_group.items.select_related('item').prefetch_related(
                'fifo_allocations__inventory_record',
            ).all():
                BULK_TYPES = ('RMB', 'FGB', 'ITMB')
                SATUAN_TYPES = ('RM', 'FG', 'ITM')

                if si.item.tipe_item in SATUAN_TYPES:
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

                    # Restore InventoryRecord quantities
                    records_to_restore = []
                    for alloc in si.fifo_allocations.select_related('inventory_record').all():
                        inv_rec = alloc.inventory_record
                        inv_rec.quantity += alloc.quantity_consumed
                        inv_rec.total_value = inv_rec.quantity * inv_rec.unit_price
                        records_to_restore.append(inv_rec)
                    if records_to_restore:
                        InventoryRecord.objects.bulk_update(records_to_restore, ['quantity', 'total_value'])

                elif si.item.tipe_item in BULK_TYPES:
                    if si.cogs_amount <= 0:
                        continue

                    # Restore InventoryRecord values using allocations
                    records_to_restore = []
                    for alloc in si.fifo_allocations.select_related('inventory_record').all():
                        inv_rec = alloc.inventory_record
                        inv_rec.total_value += alloc.cogs_amount
                        inv_rec.unit_price = inv_rec.total_value  # bulk: unit_price = total_value
                        records_to_restore.append(inv_rec)
                    if records_to_restore:
                        InventoryRecord.objects.bulk_update(records_to_restore, ['total_value', 'unit_price'])

                    # Restore FIFO batch values
                    hpp = si.cogs_amount
                    batches = (
                        FIFOBatch.objects
                        .filter(item_id=si.item_id)
                        .order_by('-tanggal', '-created_at')
                        .select_for_update()
                    )
                    remaining_to_restore = hpp
                    for batch in batches:
                        if remaining_to_restore <= 0:
                            break
                        max_value = batch.quantity_in * batch.unit_price
                        current_value = batch.remaining_qty * batch.unit_price
                        can_restore = max_value - current_value
                        restore = min(can_restore, remaining_to_restore)
                        if restore > 0 and batch.unit_price:
                            batch.remaining_qty += restore / batch.unit_price
                            batch.save()
                            remaining_to_restore -= restore


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
