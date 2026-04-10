"""Jurnal models."""
from django.db import models


class JurnalHeader(models.Model):
    tanggal = models.DateField(db_index=True)
    uraian_transaksi = models.CharField(max_length=512)
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jurnal_headers',
    )
    no_bukti = models.ForeignKey(
        'master_data.Bukti',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jurnal_headers',
    )
    tipe_transaksi = models.ForeignKey(
        'master_data.TipeTransaksi',
        on_delete=models.PROTECT,
        related_name='jurnal_headers',
    )
    item = models.ForeignKey(
        'sales.ItemMaster',
        on_delete=models.PROTECT,
        related_name='jurnal_headers',
    )

    class Meta:
        verbose_name = 'Jurnal Header'
        verbose_name_plural = 'Jurnal Header'
        ordering = ['-tanggal']
        indexes = [
            # Date-range queries filtered by transaction type (monthly closing, reports)
            models.Index(fields=['tanggal', 'tipe_transaksi'], name='idx_jh_tanggal_tipe'),
            # Per-entity journal lookups (all journals for a business entity)
            models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_jh_entitas_tanggal'),
            # Per-item journal lookups
            models.Index(fields=['item'], name='idx_jh_item'),
        ]

    def __str__(self) -> str:
        return f'{self.tanggal} - {self.uraian_transaksi[:50]}'


class JurnalDetail(models.Model):
    jurnal_header = models.ForeignKey(JurnalHeader, on_delete=models.CASCADE, related_name='details')
    akun = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='jurnal_details')
    debit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    kredit = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Jurnal Detail'
        verbose_name_plural = 'Jurnal Detail'
        indexes = [
            # Trial balance / general ledger: SUM(debit), SUM(kredit) GROUP BY akun
            models.Index(fields=['akun', 'jurnal_header'], name='idx_jd_akun_header'),
            # Header→detail join (fetch all lines for a single journal entry)
            models.Index(fields=['jurnal_header', 'akun'], name='idx_jd_header_akun'),
        ]

    def __str__(self) -> str:
        return f'Detail {self.id} - Header {self.jurnal_header_id}'
