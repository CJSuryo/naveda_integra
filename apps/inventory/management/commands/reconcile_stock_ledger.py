"""Reconcile StockMovement remaining vs legacy FIFOBatch/InventoryRecord."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.purchase.models import FIFOBatch
from apps.inventory.models import StockMovement, InventoryRecord


class Command(BaseCommand):
    help = 'Report drift between StockMovement and legacy stock ledgers.'

    def handle(self, *args, **options):
        drift = 0
        # 1. Per item: sum(StockMovement.remaining inflow) vs sum(FIFOBatch.remaining)
        items = set(FIFOBatch.objects.values_list('item_id', flat=True))
        items |= set(StockMovement.objects.values_list('item_id', flat=True))
        for item_id in sorted(i for i in items if i is not None):
            sm = (StockMovement.objects.filter(item_id=item_id, qty__gt=0)
                  .aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0'))
            fb = (FIFOBatch.objects.filter(item_id=item_id)
                  .aggregate(s=Sum('remaining_qty'))['s'] or Decimal('0'))
            if sm != fb:
                drift += 1
                self.stdout.write(self.style.WARNING(
                    f'[item {item_id}] StockMovement={sm} vs FIFOBatch={fb} (diff {sm - fb})'))
        # 2. FIFOBatch tanpa StockMovement tertaut (EB tak teratribusi / anomali)
        orphan = FIFOBatch.objects.exclude(
            id__in=StockMovement.objects.filter(
                legacy_fifo_batch__isnull=False).values_list('legacy_fifo_batch_id', flat=True)
        ).count()
        if orphan:
            drift += 1
            self.stdout.write(self.style.WARNING(
                f'{orphan} FIFOBatch tanpa StockMovement tertaut (cek atribusi EB).'))
        if drift == 0:
            self.stdout.write(self.style.SUCCESS('Rekonsiliasi cocok: tidak ada drift.'))
        else:
            self.stdout.write(self.style.ERROR(f'Ditemukan {drift} kategori drift.'))
