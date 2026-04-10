"""Jurnal models."""
from django.db import models


class JurnalHeader(models.Model):
    tanggal = models.DateField()
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

    def __str__(self) -> str:
        return f'Detail {self.id} - Header {self.jurnal_header_id}'
