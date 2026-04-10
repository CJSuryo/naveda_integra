"""Jurnal models."""
from django.db import models
from django.utils import timezone


# ── Item ──────────────────────────────────────────────────────────────────────

class Item(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Item'
        verbose_name_plural = 'Item'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── TransactionPrefix ────────────────────────────────────────────────────────

class TransactionPrefix(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Prefiks Transaksi'
        verbose_name_plural = 'Prefiks Transaksi'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── JurnalHeader ─────────────────────────────────────────────────────────────

class JurnalHeader(models.Model):
    tanggal = models.DateField(db_index=True, default=timezone.now)
    nomor_transaksi = models.CharField(max_length=100, unique=True)
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
        null=True,
        blank=True,
        related_name='jurnal_headers',
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='jurnal_headers',
    )
    transaction_prefix = models.ForeignKey(
        TransactionPrefix,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='jurnal_headers',
    )

    class Meta:
        verbose_name = 'Jurnal Header'
        verbose_name_plural = 'Jurnal Header'
        ordering = ['-tanggal']
        indexes = [
            models.Index(fields=['tanggal', 'tipe_transaksi'], name='idx_jh_tanggal_tipe'),
            models.Index(fields=['entitas_bisnis', 'tanggal'], name='idx_jh_entitas_tanggal'),
            models.Index(fields=['item'], name='idx_jh_item'),
        ]

    def __str__(self) -> str:
        return f'{self.tanggal} - {self.nomor_transaksi} - {self.uraian_transaksi[:50]}'


class JurnalDetail(models.Model):
    jurnal_header = models.ForeignKey(JurnalHeader, on_delete=models.CASCADE, related_name='details')
    akun = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='jurnal_details')
    debit = models.DecimalField(max_digits=19, decimal_places=4, default=0)
    kredit = models.DecimalField(max_digits=19, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Jurnal Detail'
        verbose_name_plural = 'Jurnal Detail'
        indexes = [
            models.Index(fields=['akun', 'jurnal_header'], name='idx_jd_akun_header'),
            models.Index(fields=['jurnal_header', 'akun'], name='idx_jd_header_akun'),
        ]

    def __str__(self) -> str:
        return f'Detail {self.id} - Header {self.jurnal_header_id}'


# ── Jurnal Automasi ──────────────────────────────────────────────────────────

class JurnalAutomasi(models.Model):
    nama = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = 'Jurnal Automasi'
        verbose_name_plural = 'Jurnal Automasi'

    def __str__(self) -> str:
        return self.nama


class JurnalAutomasiAkun(models.Model):
    automasi = models.ForeignKey(JurnalAutomasi, on_delete=models.CASCADE, related_name='akun_mappings')
    akun = models.ForeignKey('master_data.Akun', on_delete=models.PROTECT, related_name='automasi_mappings')

    class Meta:
        verbose_name = 'Jurnal Automasi Akun'
        verbose_name_plural = 'Jurnal Automasi Akun'
        unique_together = [('automasi', 'akun')]

    def __str__(self) -> str:
        return f'{self.automasi.nama} → {self.akun}'
