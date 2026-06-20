# tests/customers/factories.py
def make_user(email='testuser@example.com', name='Test User'):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.get_or_create(email=email, defaults={'name': name})[0]


def make_tipe_entitas(nama='Test Tipe'):
    from apps.entitas_bisnis.models import TipeEntitas
    return TipeEntitas.objects.get_or_create(nama=nama)[0]


def make_eb(**kwargs):
    from apps.entitas_bisnis.models import EntitasBisnis
    if 'tipe_entitas' not in kwargs:
        kwargs['tipe_entitas'] = make_tipe_entitas()
    nama = kwargs.pop('nama', 'Test EB')
    return EntitasBisnis.objects.get_or_create(nama=nama, defaults=kwargs)[0]


def make_eb_lv2(eb=None, nama='Test EB Lv2'):
    from apps.entitas_bisnis.models import EntitasBisnisLv2
    if eb is None:
        eb = make_eb()
    return EntitasBisnisLv2.objects.get_or_create(nama=nama, entitas_bisnis=eb)[0]


def make_eb_lv3(lv2=None, nama='Test EB Lv3'):
    from apps.entitas_bisnis.models import EntitasBisnisLv3
    if lv2 is None:
        lv2 = make_eb_lv2()
    return EntitasBisnisLv3.objects.get_or_create(nama=nama, parent_lv2=lv2)[0]


def make_customer(eb=None, **kwargs):
    from apps.customers.models import Customer
    if eb is None:
        eb = make_eb()
    kwargs.setdefault('nama', 'Budi Santoso')
    return Customer.objects.create(entitas_bisnis=eb, **kwargs)
