"""Ekuitas models — Modal Disetor (paid-in capital) and ownership tracking."""
from django.db import models
from django.utils import timezone


class ModalDisetor(models.Model):
    """Modal Disetor — tracks capital contributions by owners to a business entity."""
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='modal_disetors',
        verbose_name='Entitas Bisnis',
    )
    nama_pemilik = models.CharField(
        max_length=255,
        verbose_name='Nama Pemilik',
    )
    jumlah_modal = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        verbose_name='Jumlah Modal Disetor',
    )
    persentase_kepemilikan = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        verbose_name='Persentase Kepemilikan (%)',
        help_text='Contoh: 25.0000 = 25%',
    )
    tanggal_setor = models.DateField(
        db_index=True,
        default=timezone.now,
        verbose_name='Tanggal Setor',
    )
    keterangan = models.TextField(
        blank=True,
        verbose_name='Keterangan',
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
        return f'{self.nama_pemilik} — Rp {self.jumlah_modal:,.0f} ({self.entitas_bisnis})'
