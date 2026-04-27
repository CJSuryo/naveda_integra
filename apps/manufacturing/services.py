"""Manufacturing services — BOM cost computation, FIFO consumption, production processing."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.purchase.models import FIFOBatch
from apps.inventory.models import InventoryRecord

from .models import (
    BillOfMaterials, BOMLine, ProductionOrder, ProductionRMConsumption,
    OverheadCategory, OverheadRate, OverheadApplied,
)


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
    """Weighted-average cost across ALL remaining batches (used for reference/display only).

    NOTE: This is a simple weighted average, not a true FIFO simulation.
    For accurate cost preview, use _simulate_fifo_cost.
    """
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


def _simulate_fifo_cost(item_id: int, quantity: Decimal) -> tuple[Decimal, Decimal]:
    """Read-only FIFO simulation — same batch order as _consume_fifo but no DB writes.

    Returns (total_cost, qty_filled):
      total_cost  — cost for the qty_filled portion (oldest batches first)
      qty_filled  — how many units could be filled from current stock
                    (may be < quantity if stock is insufficient)

    Example: stock = 15 units @ Rp 20,000 (older) + 5 units @ Rp 18,000 (newer)
      _simulate_fifo_cost(item, 10)  → (200_000, 10)   ← 10 × 20k, all from batch 1
      _simulate_fifo_cost(item, 17)  → (336_000, 17)   ← 15 × 20k + 2 × 18k
      _simulate_fifo_cost(item, 22)  → (390_000, 20)   ← only 20 available
    """
    batches = (
        FIFOBatch.objects
        .filter(item_id=item_id, remaining_qty__gt=0)
        .order_by('tanggal', 'created_at')  # oldest first — same as _consume_fifo
    )
    remaining = quantity
    total_cost = Decimal('0')
    qty_filled = Decimal('0')
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.remaining_qty, remaining)
        total_cost += take * batch.unit_price
        qty_filled += take
        remaining -= take
    return total_cost, qty_filled


# ---------------------------------------------------------------------------
# BOM preview
# ---------------------------------------------------------------------------

def get_bom_preview(bom: BillOfMaterials, qty_produced: Decimal) -> list[dict]:
    """Return per-BOM-line preview data for a given production quantity.

    Uses FIFO simulation (same batch-order as actual consumption) so the unit cost
    and total cost shown match what will actually be consumed.

    Example: if oldest batch = 15 @ Rp 20,000 and next = 5 @ Rp 18,000:
      qty_total=10  → fifo_unit_cost = 20,000  (all from first batch)
      qty_total=17  → fifo_unit_cost ≈ 19,765  (blended: 15×20k + 2×18k)
    """
    rows = []
    for line in bom.lines.select_related('raw_material').all():
        qty_total = line.qty_required * qty_produced
        available = get_available_stock(line.raw_material_id)

        # Simulate FIFO to get accurate costs (oldest batches consumed first)
        fifo_cost, qty_filled = _simulate_fifo_cost(line.raw_material_id, qty_total)
        if qty_filled > 0:
            fifo_unit_cost = (fifo_cost / qty_filled).quantize(Decimal('0.0001'))
        else:
            fifo_unit_cost = Decimal('0')
        # Extrapolate to the full requested qty using the blended rate
        total_rm_cost = (fifo_unit_cost * qty_total).quantize(Decimal('0.0001'))

        rows.append({
            'bom_line': line,
            'rm_item': line.raw_material,
            'qty_required_per_unit': line.qty_required,
            'qty_required_total': qty_total,
            'fifo_unit_cost': fifo_unit_cost,
            'total_rm_cost': total_rm_cost,
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

def get_overhead_rates_for_period(periode_bulan: str) -> dict[int, 'OverheadRate']:
    """Return a dict of {overhead_category_id: OverheadRate} for a given period.

    Only returns active PRODUCTION categories that have a rate configured.
    """
    rates = (
        OverheadRate.objects
        .filter(periode_bulan=periode_bulan, overhead_category__is_active=True)
        .select_related('overhead_category')
    )
    return {r.overhead_category_id: r for r in rates}


def create_overhead_applied(
    production_order: ProductionOrder,
    overhead_drivers: dict[int, Decimal],
    periode_bulan: str,
) -> Decimal:
    """Create OverheadApplied records for a production order and return total overhead.

    overhead_drivers: {overhead_category_id: driver_value}
    Returns total PRODUCTION overhead applied (for overhead_cost field on the order).
    """
    rates = get_overhead_rates_for_period(periode_bulan)
    total_overhead = Decimal('0')

    for cat_id, driver_value in overhead_drivers.items():
        if driver_value <= 0:
            continue
        rate = rates.get(cat_id)
        if not rate:
            continue
        applied = OverheadApplied.objects.create(
            production_order=production_order,
            overhead_category_id=cat_id,
            periode_bulan=periode_bulan,
            driver_value=driver_value,
            rate_per_driver=rate.rate_per_driver,
        )
        total_overhead += applied.amount_applied

    return total_overhead


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

        # 2. Compute final costs — read applied overhead from DB
        production_overhead = (
            production_order.overhead_applied
            .filter(overhead_category__overhead_type='PRODUCTION')
            .aggregate(total=Sum('amount_applied'))['total'] or Decimal('0')
        )
        total_cost = total_rm_cost + production_overhead
        unit_cost = (
            (total_cost / qty_produced).quantize(Decimal('0.0001'))
            if qty_produced > 0 else Decimal('0')
        )

        # Store costs on the order now so _create_production_journals can read them
        production_order.rm_cost = total_rm_cost
        production_order.overhead_cost = production_overhead
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
    # Overhead entries: one DR/CR pair per OverheadApplied (PRODUCTION only)
    # DR coa_produksi (WIP) / CR coa_overhead_applied (2.x.x per category)
    for applied in (
        production_order.overhead_applied
        .filter(overhead_category__overhead_type='PRODUCTION')
        .select_related('overhead_category__coa_overhead_applied')
    ):
        cat = applied.overhead_category
        if not cat.coa_overhead_applied_id:
            continue
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=production_order.coa_produksi,
            debit=applied.amount_applied,
            kredit=zero,
        ))
        details.append(JurnalDetail(
            jurnal_header=header,
            akun=cat.coa_overhead_applied,
            debit=zero,
            kredit=applied.amount_applied,
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
    query = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-PROD-')
        .order_by('-nomor_transaksi')
    )
    if transaction.get_connection().in_atomic_block:
        query = query.select_for_update()

    last = query.values_list('nomor_transaksi', flat=True).first()
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

        # Delete consumption records and overhead applied records
        production_order.rm_consumptions.all().delete()
        production_order.overhead_applied.all().delete()

        # Reset the production order
        production_order.is_processed = False
        production_order.status = 'in_progress'
        production_order.rm_cost = Decimal('0')
        production_order.overhead_cost = Decimal('0')
        production_order.total_cost = Decimal('0')
        production_order.unit_cost = Decimal('0')
        production_order.fg_inventory_record = None
        production_order.save()


# ---------------------------------------------------------------------------
# Period-end closing
# ---------------------------------------------------------------------------

def period_end_closing(
    periode_bulan: str,
    coa_cogs_id: int,
) -> list[dict]:
    """Compute over/under-absorbed overhead for a period and generate closing journals.

    For each PRODUCTION overhead category that has an OverheadRate with aktual_total set:
        - Compute total amount applied (from OverheadApplied records)
        - Compare to aktual_total
        - If applied > aktual_total (over-absorbed): DR Overhead Applied / CR COGS
        - If applied < aktual_total (under-absorbed): DR COGS / CR Overhead Applied

    Returns a list of result dicts with fields: category, applied, actual, variance, journal_id.
    Raises ValueError if aktual_total is not set for any category in the period.
    """
    rates = (
        OverheadRate.objects
        .filter(
            periode_bulan=periode_bulan,
            overhead_category__overhead_type='PRODUCTION',
        )
        .select_related('overhead_category__coa_overhead_applied')
    )

    if not rates.exists():
        raise ValueError(f'Tidak ada overhead rate yang dikonfigurasi untuk periode {periode_bulan}.')

    missing_actual = [r.overhead_category.name for r in rates if r.aktual_total is None]
    if missing_actual:
        raise ValueError(
            f'Aktual total belum diisi untuk: {", ".join(missing_actual)}. '
            'Isi aktual total sebelum melakukan period-end closing.'
        )

    results = []
    zero = Decimal('0')
    from apps.jurnal.models import JurnalHeader, JurnalDetail  # local to avoid circulars

    year, month = map(int, periode_bulan.split('-'))
    last_day = monthrange(year, month)[1]
    journal_date = date(year, month, last_day)

    with transaction.atomic():
        for rate in rates:
            cat = rate.overhead_category
            applied_total = (
                OverheadApplied.objects
                .filter(overhead_category=cat, periode_bulan=periode_bulan)
                .aggregate(total=Sum('amount_applied'))['total'] or zero
            )
            actual_total = rate.aktual_total
            variance = applied_total - actual_total  # positive = over-absorbed

            if variance == 0 or not cat.coa_overhead_applied_id:
                results.append({
                    'category': cat.name,
                    'applied': applied_total,
                    'actual': actual_total,
                    'variance': zero,
                    'journal_id': None,
                })
                continue

            # Build closing journal
            from apps.master_data.models import Akun  # local import
            try:
                coa_cogs = Akun.objects.get(pk=coa_cogs_id)
            except Akun.DoesNotExist:
                raise ValueError(f'Akun COGS (id={coa_cogs_id}) tidak ditemukan.')

            if variance > 0:
                # Over-absorbed: applied > actual — reduce overhead applied
                uraian = f'Closing overhead over-absorbed {cat.name} {periode_bulan}'
                debit_akun = cat.coa_overhead_applied
                kredit_akun = coa_cogs
            else:
                # Under-absorbed: applied < actual — charge shortage to COGS
                uraian = f'Closing overhead under-absorbed {cat.name} {periode_bulan}'
                debit_akun = coa_cogs
                kredit_akun = cat.coa_overhead_applied

            if JurnalHeader.objects.filter(uraian_transaksi=uraian, is_penyesuaian=True).exists():
                results.append({
                    'category': cat.name,
                    'applied': applied_total,
                    'actual': actual_total,
                    'variance': variance,
                    'journal_id': None,
                    'skipped': True,
                })
                continue

            entitas_ids = list(
                OverheadApplied.objects
                .filter(overhead_category=cat, periode_bulan=periode_bulan)
                .values_list('production_order__entitas_bisnis_id', flat=True)
                .distinct()
            )
            entitas_bisnis_id = entitas_ids[0] if len(entitas_ids) == 1 else None

            nomor = _next_production_journal_number()
            header = JurnalHeader.objects.create(
                tanggal=journal_date,
                nomor_transaksi=nomor,
                uraian_transaksi=uraian,
                entitas_bisnis_id=entitas_bisnis_id,
                is_penyesuaian=True,
            )
            amount = abs(variance)
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=header, akun=debit_akun, debit=amount, kredit=zero),
                JurnalDetail(jurnal_header=header, akun=kredit_akun, debit=zero, kredit=amount),
            ])

            results.append({
                'category': cat.name,
                'applied': applied_total,
                'actual': actual_total,
                'variance': variance,
                'journal_id': header.pk,
            })

    return results
