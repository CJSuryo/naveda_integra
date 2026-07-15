"""Purchase services — automated journal generation, FIFO engine, and inventory record updates."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.jurnal.models import JurnalHeader, JurnalDetail
from apps.inventory.models import InventoryRecord
from apps.aset_tetap.models import AsetTetapRecord
from apps.aset_lainnya.models import AsetLainnyaRecord

from .models import PurchaseHeader, PurchaseItem, FIFOBatch


def create_automated_journals(purchase_header: PurchaseHeader) -> list[JurnalHeader]:
    """Generate automated journal entries for all items in a purchase.

    For each PurchaseItem:
      Debit: CoA Account (e.g. Persediaan Bahan Baku) — item's coa_account
      Credit: Offset CoA Account (e.g. Kas/Bank) — from sub_transaction_type settings

    Returns the list of created JurnalHeader objects.
    """
    created_headers: list[JurnalHeader] = []

    with transaction.atomic():
        for eb_group in purchase_header.entitas_groups.select_related('entitas_bisnis').all():
            items = eb_group.items.select_related(
                'item', 'coa_account', 'offset_coa_account', 'sub_transaction_type',
            ).all()

            if not items:
                continue

            # One journal header per entitas bisnis group
            nomor = _next_purchase_journal_number()
            header = JurnalHeader.objects.create(
                tanggal=purchase_header.tanggal,
                nomor_transaksi=nomor,
                uraian_transaksi=f'Pembelian {purchase_header.transaction_id} — {eb_group.entitas_bisnis.nama}',
                entitas_bisnis=eb_group.entitas_bisnis,
                is_penyesuaian=False,
            )

            detail_lines: list[JurnalDetail] = []
            for pi in items:
                total = pi.total_value
                # Debit: inventory/asset account
                detail_lines.append(JurnalDetail(
                    jurnal_header=header,
                    akun=pi.coa_account,
                    debit=total,
                    kredit=Decimal('0'),
                ))
                # Credit: offset account (kas/bank/modal)
                detail_lines.append(JurnalDetail(
                    jurnal_header=header,
                    akun=pi.offset_coa_account,
                    debit=Decimal('0'),
                    kredit=total,
                ))

            JurnalDetail.objects.bulk_create(detail_lines)
            created_headers.append(header)

    return created_headers


def create_fifo_batches(purchase_header: PurchaseHeader) -> list[FIFOBatch]:
    """Create FIFO batch records for each inventory purchase item (inflow only)."""
    batches: list[FIFOBatch] = []

    for eb_group in purchase_header.entitas_groups.all():
        items = eb_group.items.select_related('item', 'sub_transaction_type').all()
        for pi in items:
            # Only create FIFO batches for inventory items (not assets)
            if pi.item.tipe_item not in ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'):
                continue
            # Only create FIFO batches for inflow transactions
            if pi.sub_transaction_type.direction != 'inflow':
                continue
            # Bulk items: qty=1, unit_price=total_value (value-based tracking)
            is_bulk = pi.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            batch = FIFOBatch.objects.create(
                purchase_item=pi,
                item=pi.item,
                tanggal=purchase_header.tanggal,
                quantity_in=Decimal('1') if is_bulk else pi.quantity,
                unit_price=pi.total_value if is_bulk else pi.unit_price,
                remaining_qty=Decimal('1') if is_bulk else pi.quantity,
            )
            batches.append(batch)

    return batches


def reverse_automated_journals(purchase_header: PurchaseHeader) -> None:
    """Delete all automated journal entries linked to this purchase."""
    nomor_prefix = f'Pembelian {purchase_header.transaction_id}'
    JurnalHeader.objects.filter(
        nomor_transaksi__startswith='TRX-PUR-',
        uraian_transaksi__startswith=nomor_prefix,
        is_penyesuaian=False,
    ).delete()


def reverse_fifo_batches(purchase_header: PurchaseHeader) -> None:
    """Delete FIFO batches created by this purchase."""
    FIFOBatch.objects.filter(
        purchase_item__purchase_eb__purchase_header=purchase_header,
    ).delete()


def create_inventory_records(purchase_header: PurchaseHeader) -> list[InventoryRecord]:
    """Create InventoryRecord entries for each purchase item (inventory types only).

    Numbering format: PREFIX-XXXX-YYY where PREFIX=RM/FG/ITM,
    XXXX = item_id suffix, YYY = sequential number per item.
    """
    records: list[InventoryRecord] = []

    for eb_group in purchase_header.entitas_groups.select_related('entitas_bisnis').all():
        items = eb_group.items.select_related('item', 'sub_transaction_type').all()
        for pi in items:
            # Only create inventory records for inflow inventory items (RM/FG/ITM/RMB/FGB/ITMB)
            if pi.item.tipe_item not in ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'):
                continue
            if pi.sub_transaction_type.direction != 'inflow':
                continue

            # Determine metode_alokasi: use PurchaseItem value, fallback to ItemMaster
            metode = pi.metode_alokasi_biaya or pi.item.metode_biaya_persediaan or ''

            # Determine tanggal_kadaluarsa: auto-calculate from lama_kadaluarsa if not manually set
            tanggal_kadaluarsa = None
            if pi.item.lama_kadaluarsa:
                tanggal_base = purchase_header.tanggal if isinstance(purchase_header.tanggal, date) else date.fromisoformat(str(purchase_header.tanggal))
                tanggal_kadaluarsa = tanggal_base + timedelta(days=pi.item.lama_kadaluarsa)

            # Bulk items: quantity=1, unit_price=total_value (value-based tracking)
            is_bulk = pi.item.tipe_item in ('RMB', 'FGB', 'ITMB')

            record = InventoryRecord(
                item=pi.item,
                purchase_item=pi,
                entitas_bisnis=eb_group.entitas_bisnis,
                quantity=Decimal('1') if is_bulk else pi.quantity,
                unit_price=pi.total_value if is_bulk else pi.unit_price,
                tanggal=purchase_header.tanggal,
                lead_time_days=pi.lead_time_days,
                ordering_cost=pi.ordering_cost,
                holding_cost_pct=pi.holding_cost_pct,
                moq=pi.moq,
                metode_alokasi=metode,
                tanggal_kadaluarsa=tanggal_kadaluarsa,
            )
            record.save()
            records.append(record)

    return records


def create_stock_movements(purchase_header: PurchaseHeader) -> list:
    """Create StockMovement inflow layers linked to the FIFOBatch + InventoryRecord
    that create_fifo_batches / create_inventory_records already made for this purchase.
    """
    from apps.inventory.ledger import record_inflow

    movements = []
    for eb_group in purchase_header.entitas_groups.select_related(
        'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
    ).all():
        items = eb_group.items.select_related('item', 'sub_transaction_type').all()
        for pi in items:
            if pi.item.tipe_item not in ('RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'):
                continue
            if pi.sub_transaction_type.direction != 'inflow':
                continue

            is_bulk = pi.item.tipe_item in ('RMB', 'FGB', 'ITMB')
            batch = pi.fifo_batches.get()
            rec = InventoryRecord.objects.get(purchase_item=pi)
            qty = Decimal('1') if is_bulk else pi.quantity
            unit_cost = pi.total_value if is_bulk else pi.unit_price

            mv = record_inflow(
                pi.item, eb_group.entitas_bisnis,
                eb_group.entitas_bisnis_lv2, eb_group.entitas_bisnis_lv3,
                qty, unit_cost, purchase_header.tanggal, 'purchase_in',
                source=pi, legacy_fifo_batch=batch, legacy_inventory_record=rec,
            )
            movements.append(mv)

    return movements


def reverse_inventory_records(purchase_header: PurchaseHeader) -> None:
    """Delete inventory records created by this purchase."""
    InventoryRecord.objects.filter(
        purchase_item__purchase_eb__purchase_header=purchase_header,
    ).delete()


def reverse_aset_tetap_records(purchase_header: PurchaseHeader) -> None:
    """Delete AsetTetapRecord entries created by this purchase."""
    AsetTetapRecord.objects.filter(
        purchase_item__purchase_eb__purchase_header=purchase_header,
    ).delete()


def reverse_aset_lainnya_records(purchase_header: PurchaseHeader) -> None:
    """Delete AsetLainnyaRecord entries created by this purchase."""
    AsetLainnyaRecord.objects.filter(
        purchase_item__purchase_eb__purchase_header=purchase_header,
    ).delete()


def create_aset_tetap_records(purchase_header: PurchaseHeader) -> list[AsetTetapRecord]:
    """Create AsetTetapRecord for each ATP purchase item (inflow only)."""
    records: list[AsetTetapRecord] = []
    for eb_group in purchase_header.entitas_groups.select_related('entitas_bisnis').all():
        items = eb_group.items.select_related('item', 'sub_transaction_type').all()
        for pi in items:
            if pi.item.tipe_item != 'ATP':
                continue
            if pi.sub_transaction_type.direction != 'inflow':
                continue
            record = AsetTetapRecord(
                item=pi.item,
                purchase_item=pi,
                entitas_bisnis=eb_group.entitas_bisnis,
                quantity=pi.quantity,
                harga_perolehan=pi.unit_price,
                tanggal_perolehan=purchase_header.tanggal,
                masa_manfaat=pi.item.masa_manfaat or None,
                metode_penyusutan=pi.item.metode_penyusutan or '',
            )
            record.save()
            records.append(record)
    return records


def create_aset_lainnya_records(purchase_header: PurchaseHeader) -> list[AsetLainnyaRecord]:
    """Create AsetLainnyaRecord for each ALL purchase item (inflow only)."""
    records: list[AsetLainnyaRecord] = []
    for eb_group in purchase_header.entitas_groups.select_related('entitas_bisnis').all():
        items = eb_group.items.select_related('item', 'sub_transaction_type').all()
        for pi in items:
            if pi.item.tipe_item != 'ALL':
                continue
            if pi.sub_transaction_type.direction != 'inflow':
                continue
            record = AsetLainnyaRecord(
                item=pi.item,
                purchase_item=pi,
                entitas_bisnis=eb_group.entitas_bisnis,
                quantity=pi.quantity,
                harga_perolehan=pi.unit_price,
                tanggal_perolehan=purchase_header.tanggal,
                masa_manfaat=pi.item.masa_manfaat or None,
                metode_amortisasi=pi.item.metode_amortisasi or '',
            )
            record.save()
            records.append(record)
    return records


def _next_purchase_journal_number() -> str:
    """Generate sequential journal number for purchase journals."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-PUR-')
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
    return f'TRX-PUR-{seq:03d}'
