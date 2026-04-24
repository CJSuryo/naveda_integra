"""Manufacturing services — BOM cost computation, FIFO consumption, production processing."""
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.purchase.models import FIFOBatch
from apps.inventory.models import InventoryRecord

from .models import BillOfMaterials, BOMLine, ProductionOrder, ProductionRMConsumption


# ---------------------------------------------------------------------------
# Stock / cost helpers
# ---------------------------------------------------------------------------

def get_available_stock(item_id: int) -> Decimal:
    """Return current available stock for an item (sum of remaining FIFO qty)."""
    result = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .aggregate(total=Sum('remaining_qty'))
    )
    return result['total'] or Decimal('0')


def get_fifo_unit_cost(item_id: int) -> Decimal:
    """Weighted-average FIFO unit cost across remaining batches."""
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
    return (total_value / total_qty).quantize(Decimal('0.0001'))


# ---------------------------------------------------------------------------
# BOM preview
# ---------------------------------------------------------------------------

def get_bom_preview(bom: BillOfMaterials, qty_produced: Decimal) -> list[dict]:
    """Return per-BOM-line preview data for a given production quantity.

    Each entry contains:
      bom_line, rm_item, qty_required_per_unit, qty_required_total,
      fifo_unit_cost, total_rm_cost, available_stock, is_sufficient
    """
    rows = []
    for line in bom.lines.select_related('raw_material').all():
        qty_total = line.qty_required * qty_produced
        fifo_cost = get_fifo_unit_cost(line.raw_material_id)
        available = get_available_stock(line.raw_material_id)
        rows.append({
            'bom_line': line,
            'rm_item': line.raw_material,
            'qty_required_per_unit': line.qty_required,
            'qty_required_total': qty_total,
            'fifo_unit_cost': fifo_cost,
            'total_rm_cost': qty_total * fifo_cost,
            'available_stock': available,
            'is_sufficient': available >= qty_total,
            'shortage': max(Decimal('0'), qty_total - available),
        })
    return rows


def compute_estimated_cost(
    bom: BillOfMaterials,
    qty_produced: Decimal,
    overhead_cost: Decimal,
) -> dict:
    """Compute estimated production costs without modifying any stock."""
    preview = get_bom_preview(bom, qty_produced)
    rm_cost = sum((r['total_rm_cost'] for r in preview), Decimal('0'))
    total_cost = rm_cost + overhead_cost
    unit_cost = (
        (total_cost / qty_produced).quantize(Decimal('0.0001'))
        if qty_produced > 0 else Decimal('0')
    )
    return {
        'preview': preview,
        'rm_cost': rm_cost,
        'total_cost': total_cost,
        'unit_cost': unit_cost,
        'all_sufficient': all(r['is_sufficient'] for r in preview),
    }


def validate_production(production_order: ProductionOrder) -> list[str]:
    """Return a list of human-readable validation errors (empty = OK to process)."""
    errors: list[str] = []
    bom = production_order.bom
    qty_produced = production_order.qty_produced

    if not bom.lines.exists():
        errors.append('BOM tidak memiliki baris bahan baku.')
        return errors

    for line in bom.lines.select_related('raw_material').all():
        qty_needed = line.qty_required * qty_produced
        available = get_available_stock(line.raw_material_id)
        if available < qty_needed:
            shortage = qty_needed - available
            errors.append(
                f'{line.raw_material.item_id} — {line.raw_material.nama}: '
                f'dibutuhkan {qty_needed} unit, '
                f'tersedia {available}, kurang {shortage}.'
            )

    if production_order.overhead_cost > 0 and not production_order.coa_overhead_applied_id:
        errors.append(
            'Akun Manufacturing Overhead Applied wajib diisi jika Overhead Cost > 0.'
        )

    return errors


# ---------------------------------------------------------------------------
# Internal FIFO consumer
# ---------------------------------------------------------------------------

def _consume_fifo(
    item_id: int,
    quantity: Decimal,
) -> tuple[Decimal, list[tuple[FIFOBatch, Decimal]]]:
    """Consume `quantity` units of `item_id` using FIFO order.

    Returns (total_cost, [(batch, qty_consumed), ...]).
    Raises ValueError if insufficient stock.
    """
    batches = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .order_by('tanggal', 'created_at')
        .select_for_update()
    )
    remaining = quantity
    total_cost = Decimal('0')
    consumed: list[tuple[FIFOBatch, Decimal]] = []

    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_qty, remaining)
        total_cost += take * batch.unit_price
        batch.remaining_qty -= take
        batch.save()
        consumed.append((batch, take))
        remaining -= take

    if remaining > 0:
        raise ValueError(
            f'Stok item {item_id} tidak mencukupi. '
            f'Tersedia: {quantity - remaining}, dibutuhkan: {quantity}.'
        )

    return total_cost, consumed


# ---------------------------------------------------------------------------
# Main production execution
# ---------------------------------------------------------------------------

def process_production(production_order: ProductionOrder, as_wip: bool = False) -> None:
    """Execute a production order: consume RM stock, optionally create FG stock, generate journals.

    as_wip=False (default): Full production — consume RM, create FG batch + inventory,
        post full journal (including FG completion entry), set status='completed'.
    as_wip=True: WIP mode — consume RM, post WIP-only journals (no FG completion entry),
        do NOT create FG batch/inventory. Status remains 'in_progress'.
        Call approve_production() later to complete.

    Raises ValueError for validation failures or duplicate processing.
    """
    if production_order.is_processed:
        raise ValueError('Production order sudah diproses sebelumnya.')

    errors = validate_production(production_order)
    if errors:
        raise ValueError('\n'.join(errors))

    bom = production_order.bom
    qty_produced = production_order.qty_produced
    overhead = production_order.overhead_cost or Decimal('0')
    entitas_bisnis = production_order.entitas_bisnis

    with transaction.atomic():
        # 1. Consume RM FIFO batches and record consumption
        total_rm_cost = Decimal('0')
        for line in bom.lines.select_related('raw_material').all():
            qty_needed = line.qty_required * qty_produced
            rm_cost, consumed_batches = _consume_fifo(line.raw_material_id, qty_needed)
            total_rm_cost += rm_cost
            for batch, qty in consumed_batches:
                ProductionRMConsumption.objects.create(
                    production_order=production_order,
                    bom_line=line,
                    fifo_batch=batch,
                    qty_consumed=qty,
                    unit_cost=batch.unit_price,
                )

        # 2. Compute final costs
        total_cost = total_rm_cost + overhead
        unit_cost = (
            (total_cost / qty_produced).quantize(Decimal('0.0001'))
            if qty_produced > 0 else Decimal('0')
        )

        # Store costs on the order now so _create_production_journals can read them
        production_order.rm_cost = total_rm_cost
        production_order.total_cost = total_cost
        production_order.unit_cost = unit_cost

        fg_item = bom.finished_good

        if not as_wip:
            # 3. Create FG FIFO inflow batch (completed mode only)
            FIFOBatch.objects.create(
                purchase_item=None,
                item=fg_item,
                tanggal=production_order.tanggal,
                quantity_in=qty_produced,
                unit_price=unit_cost,
                remaining_qty=qty_produced,
            )

            # 4. Create FG InventoryRecord
            inv_record = InventoryRecord.objects.create(
                item=fg_item,
                purchase_item=None,
                entitas_bisnis=entitas_bisnis,
                quantity=qty_produced,
                unit_price=unit_cost,
                tanggal=production_order.tanggal,
                lead_time_days=production_order.lead_time_days,
                ordering_cost=production_order.ordering_cost,
                holding_cost_pct=production_order.holding_cost_pct,
                moq=production_order.moq,
            )

        # 5. Generate journal entries
        # WIP: post RM consumption + overhead only (no FG completion entry yet)
        # Completed: post full journal including FG completion entry
        _create_production_journals(production_order, include_fg_completion=not as_wip)

        # 6. Finalise the order
        production_order.is_processed = True
        if not as_wip:
            production_order.status = 'completed'
            production_order.fg_inventory_record = inv_record
        # else: status stays 'in_progress' as set by the form
        production_order.save()


# ---------------------------------------------------------------------------
# Journal generation
# ---------------------------------------------------------------------------

def _create_production_journals(
    production_order: ProductionOrder,
    include_fg_completion: bool = True,
) -> JurnalHeader:
    """Create double-entry journal entries for a production run.

    Per RM consumed:
        DR coa_produksi (WIP)        | actual consumed cost
        CR rm.coa_account            | actual consumed cost

    If overhead > 0 and coa_overhead_applied is set:
        DR coa_produksi (WIP)             | overhead_cost
        CR coa_overhead_applied (2.x.x)  | overhead_cost  (Manufacturing Overhead Applied)

    FG completion (only when include_fg_completion=True):
        DR fg.coa_account            | total_cost
        CR coa_produksi (WIP)        | total_cost
    """
    fg_item = production_order.bom.finished_good
    nomor = _next_production_journal_number()

    header = JurnalHeader.objects.create(
        tanggal=production_order.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Produksi {production_order.production_id} — {fg_item.nama}'
        ),
        entitas_bisnis=production_order.entitas_bisnis,
        is_penyesuaian=False,
    )

    details: list[JurnalDetail] = []
    zero = Decimal('0')

    # RM consumption entries (grouped per BOM line)
    for line in production_order.bom.lines.select_related('raw_material__coa_account').all():
        rm_item = line.raw_material
        if not rm_item.coa_account_id:
            continue
        consumed_cost = (
            production_order.rm_consumptions
            .filter(bom_line=line)
            .aggregate(total=Sum('total_cost'))['total'] or zero
        )
        if consumed_cost > 0:
            details.append(JurnalDetail(
                jurnal_header=header,
                akun=production_order.coa_produksi,
                debit=consumed_cost,
                kredit=zero,
            ))
            details.append(JurnalDetail(
                jurnal_header=header,
                akun=rm_item.coa_account,
                debit=zero,
                kredit=consumed_cost,
            ))

    # Overhead entry: DR WIP / CR Manufacturing Overhead Applied (2.x.x liability)
    overhead = production_order.overhead_cost or zero
    if overhead > 0 and production_order.coa_overhead_applied_id:
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=production_order.coa_produksi,
            debit=overhead,
            kredit=zero,
        ))
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=production_order.coa_overhead_applied,
            debit=zero,
            kredit=overhead,
        ))

    # FG completion entry (only when completing directly, not for WIP)
    if include_fg_completion and fg_item.coa_account_id:
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=fg_item.coa_account,
            debit=production_order.total_cost,
            kredit=zero,
        ))
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=production_order.coa_produksi,
            debit=zero,
            kredit=production_order.total_cost,
        ))

    JurnalDetail.objects.bulk_create(details)
    return header


def _create_fg_completion_journal(production_order: ProductionOrder) -> JurnalHeader | None:
    """Create the FG completion journal when approving a WIP order.

    DR fg.coa_account  | total_cost
    CR coa_produksi    | total_cost
    """
    fg_item = production_order.bom.finished_good
    if not fg_item.coa_account_id:
        return None

    nomor = _next_production_journal_number()
    header = JurnalHeader.objects.create(
        tanggal=production_order.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=(
            f'Produksi {production_order.production_id} — Selesai (FG)'
        ),
        entitas_bisnis=production_order.entitas_bisnis,
        is_penyesuaian=False,
    )
    zero = Decimal('0')
    JurnalDetail.objects.bulk_create([
        JurnalDetail(
            jurnal_header=header,
            akun=fg_item.coa_account,
            debit=production_order.total_cost,
            kredit=zero,
        ),
        JurnalDetail(
            jurnal_header=header,
            akun=production_order.coa_produksi,
            debit=zero,
            kredit=production_order.total_cost,
        ),
    ])
    return header


def _next_production_journal_number() -> str:
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-PROD-')
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
    return f'TRX-PROD-{seq:04d}'


# ---------------------------------------------------------------------------
# WIP Approval
# ---------------------------------------------------------------------------

def approve_production(production_order: ProductionOrder) -> None:
    """Complete a WIP production order.

    Creates the FG FIFO batch, FG InventoryRecord, and the FG completion
    journal entry (DR fg.coa_account / CR coa_produksi).
    Sets status='completed' and links fg_inventory_record.

    Raises ValueError if the order is not a processable WIP.
    """
    if production_order.status != 'in_progress':
        raise ValueError('Hanya production order berstatus In Progress yang dapat di-approve.')
    if not production_order.is_processed:
        raise ValueError(
            'Production order belum diproses. Proses order terlebih dahulu sebelum approve.'
        )
    if production_order.fg_inventory_record_id:
        raise ValueError('Production order sudah memiliki Inventory FG — tidak dapat di-approve ulang.')

    fg_item = production_order.bom.finished_good
    qty_produced = production_order.qty_produced

    with transaction.atomic():
        # Create FG FIFO inflow batch
        FIFOBatch.objects.create(
            purchase_item=None,
            item=fg_item,
            tanggal=production_order.tanggal,
            quantity_in=qty_produced,
            unit_price=production_order.unit_cost,
            remaining_qty=qty_produced,
        )

        # Create FG InventoryRecord
        inv_record = InventoryRecord.objects.create(
            item=fg_item,
            purchase_item=None,
            entitas_bisnis=production_order.entitas_bisnis,
            quantity=qty_produced,
            unit_price=production_order.unit_cost,
            tanggal=production_order.tanggal,
            lead_time_days=production_order.lead_time_days,
            ordering_cost=production_order.ordering_cost,
            holding_cost_pct=production_order.holding_cost_pct,
            moq=production_order.moq,
        )

        # Create completion journal (DR fg_coa / CR wip_coa)
        _create_fg_completion_journal(production_order)

        # Finalize
        production_order.status = 'completed'
        production_order.fg_inventory_record = inv_record
        production_order.save()


# ---------------------------------------------------------------------------
# Reversal
# ---------------------------------------------------------------------------

def reverse_production(production_order: ProductionOrder) -> None:
    """Reverse a completed production order.

    Restores RM FIFO batches, deletes FG FIFO batch, FG InventoryRecord,
    journal entries, and RM consumption records. Resets the order to in_progress.
    """
    if not production_order.is_processed:
        raise ValueError('Production order belum diproses, tidak dapat di-reverse.')

    fg_item = production_order.bom.finished_good

    with transaction.atomic():
        # Restore RM FIFO batches
        for consumption in production_order.rm_consumptions.select_related('fifo_batch').all():
            batch = consumption.fifo_batch
            batch.remaining_qty += consumption.qty_consumed
            batch.save()

        # Delete FG InventoryRecord created by this production
        if production_order.fg_inventory_record_id:
            production_order.fg_inventory_record.delete()
        else:
            # Fallback for orders processed before FK was added
            InventoryRecord.objects.filter(
                item=fg_item,
                purchase_item__isnull=True,
                tanggal=production_order.tanggal,
                quantity=production_order.qty_produced,
                unit_price=production_order.unit_cost,
                entitas_bisnis=production_order.entitas_bisnis,
            ).delete()

        # Delete FG FIFO batch created by this production
        FIFOBatch.objects.filter(
            item=fg_item,
            purchase_item__isnull=True,
            tanggal=production_order.tanggal,
            quantity_in=production_order.qty_produced,
            unit_price=production_order.unit_cost,
        ).delete()

        # Delete journal entries
        JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Produksi {production_order.production_id}',
        ).delete()

        # Delete consumption records
        production_order.rm_consumptions.all().delete()

        # Reset the production order
        production_order.is_processed = False
        production_order.status = 'in_progress'
        production_order.rm_cost = Decimal('0')
        production_order.total_cost = Decimal('0')
        production_order.unit_cost = Decimal('0')
        production_order.fg_inventory_record = None
        production_order.save()
