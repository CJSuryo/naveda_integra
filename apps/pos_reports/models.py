from decimal import Decimal
from django.db import models


class DailySalesSnapshot(models.Model):
    """Generated at shift close — NOT computed live. Use for fast dashboard queries."""
    store                = models.ForeignKey('pos_config.StorePOSConfig', on_delete=models.CASCADE, related_name='daily_snapshots')
    date                 = models.DateField(db_index=True)
    shift_log            = models.ForeignKey('pos_config.ShiftLog', on_delete=models.SET_NULL, null=True, blank=True)
    total_orders         = models.IntegerField(default=0)
    total_items          = models.IntegerField(default=0)
    gross_sales          = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_discount       = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_tax            = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_service_charge = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    net_sales            = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_cogs           = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    gross_profit         = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    cash_collected       = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    qris_collected       = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    transfer_collected   = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    total_refunds        = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('store', 'date')
        ordering = ['-date']

    def __str__(self):
        return f'{self.store.entitas_bisnis_lv2.nama} — {self.date}'
