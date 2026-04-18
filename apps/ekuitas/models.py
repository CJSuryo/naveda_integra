"""Ekuitas models — Pemilik, Modal Disetor (paid-in capital), and debit lines."""
from django.db import models
from django.utils import timezone


class Pemilik(models.Model):
    """Pemilik bisnis — tidak harus system user, hanya pencatatan data pemilik."""
    nama = models.CharField(max_length=255, unique=True, verbose_name='Nama Pemilik')
    keterangan = models.TextField(blank=True, verbose_name='Keterangan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pemilik'
        verbose_name_plural = 'Pemilik'
        ordering = ['nama']

    def __str__(self) -> str:
        return self.nama


class ModalDisetor(models.Model):
    """Modal Disetor — pencatatan setoran modal dari seorang pemilik."""
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='modal_disetors',
        verbose_name='Entitas Bisnis',
    )
    pemilik = models.ForeignKey(
        Pemilik,
        on_delete=models.PROTECT,
        related_name='modal_disetors',
        verbose_name='Pemilik',
    )
    jumlah_modal = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Jumlah Modal Disetor',
    )
    persentase_kepemilikan = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Persentase Kepemilikan (%)',
        help_text='Opsional. Jika kosong, dihitung otomatis dari total modal entitas.',
    )
    tanggal_setor = models.DateField(
        db_index=True,
        default=timezone.now,
        verbose_name='Tanggal Setor',
    )
    keterangan = models.TextField(blank=True, verbose_name='Keterangan')
    jurnal_header = models.ForeignKey(
        'jurnal.JurnalHeader',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='modal_disetors',
        verbose_name='Jurnal',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Modal Disetor'
        verbose_name_plural = 'Modal Disetor'
        ordering = ['-tanggal_setor', '-created_at']
        indexes = [
            models.Index(fields=['entitas_bisnis', 'tanggal_setor'], name='idx_md_eb_tanggal'),
        ]

    def __str__(self) -> str:
        return f'{self.pemilik.nama} — Rp {self.jumlah_modal:,.0f} ({self.entitas_bisnis})'


class ModalDisetorDebit(models.Model):
    """Baris debit akun aset untuk satu transaksi Modal Disetor."""
    modal_disetor = models.ForeignKey(
        ModalDisetor,
        on_delete=models.CASCADE,
        related_name='debit_lines',
        verbose_name='Modal Disetor',
    )
    akun = models.ForeignKey(
        'master_data.Akun',
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name='Akun',
    )
    jumlah = models.DecimalField(max_digits=19, decimal_places=4, verbose_name='Jumlah')

    class Meta:
        verbose_name = 'Debit Modal Disetor'
        verbose_name_plural = 'Debit Modal Disetor'

    def __str__(self) -> str:
        return f'{self.akun} — Rp {self.jumlah:,.0f}'
