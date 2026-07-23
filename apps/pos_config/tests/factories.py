"""Shared builders for the EntitasBisnis → POS config hierarchy.

lv1 (group) → lv2 (operating company, holds MerchantPOSConfig)
            → lv3 (branch, holds StorePOSConfig)
"""
from apps.entitas_bisnis.models import EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3, TipeEntitas
from pos_config.models import MerchantPOSConfig, StorePOSConfig


def make_tipe(nama='FnB'):
    return TipeEntitas.objects.get_or_create(nama=nama)[0]


def make_lv1(nama='Grup Naveda', tipe=None):
    return EntitasBisnis.objects.create(
        nama=nama, tipe_entitas=tipe or make_tipe(), relasi='pelanggan'
    )


def make_lv2(lv1=None, nama='PT Kafe Naveda'):
    return EntitasBisnisLv2.objects.create(entitas_bisnis=lv1 or make_lv1(), nama=nama)


def make_lv3(lv2=None, nama='Cabang Sudirman'):
    return EntitasBisnisLv3.objects.create(parent_lv2=lv2 or make_lv2(), nama=nama)


def make_merchant(lv2=None, **kwargs):
    return MerchantPOSConfig.objects.create(entitas_bisnis_lv2=lv2 or make_lv2(), **kwargs)


def make_store(merchant=None, lv3=None, **kwargs):
    merchant = merchant or make_merchant()
    lv3 = lv3 or make_lv3(lv2=merchant.entitas_bisnis_lv2)
    return StorePOSConfig.objects.create(
        entitas_bisnis_lv3=lv3, merchant_config=merchant, **kwargs
    )


def make_hierarchy(**merchant_kwargs):
    """Return (lv1, lv2, lv3, merchant, store) fully wired."""
    lv1 = make_lv1()
    lv2 = make_lv2(lv1)
    lv3 = make_lv3(lv2)
    merchant = make_merchant(lv2, **merchant_kwargs)
    store = make_store(merchant, lv3)
    return lv1, lv2, lv3, merchant, store
