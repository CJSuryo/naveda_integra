# tests/pendapatan/factories.py
from decimal import Decimal


def make_user(email='testuser@example.com', name='Test User'):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.get_or_create(email=email, defaults={'name': name})[0]


def make_tipe_entitas(nama='Test Tipe'):
    from apps.entitas_bisnis.models import TipeEntitas
    return TipeEntitas.objects.get_or_create(nama=nama)[0]


def make_entitas_bisnis(**kwargs):
    from apps.entitas_bisnis.models import EntitasBisnis
    # tipe_entitas is required (non-null FK)
    if 'tipe_entitas' not in kwargs:
        kwargs['tipe_entitas'] = make_tipe_entitas()
    nama = kwargs.pop('nama', 'Test EB')
    return EntitasBisnis.objects.get_or_create(
        nama=nama,
        defaults=kwargs,
    )[0]


def make_akun(kode_akun, nama='Test Akun', kategori_id='aset', **kwargs):
    from apps.master_data.models import Akun
    # kategori_id is required; kode_akun and nama have defaults but we set them explicitly
    return Akun.objects.get_or_create(
        kode_akun=kode_akun,
        defaults={'nama': nama, 'kategori_id': kategori_id, **kwargs},
    )[0]


def make_sub_transaction_type(nama='Test STT', module='pendapatan', **kwargs):
    from apps.purchase.models import SubTransactionType
    # default_offset_account is required (non-null FK)
    if 'default_offset_account' not in kwargs:
        kwargs['default_offset_account'] = make_akun('9001', 'Offset Account', 'beban')
    return SubTransactionType.objects.get_or_create(
        nama=nama,
        module=module,
        defaults=kwargs,
    )[0]


def make_header(user=None, **kwargs):
    from apps.pendapatan.models import PendapatanHeader
    if user is None:
        user = make_user()
    return PendapatanHeader.objects.create(
        deskripsi='Test Header',
        payment_type='cash',
        status='draft',
        created_by=user,
        **kwargs,
    )


def make_pendapatan_eb(header, eb=None, payment_account=None):
    from apps.pendapatan.models import PendapatanEntitasBisnis
    if eb is None:
        eb = make_entitas_bisnis()
    # payment_account is nullable on PendapatanEntitasBisnis, so omit if not provided
    create_kwargs = {
        'pendapatan_header': header,
        'entitas_bisnis': eb,
    }
    if payment_account is not None:
        create_kwargs['payment_account'] = payment_account
    return PendapatanEntitasBisnis.objects.create(**create_kwargs)


def make_kp(peb, nilai_kontrak, recognition_type='point_in_time', **kwargs):
    from apps.pendapatan.models import KewajibabPelaksanaan
    revenue_account = kwargs.pop('revenue_account', None) or make_akun('4001', 'Pendapatan Jasa', 'pendapatan')
    stt = kwargs.pop('sub_transaction_type', None) or make_sub_transaction_type()
    return KewajibabPelaksanaan.objects.create(
        pendapatan_eb=peb,
        deskripsi_item='Test KP',
        kategori='jasa',
        sub_transaction_type=stt,
        nilai_kontrak=Decimal(str(nilai_kontrak)),
        revenue_account=revenue_account,
        recognition_type=recognition_type,
        **kwargs,
    )
