"""Signals to auto-sync Akun records when Lv2 entries are saved or deleted."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    AsetLv2, KewajibanLv2, EkuitasLv2, PendapatanLv2, BebanLv2,
    Akun, _compute_kode_akun,
)


def _sync_akun(kategori: str, lv2_instance) -> None:
    """Create or update an Akun row that mirrors the given Lv2 record."""
    kode = _compute_kode_akun(kategori, lv2_instance.pk)
    Akun.objects.update_or_create(
        kategori_id=kategori,
        kategori_akun=lv2_instance.pk,
        defaults={'nama': lv2_instance.nama, 'kode_akun': kode},
    )


def _delete_akun(kategori: str, lv2_pk: int) -> None:
    """Remove the Akun row that mirrors the deleted Lv2 record."""
    Akun.objects.filter(kategori_id=kategori, kategori_akun=lv2_pk).delete()


# ── Aset Lv2 ─────────────────────────────────────────────────────────────────

@receiver(post_save, sender=AsetLv2)
def sync_akun_on_aset_lv2_save(sender, instance, **kwargs):
    _sync_akun('aset', instance)


@receiver(post_delete, sender=AsetLv2)
def delete_akun_on_aset_lv2_delete(sender, instance, **kwargs):
    _delete_akun('aset', instance.pk)


# ── Kewajiban Lv2 ────────────────────────────────────────────────────────────

@receiver(post_save, sender=KewajibanLv2)
def sync_akun_on_kewajiban_lv2_save(sender, instance, **kwargs):
    _sync_akun('kewajiban', instance)


@receiver(post_delete, sender=KewajibanLv2)
def delete_akun_on_kewajiban_lv2_delete(sender, instance, **kwargs):
    _delete_akun('kewajiban', instance.pk)


# ── Ekuitas Lv2 ──────────────────────────────────────────────────────────────

@receiver(post_save, sender=EkuitasLv2)
def sync_akun_on_ekuitas_lv2_save(sender, instance, **kwargs):
    _sync_akun('ekuitas', instance)


@receiver(post_delete, sender=EkuitasLv2)
def delete_akun_on_ekuitas_lv2_delete(sender, instance, **kwargs):
    _delete_akun('ekuitas', instance.pk)


# ── Pendapatan Lv2 ───────────────────────────────────────────────────────────

@receiver(post_save, sender=PendapatanLv2)
def sync_akun_on_pendapatan_lv2_save(sender, instance, **kwargs):
    _sync_akun('pendapatan', instance)


@receiver(post_delete, sender=PendapatanLv2)
def delete_akun_on_pendapatan_lv2_delete(sender, instance, **kwargs):
    _delete_akun('pendapatan', instance.pk)


# ── Beban Lv2 ────────────────────────────────────────────────────────────────

@receiver(post_save, sender=BebanLv2)
def sync_akun_on_beban_lv2_save(sender, instance, **kwargs):
    _sync_akun('beban', instance)


@receiver(post_delete, sender=BebanLv2)
def delete_akun_on_beban_lv2_delete(sender, instance, **kwargs):
    _delete_akun('beban', instance.pk)
