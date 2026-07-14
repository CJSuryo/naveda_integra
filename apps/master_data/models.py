"""Master data models: Aset, Kewajiban, Ekuitas, Pendapatan, Beban, TipeTransaksi, Akun, Bukti."""
from django.db import models


# ── Aset ─────────────────────────────────────────────────────────────────────

class AsetLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Aset Level 1'
        verbose_name_plural = 'Aset Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class AsetLv2(models.Model):
    aset = models.ForeignKey(AsetLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Aset Level 2'
        verbose_name_plural = 'Aset Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Kewajiban ─────────────────────────────────────────────────────────────────

class KewajibanLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Kewajiban Level 1'
        verbose_name_plural = 'Kewajiban Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class KewajibanLv2(models.Model):
    kewajiban = models.ForeignKey(KewajibanLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Kewajiban Level 2'
        verbose_name_plural = 'Kewajiban Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Ekuitas ───────────────────────────────────────────────────────────────────

class EkuitasLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Ekuitas Level 1'
        verbose_name_plural = 'Ekuitas Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class EkuitasLv2(models.Model):
    ekuitas = models.ForeignKey(EkuitasLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Ekuitas Level 2'
        verbose_name_plural = 'Ekuitas Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Pendapatan ───────────────────────────────────────────────────────────────

class PendapatanLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Pendapatan Level 1'
        verbose_name_plural = 'Pendapatan Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class PendapatanLv2(models.Model):
    pendapatan = models.ForeignKey(PendapatanLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Pendapatan Level 2'
        verbose_name_plural = 'Pendapatan Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Beban ────────────────────────────────────────────────────────────────────

class BebanLv1(models.Model):
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Beban Level 1'
        verbose_name_plural = 'Beban Level 1'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


class BebanLv2(models.Model):
    beban = models.ForeignKey(BebanLv1, on_delete=models.CASCADE, related_name='children', null=True, blank=True)
    kode = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Beban Level 2'
        verbose_name_plural = 'Beban Level 2'

    def __str__(self) -> str:
        return f'{self.kode} - {self.nama}'


# ── Akun ──────────────────────────────────────────────────────────────────────

# Prefix used to build the "Kode Akun" string (e.g. 1.1.8 for Aset)
KATEGORI_PREFIX = {
    'aset': '1',
    'kewajiban': '2',
    'ekuitas': '3',
    'pendapatan': '4',
    'beban': '5',
}


def _compute_kode_akun(kategori_id: str, kategori_akun: int | None) -> str:
    """Compute the Kode Akun string from the Lv2 record.

    The Lv2 ``kode`` field already contains the full hierarchical path
    (e.g. ``1.1.1`` for Aset Lv1=1 → Lv2=1).  We simply return that value
    so the Akun ``kode_akun`` matches the displayed code in the CoA tree.
    """
    prefix = KATEGORI_PREFIX.get(kategori_id, '?')
    if not kategori_akun:
        return f'{prefix}.?.?'

    MODEL_MAP: dict[str, type[models.Model]] = {
        'aset': AsetLv2,
        'kewajiban': KewajibanLv2,
        'ekuitas': EkuitasLv2,
        'pendapatan': PendapatanLv2,
        'beban': BebanLv2,
    }

    lv2_model = MODEL_MAP.get(kategori_id)
    if lv2_model:
        kode = lv2_model.objects.filter(pk=kategori_akun).values_list('kode', flat=True).first()
        if kode:
            return kode

    return f'{prefix}.?.?'


class Akun(models.Model):
    KATEGORI_CHOICES = [
        ('aset', 'Aset'),
        ('kewajiban', 'Kewajiban'),
        ('ekuitas', 'Ekuitas'),
        ('pendapatan', 'Pendapatan'),
        ('beban', 'Beban'),
    ]
    kategori_id = models.CharField(max_length=50, choices=KATEGORI_CHOICES, db_index=True)
    kategori_akun = models.BigIntegerField(null=True, blank=True, db_index=True)
    nama = models.CharField(max_length=255, blank=True, default='')
    kode_akun = models.CharField(max_length=50, blank=True, default='', db_index=True)
    is_kas_setara = models.BooleanField(
        default=False,
        verbose_name='Kas/Setara Kas',
        help_text='Centang jika akun ini kas/bank (dibayar tunai). Biarkan kosong untuk akun piutang/kredit.',
    )

    class Meta:
        verbose_name = 'Akun'
        verbose_name_plural = 'Akun'
        indexes = [
            # Composite index for chart-of-accounts lookups by category + sub-category
            models.Index(fields=['kategori_id', 'kategori_akun'], name='idx_akun_kategori'),
        ]

    def __str__(self) -> str:
        return f'{self.kode_akun} - {self.nama}' if self.nama else f'Akun {self.id} ({self.kategori_id})'

    def get_lv2_url(self) -> str | None:
        """Return the URL to the associated Lv1 detail page (which lists Lv2 records), or None."""
        from django.urls import reverse
        if not self.kategori_akun:
            return None
        if self.kategori_id == 'aset':
            lv1_pk = AsetLv2.objects.filter(pk=self.kategori_akun).values_list('aset_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:aset_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'kewajiban':
            lv1_pk = KewajibanLv2.objects.filter(pk=self.kategori_akun).values_list('kewajiban_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:kewajiban_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'ekuitas':
            lv1_pk = EkuitasLv2.objects.filter(pk=self.kategori_akun).values_list('ekuitas_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:ekuitas_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'pendapatan':
            lv1_pk = PendapatanLv2.objects.filter(pk=self.kategori_akun).values_list('pendapatan_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:pendapatan_lv1_detail', args=[lv1_pk])
        elif self.kategori_id == 'beban':
            lv1_pk = BebanLv2.objects.filter(pk=self.kategori_akun).values_list('beban_id', flat=True).first()
            if lv1_pk:
                return reverse('master_data:beban_lv1_detail', args=[lv1_pk])
        return None


# ── TipeTransaksi ─────────────────────────────────────────────────────────────

class TipeTransaksi(models.Model):
    kode_transaksi = models.CharField(max_length=50, unique=True)
    nama = models.CharField(max_length=255)

    class Meta:
        verbose_name = 'Tipe Transaksi'
        verbose_name_plural = 'Tipe Transaksi'

    def __str__(self) -> str:
        return f'{self.kode_transaksi} - {self.nama}'


# ── Entitas Bisnis — Akun Available ──────────────────────────────────────────

class EntitasBisnisAkun(models.Model):
    """Links an Entitas Bisnis to available Akun from Chart of Accounts.

    Used to filter which akuns are available for journal entries per EB.
    """
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        related_name='available_akuns',
        verbose_name='Entitas Bisnis',
    )
    akun = models.ForeignKey(
        Akun,
        on_delete=models.CASCADE,
        related_name='entitas_bisnis_links',
        verbose_name='Akun',
    )

    class Meta:
        verbose_name = 'Entitas Bisnis Akun'
        verbose_name_plural = 'Entitas Bisnis Akun'
        unique_together = [('entitas_bisnis', 'akun')]
        indexes = [
            models.Index(fields=['entitas_bisnis', 'akun'], name='idx_eba_eb_akun'),
        ]

    def __str__(self) -> str:
        return f'{self.entitas_bisnis} → {self.akun}'


# ── Bukti ─────────────────────────────────────────────────────────────────────

class Bukti(models.Model):
    referensi_eksternal = models.CharField(max_length=100)
    tipe_dokumen = models.CharField(max_length=50)
    filepath = models.CharField(max_length=512)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(max_length=256)

    class Meta:
        verbose_name = 'Bukti'
        verbose_name_plural = 'Bukti'
        indexes = [
            # Document lookups by external reference + type
            models.Index(fields=['referensi_eksternal', 'tipe_dokumen'], name='idx_bukti_ref_tipe'),
            # Duplicate-detection by file hash
            models.Index(fields=['file_hash'], name='idx_bukti_hash'),
        ]

    def __str__(self) -> str:
        return f'{self.tipe_dokumen} - {self.referensi_eksternal}'
