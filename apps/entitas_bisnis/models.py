"""EntitasBisnis model."""
from django.conf import settings
from django.db import models


class EntitasBisnis(models.Model):
    TIPE_CHOICES = [
        ('pelanggan', 'Pelanggan'),
        ('pemasok', 'Pemasok'),
        ('keduanya', 'Keduanya'),
    ]

    nama = models.CharField(max_length=255)
    tipe_entitas = models.CharField(max_length=50, choices=TIPE_CHOICES)
    email = models.EmailField(blank=True, null=True)
    telepon = models.CharField(max_length=50, blank=True, null=True)
    alamat_lengkap = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    tanggal_bergabung = models.DateField(blank=True, null=True)
    status_aktif = models.BooleanField(default=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='entitas_bisnis_set',
        blank=True,
        verbose_name='Users',
    )

    class Meta:
        verbose_name = 'Entitas Bisnis'
        verbose_name_plural = 'Entitas Bisnis'

    def __str__(self) -> str:
        return self.nama
