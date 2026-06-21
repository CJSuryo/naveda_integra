# apps/customers/models.py
import datetime
from django.db import models


class Customer(models.Model):
    GENDER_CHOICES = [
        ('L', 'Laki-laki'),
        ('P', 'Perempuan'),
        ('O', 'Lainnya'),
    ]

    nama             = models.CharField(max_length=200)
    email            = models.EmailField(blank=True, null=True)
    telepon          = models.CharField(max_length=20, blank=True, null=True)
    alamat           = models.TextField(blank=True, null=True)
    npwp             = models.CharField(max_length=20, blank=True, null=True, unique=True)
    gender           = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    tanggal_lahir    = models.DateField(blank=True, null=True)

    entitas_bisnis     = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.PROTECT,
        related_name='customers',
    )
    entitas_bisnis_lv2 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv2',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customers',
    )
    entitas_bisnis_lv3 = models.ForeignKey(
        'entitas_bisnis.EntitasBisnisLv3',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customers',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['nama']
        indexes = [
            models.Index(fields=['entitas_bisnis', 'nama'], name='idx_customer_eb_nama'),
        ]

    def __str__(self) -> str:
        return self.nama

    @property
    def umur(self) -> int | None:
        if not self.tanggal_lahir:
            return None
        today = datetime.date.today()
        return today.year - self.tanggal_lahir.year - (
            (today.month, today.day) < (self.tanggal_lahir.month, self.tanggal_lahir.day)
        )
