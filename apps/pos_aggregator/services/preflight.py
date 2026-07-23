"""Pre-flight checks — the gate that makes going live safe for anyone.

The point is to move the judgement of "is this ready?" from the operator to the
system. Every check answers a question that, if wrong, produces a failure that
is confusing and expensive at 12:00 on a Saturday:

* Can we authenticate at all?
* Is the branch actually linked to an outlet?
* Would the menu publish cleanly?
* Is tax configured, so revenue is not silently wrong?
* Can the accounting entries be produced?

Each failure carries a remedy written for the person reading it, not for a
developer.
"""
from __future__ import annotations

import logging

from django.conf import settings

from ..dto import CheckResult
from ..models import AggregatorStoreLink

logger = logging.getLogger(__name__)


def run_preflight(credential) -> list[CheckResult]:
    """Run every check for a merchant + aggregator. Order is presentation order."""
    checks = [
        _check_public_url(),
        _check_auth(credential),
        _check_encryption(),
    ]
    links = list(
        AggregatorStoreLink.objects
        .filter(credential=credential)
        .select_related('store_config__entitas_bisnis_lv3__parent_lv2')
    )
    checks.append(_check_store_links(links))
    checks.append(_check_tax(credential))
    checks.extend(_check_menu(link) for link in links if link.external_store_id)
    checks.extend(_check_accounting(link) for link in links)
    return checks


def _check_public_url() -> CheckResult:
    base = getattr(settings, 'AGGREGATOR_PUBLIC_BASE_URL', '')
    if not base:
        return CheckResult(
            code='public_url', label='Alamat publik', passed=False,
            detail='AGGREGATOR_PUBLIC_BASE_URL belum diisi.',
            remedy=(
                'Aggregator perlu alamat HTTPS untuk mengirim pesanan. Minta '
                'tim teknis mengisi AGGREGATOR_PUBLIC_BASE_URL.'
            ),
        )
    if not base.startswith('https://'):
        return CheckResult(
            code='public_url', label='Alamat publik', passed=False,
            detail=f'Alamat saat ini: {base}',
            remedy='Alamat harus HTTPS. Aggregator menolak mengirim ke HTTP.',
        )
    return CheckResult(
        code='public_url', label='Alamat publik', passed=True, detail=base
    )


def _check_encryption() -> CheckResult:
    from ..crypto import check_encryption_config
    warnings = check_encryption_config()
    if warnings:
        return CheckResult(
            code='encryption', label='Keamanan kredensial', passed=False,
            detail=warnings[0],
            remedy=(
                'Minta tim teknis mengisi AGGREGATOR_ENCRYPTION_KEY sebelum '
                'digunakan di produksi.'
            ),
        )
    return CheckResult(
        code='encryption', label='Keamanan kredensial', passed=True,
        detail='Kredensial dienkripsi dengan kunci khusus.',
    )


def _check_auth(credential) -> CheckResult:
    from ..adapters import get_adapter
    try:
        ok, detail = get_adapter(credential).ping()
    except Exception as exc:
        ok, detail = False, str(exc)
    return CheckResult(
        code='auth', label='Autentikasi', passed=ok, detail=detail,
        remedy='' if ok else (
            'Jalankan ulang "Hubungkan Akun". Jika tetap gagal, kredensial '
            'mungkin dicabut oleh aggregator — hubungi tim teknis.'
        ),
    )


def _check_store_links(links) -> CheckResult:
    linked = [link for link in links if link.external_store_id]
    if not linked:
        return CheckResult(
            code='store_link', label='Cabang terhubung', passed=False,
            detail='Belum ada cabang yang terhubung ke outlet aggregator.',
            remedy='Selesaikan langkah "Hubungkan Cabang" terlebih dahulu.',
        )
    names = ', '.join(link.store_config.entitas_bisnis_lv3.nama for link in linked)
    return CheckResult(
        code='store_link', label='Cabang terhubung', passed=True,
        detail=f'{len(linked)} cabang: {names}',
    )


def _check_tax(credential) -> CheckResult:
    tax = credential.effective_tax_pct()
    if tax is None:
        return CheckResult(
            code='tax', label='Pajak channel', passed=False,
            detail='Persentase pajak belum diisi.',
            remedy=(
                'Isi persentase pajak untuk channel ini. Salah isi membuat '
                'pajak dan pendapatan setiap pesanan salah — tanyakan bagian '
                'keuangan bila ragu.'
            ),
        )
    return CheckResult(
        code='tax', label='Pajak channel', passed=True, detail=f'{tax}%'
    )


def _check_menu(link) -> CheckResult:
    from .menu import build_menu, validate_menu
    branch = link.store_config.entitas_bisnis_lv3.nama
    try:
        problems = validate_menu(build_menu(link))
    except Exception as exc:
        return CheckResult(
            code=f'menu_{link.pk}', label=f'Menu — {branch}', passed=False,
            detail=str(exc), remedy='Periksa katalog cabang ini.',
        )
    if problems:
        return CheckResult(
            code=f'menu_{link.pk}', label=f'Menu — {branch}', passed=False,
            detail='; '.join(problems[:5]),
            remedy='Perbaiki item yang disebutkan di menu katalog, lalu jalankan ulang.',
        )
    return CheckResult(
        code=f'menu_{link.pk}', label=f'Menu — {branch}', passed=True,
        detail='Menu siap dipublikasikan.',
    )


def _check_accounting(link) -> CheckResult:
    """A sale that cannot be journalled is a sale that will be lost."""
    from pos_config.utils import resolve_pos_config
    branch = link.store_config.entitas_bisnis_lv3.nama
    cfg = resolve_pos_config(link.store_config.entitas_bisnis_lv3)
    missing = [
        label for label, value in (
            ('Sub-Transaction Type', cfg['sub_transaction_type_id']),
            ('Revenue Account', cfg['revenue_account_id']),
            ('HPP Account', cfg['offset_coa_account_id']),
        ) if not value
    ]
    if missing:
        return CheckResult(
            code=f'accounting_{link.pk}', label=f'Akuntansi — {branch}', passed=False,
            detail=f'Belum diisi: {", ".join(missing)}',
            remedy=(
                'Lengkapi Konfigurasi POS untuk cabang ini. Tanpa ini pesanan '
                'masuk tetapi tidak bisa dibukukan.'
            ),
        )
    return CheckResult(
        code=f'accounting_{link.pk}', label=f'Akuntansi — {branch}', passed=True,
        detail='Akun penjualan lengkap.',
    )


def as_dicts(results: list[CheckResult]) -> list[dict]:
    return [
        {
            'code': r.code, 'label': r.label, 'passed': r.passed,
            'detail': r.detail, 'remedy': r.remedy,
        }
        for r in results
    ]
