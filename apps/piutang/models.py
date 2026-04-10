"""Piutang models."""
from django.db import models


class PiutangHeader(models.Model):
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='piutang_headers',
    )
    dll = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Piutang Header'
        verbose_name_plural = 'Piutang Header'
        indexes = [
            # Per-entity receivable lookups
            models.Index(fields=['entitas_bisnis'], name='idx_ph_entitas'),
        ]

    def __str__(self) -> str:
        return f'Piutang {self.id} - {self.entitas_bisnis}'


class PiutangDetail(models.Model):
    piutang_header = models.ForeignKey(PiutangHeader, on_delete=models.CASCADE, related_name='details')
    dll = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = 'Piutang Detail'
        verbose_name_plural = 'Piutang Detail'

    def __str__(self) -> str:
        return f'Detail {self.id} - Header {self.piutang_header_id}'
