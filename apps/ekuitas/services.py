"""Ekuitas services — journal generation for Modal Disetor transactions."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.master_data.models import Akun

from .models import ModalDisetor, ModalDisetorDebit, Pemilik


def _next_modal_disetor_journal_number() -> str:
    """Generate sequential journal number for modal disetor journals (TRX-MD-001)."""
    last = (
        JurnalHeader.objects
        .filter(nomor_transaksi__startswith='TRX-MD-')
        .order_by('-nomor_transaksi')
        .values_list('nomor_transaksi', flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit('-', 1)[1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'TRX-MD-{seq:03d}'


def get_or_create_pemilik(nama: str) -> Pemilik:
    """Get existing Pemilik by name (case-insensitive) or create a new one."""
    pemilik = Pemilik.objects.filter(nama__iexact=nama.strip()).first()
    if not pemilik:
        pemilik = Pemilik.objects.create(nama=nama.strip())
    return pemilik


def create_modal_disetor(
    *,
    entitas_bisnis_id: int,
    pemilik_id: int,
    tanggal,
    jumlah_modal: Decimal,
    keterangan: str,
    debit_lines: list[dict[str, Any]],
) -> ModalDisetor:
    """Create a ModalDisetor record and its journal entry.

    Journal:
        Debit:  user-selected asset accounts (sum = jumlah_modal)
        Credit: Akun Modal Disetor (kode_akun starts with 3.1.1)

    Args:
        entitas_bisnis_id: PK of EntitasBisnis.
        pemilik_id: PK of Pemilik.
        tanggal: Date of the contribution.
        jumlah_modal: Total capital contributed.
        keterangan: Optional description.
        debit_lines: List of {'akun_id': int, 'jumlah': Decimal/str} dicts.

    Returns:
        The created ModalDisetor instance.

    Raises:
        ValueError: if validation fails (sum mismatch, missing accounts, etc.)
    """
    if not debit_lines:
        raise ValueError('Minimal 1 baris akun debit wajib diisi.')

    # Validate debit line amounts
    total_debit = Decimal('0')
    for d in debit_lines:
        try:
            j = Decimal(str(d.get('jumlah', 0)))
        except Exception:
            raise ValueError(f'Jumlah tidak valid: {d.get("jumlah")}')
        if j <= 0:
            raise ValueError('Setiap baris debit harus memiliki jumlah lebih dari 0.')
        total_debit += j

    if abs(total_debit - jumlah_modal) > Decimal('0.01'):
        raise ValueError(
            f'Total debit (Rp {total_debit:,.0f}) harus sama dengan '
            f'jumlah modal disetor (Rp {jumlah_modal:,.0f}).'
        )

    # Resolve pemilik
    try:
        pemilik = Pemilik.objects.get(pk=pemilik_id)
    except Pemilik.DoesNotExist:
        raise ValueError('Pemilik tidak ditemukan.')

    # Find Modal Disetor kredit akun (3.1.1.xx)
    modal_akun = Akun.objects.filter(kode_akun__startswith='3.1.1').first()
    if not modal_akun:
        raise ValueError('Akun Modal Disetor (3.1.1.xx) belum tersedia di Chart of Accounts.')

    # Resolve all debit akun
    akun_ids = []
    for d in debit_lines:
        try:
            akun_ids.append(int(d['akun_id']))
        except (KeyError, TypeError, ValueError):
            raise ValueError(f'akun_id tidak valid: {d.get("akun_id")}')
    akun_map = {a.pk: a for a in Akun.objects.filter(pk__in=akun_ids)}
    for aid in akun_ids:
        if aid not in akun_map:
            raise ValueError(f'Akun ID {aid} tidak ditemukan.')

    with transaction.atomic():
        nomor = _next_modal_disetor_journal_number()
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=f'Modal Disetor — {pemilik.nama}',
            entitas_bisnis_id=entitas_bisnis_id,
            is_penyesuaian=False,
        )

        # Debit lines
        details = [
            JurnalDetail(
                jurnal_header=header,
                akun=akun_map[int(d['akun_id'])],
                debit=Decimal(str(d['jumlah'])),
                kredit=Decimal('0'),
            )
            for d in debit_lines
        ]
        # Kredit line — Modal Disetor akun
        details.append(
            JurnalDetail(
                jurnal_header=header,
                akun=modal_akun,
                debit=Decimal('0'),
                kredit=jumlah_modal,
            )
        )
        JurnalDetail.objects.bulk_create(details)

        record = ModalDisetor.objects.create(
            entitas_bisnis_id=entitas_bisnis_id,
            pemilik=pemilik,
            jumlah_modal=jumlah_modal,
            tanggal_setor=tanggal,
            keterangan=keterangan,
            jurnal_header=header,
        )
        ModalDisetorDebit.objects.bulk_create([
            ModalDisetorDebit(
                modal_disetor=record,
                akun=akun_map[int(d['akun_id'])],
                jumlah=Decimal(str(d['jumlah'])),
            )
            for d in debit_lines
        ])

    return record


def delete_modal_disetor(record: ModalDisetor) -> None:
    """Delete a ModalDisetor and its journal entry (if standalone)."""
    with transaction.atomic():
        header = record.jurnal_header
        record.delete()  # CASCADE deletes ModalDisetorDebit rows
        if header and not header.is_saldo_awal:
            header.details.all().delete()
            header.delete()
