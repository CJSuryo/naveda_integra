"""Ekuitas services — journal generation for Modal Disetor transactions."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.jurnal.models import JurnalDetail, JurnalHeader
from apps.jurnal.utils import log_jurnal_terhapus
from apps.master_data.models import Akun

from .models import ModalDisetor, ModalDisetorDebit, Pemilik


def _next_modal_disetor_journal_number() -> str:
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
    pemilik = Pemilik.objects.filter(nama__iexact=nama.strip()).first()
    if not pemilik:
        pemilik = Pemilik.objects.create(nama=nama.strip())
    return pemilik


def create_modal_disetor_batch(
    *,
    entitas_bisnis_id: int,
    tanggal,
    owners: list[dict[str, Any]],
    debit_lines: list[dict[str, Any]],
) -> list[ModalDisetor]:
    if not owners:
        raise ValueError('Minimal 1 pemilik wajib diisi.')
    if not debit_lines:
        raise ValueError('Minimal 1 baris akun debit wajib diisi.')

    parsed_owners: list[dict] = []
    total_modal = Decimal('0')
    for o in owners:
        try:
            pemilik_id = int(o['pemilik_id'])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f'pemilik_id tidak valid: {o.get("pemilik_id")}')
        try:
            jm = Decimal(str(o.get('jumlah_modal', 0)))
        except Exception:
            raise ValueError(f'Jumlah modal tidak valid untuk pemilik id={pemilik_id}.')
        if jm <= 0:
            raise ValueError(f'Jumlah modal harus lebih dari 0 (pemilik id={pemilik_id}).')

        pct_raw = o.get('persentase_kepemilikan')
        try:
            pct = Decimal(str(pct_raw)) if pct_raw not in (None, '', 0, '0') else None
        except Exception:
            pct = None

        parsed_owners.append({
            'pemilik_id': pemilik_id,
            'jumlah_modal': jm,
            'persentase_kepemilikan': pct,
            'keterangan': str(o.get('keterangan', '')).strip(),
        })
        total_modal += jm

    total_debit = Decimal('0')
    parsed_debits: list[dict] = []
    for d in debit_lines:
        try:
            akun_id = int(d['akun_id'])
            j = Decimal(str(d.get('jumlah', 0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'Baris debit tidak valid: {exc}')
        if j <= 0:
            raise ValueError('Setiap baris debit harus memiliki jumlah lebih dari 0.')
        parsed_debits.append({'akun_id': akun_id, 'jumlah': j})
        total_debit += j

    if abs(total_debit - total_modal) > Decimal('0.01'):
        raise ValueError(
            f'Total debit (Rp {total_debit:,.0f}) harus sama dengan '
            f'total jumlah modal pemilik (Rp {total_modal:,.0f}).'
        )

    pemilik_ids = [o['pemilik_id'] for o in parsed_owners]
    pemilik_map = {p.pk: p for p in Pemilik.objects.filter(pk__in=pemilik_ids)}
    for pid in pemilik_ids:
        if pid not in pemilik_map:
            raise ValueError(f'Pemilik id={pid} tidak ditemukan.')

    akun_ids = [d['akun_id'] for d in parsed_debits]
    akun_map = {a.pk: a for a in Akun.objects.filter(pk__in=akun_ids)}
    for aid in akun_ids:
        if aid not in akun_map:
            raise ValueError(f'Akun id={aid} tidak ditemukan.')

    modal_akun = Akun.objects.filter(kode_akun__startswith='3.1.1').first()
    if not modal_akun:
        raise ValueError('Akun Modal Disetor (3.1.1.xx) belum tersedia di Chart of Accounts.')

    with transaction.atomic():
        if len(parsed_owners) == 1:
            uraian = f'Modal Disetor \u2014 {pemilik_map[parsed_owners[0]["pemilik_id"]].nama}'
        else:
            names = ', '.join(pemilik_map[o['pemilik_id']].nama for o in parsed_owners)
            uraian = f'Modal Disetor \u2014 {names}'

        nomor = _next_modal_disetor_journal_number()
        header = JurnalHeader.objects.create(
            tanggal=tanggal,
            nomor_transaksi=nomor,
            uraian_transaksi=uraian,
            entitas_bisnis_id=entitas_bisnis_id,
            is_penyesuaian=False,
        )

        debit_details = [
            JurnalDetail(jurnal_header=header, akun=akun_map[d['akun_id']], debit=d['jumlah'], kredit=Decimal('0'))
            for d in parsed_debits
        ]
        debit_details.append(
            JurnalDetail(jurnal_header=header, akun=modal_akun, debit=Decimal('0'), kredit=total_modal)
        )
        JurnalDetail.objects.bulk_create(debit_details)

        records: list[ModalDisetor] = []
        for o in parsed_owners:
            record = ModalDisetor.objects.create(
                entitas_bisnis_id=entitas_bisnis_id,
                pemilik_id=o['pemilik_id'],
                jumlah_modal=o['jumlah_modal'],
                persentase_kepemilikan=o['persentase_kepemilikan'],
                tanggal_setor=tanggal,
                keterangan=o['keterangan'],
                jurnal_header=header,
            )
            ratio = o['jumlah_modal'] / total_modal
            owner_debit_lines = [
                ModalDisetorDebit(
                    modal_disetor=record,
                    akun=akun_map[d['akun_id']],
                    jumlah=(d['jumlah'] * ratio).quantize(Decimal('0.0001')),
                )
                for d in parsed_debits
            ]
            ModalDisetorDebit.objects.bulk_create(owner_debit_lines)
            records.append(record)

    return records


def create_modal_disetor(
    *,
    entitas_bisnis_id: int,
    pemilik_id: int,
    tanggal,
    jumlah_modal: Decimal,
    persentase_kepemilikan: Decimal | None = None,
    keterangan: str,
    debit_lines: list[dict[str, Any]],
) -> ModalDisetor:
    records = create_modal_disetor_batch(
        entitas_bisnis_id=entitas_bisnis_id,
        tanggal=tanggal,
        owners=[{
            'pemilik_id': pemilik_id,
            'jumlah_modal': jumlah_modal,
            'persentase_kepemilikan': persentase_kepemilikan,
            'keterangan': keterangan,
        }],
        debit_lines=debit_lines,
    )
    return records[0]


def get_group_siblings(record: ModalDisetor) -> list[ModalDisetor]:
    if not record.jurnal_header_id:
        return [record]
    return list(
        ModalDisetor.objects.filter(jurnal_header=record.jurnal_header)
        .select_related('pemilik', 'entitas_bisnis')
        .order_by('pemilik__nama')
    )


def delete_modal_disetor_group(record: ModalDisetor, request=None) -> None:
    with transaction.atomic():
        header = record.jurnal_header
        if header:
            siblings = list(ModalDisetor.objects.filter(jurnal_header=header))
            for sibling in siblings:
                sibling.delete()
            if not header.is_saldo_awal:
                log_jurnal_terhapus(header, 'ekuitas', request)
                header.details.all().delete()
                header.delete()
        else:
            record.delete()


def delete_modal_disetor(record: ModalDisetor, request=None) -> None:
    delete_modal_disetor_group(record, request=request)
