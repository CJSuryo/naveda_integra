from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.jurnal.utils import log_jurnal_terhapus

from .models import UtangHeader, UtangDetail, UtangPembayaran


def create_manual_utang(
    tanggal,
    entitas_bisnis,
    coa_utang_account,
    total_amount,
    deskripsi,
) -> UtangHeader:
    utang = UtangHeader.objects.create(
        tanggal=tanggal,
        entitas_bisnis=entitas_bisnis,
        deskripsi=deskripsi,
        total_amount=total_amount,
        status='open',
    )
    UtangDetail.objects.create(
        utang_header=utang,
        coa_utang_account=coa_utang_account,
        description='Saldo awal utang',
        amount=total_amount,
    )
    return utang


def create_utang_for_purchase(purchase_header):
    items = (
        purchase_header.entitas_groups
        .prefetch_related('items__offset_coa_account', 'items__item')
        .all()
    )
    credit_items = []
    for eb_group in items:
        for item in eb_group.items.all():
            if item.offset_coa_account and item.offset_coa_account.kategori_id == 'kewajiban':
                credit_items.append((eb_group, item))

    if not credit_items:
        return None

    groups: dict[tuple[int, int], list] = {}
    for eb_group, item in credit_items:
        key = (item.offset_coa_account_id, eb_group.entitas_bisnis_id)
        groups.setdefault(key, []).append((eb_group, item))

    utang_headers = []
    for (coa_id, eb_id), entries in groups.items():
        total_amount = sum(item.total_value for _, item in entries)
        header = UtangHeader.objects.create(
            purchase_header=purchase_header,
            tanggal=purchase_header.tanggal,
            entitas_bisnis_id=eb_id,
            deskripsi=f'Utang dari {purchase_header.transaction_id}',
            total_amount=total_amount,
            status='open',
        )
        for eb_group, item in entries:
            UtangDetail.objects.create(
                utang_header=header,
                purchase_item=item,
                coa_utang_account=item.offset_coa_account,
                description=str(item.item),
                amount=item.total_value,
            )
        utang_headers.append(header)

    return utang_headers


def create_utang_payment(utang_header: UtangHeader, utang_detail, tanggal, coa_account, jumlah, keterangan):
    outstanding = utang_header.outstanding_amount
    if jumlah <= 0:
        raise ValueError('Jumlah pembayaran harus lebih besar dari 0.')
    if jumlah > outstanding:
        raise ValueError('Jumlah pembayaran tidak boleh melebihi sisa utang.')

    with transaction.atomic():
        payment = UtangPembayaran.objects.create(
            utang_header=utang_header,
            utang_detail=utang_detail,
            tanggal=tanggal,
            coa_account=coa_account,
            jumlah=jumlah,
            keterangan=keterangan,
        )
        journal = _create_utang_payment_journal(payment)
        payment.jurnal_header = journal
        payment.save(update_fields=['jurnal_header'])
        _update_utang_status(utang_header)
        return payment


def reverse_utang_header(utang_header: UtangHeader, user=None):
    for payment in utang_header.pembayaran.select_related('jurnal_header').all():
        if payment.jurnal_header_id:
            log_jurnal_terhapus(payment.jurnal_header, 'utang', None)
            payment.jurnal_header.delete()
    utang_header.delete()


def reverse_utang_for_purchase(purchase_header):
    for utang in purchase_header.utang_headers.select_related().all():
        reverse_utang_header(utang)


def _create_utang_payment_journal(payment: UtangPembayaran) -> JurnalHeader:
    utang_header = payment.utang_header
    if payment.utang_detail:
        utang_account = payment.utang_detail.coa_utang_account
    else:
        first_detail = utang_header.details.first()
        utang_account = first_detail.coa_utang_account if first_detail else None
    if not utang_account:
        raise ValueError('Tidak ada akun utang untuk pembayaran ini.')

    nomor = _next_utang_journal_number()
    header = JurnalHeader.objects.create(
        tanggal=payment.tanggal,
        nomor_transaksi=nomor,
        uraian_transaksi=f'Pembayaran Utang {utang_header.nomor_utang}',
        entitas_bisnis=utang_header.entitas_bisnis,
        is_penyesuaian=False,
    )
    JurnalDetail.objects.bulk_create([
        JurnalDetail(
            jurnal_header=header,
            akun=utang_account,
            debit=payment.jumlah,
            kredit=Decimal('0'),
        ),
        JurnalDetail(
            jurnal_header=header,
            akun=payment.coa_account,
            debit=Decimal('0'),
            kredit=payment.jumlah,
        ),
    ])
    return header


def _update_utang_status(utang_header: UtangHeader) -> None:
    paid = utang_header.paid_amount
    if paid >= utang_header.total_amount:
        utang_header.status = 'paid'
    elif paid > 0:
        utang_header.status = 'partial'
    else:
        utang_header.status = 'open'
    utang_header.save(update_fields=['status'])


def _next_utang_journal_number() -> str:
    query = JurnalHeader.objects.filter(nomor_transaksi__startswith='TRX-UTG-')
    seq = 0
    for nomor in query.values_list('nomor_transaksi', flat=True):
        try:
            candidate = int(nomor.rsplit('-', 1)[1])
            if candidate > seq:
                seq = candidate
        except (ValueError, IndexError):
            continue
    return f'TRX-UTG-{seq + 1:04d}'
