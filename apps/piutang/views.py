import json
from decimal import Decimal

from naveda_integra.json_utils import safe_json

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit

from naveda_integra.ratelimit_utils import rate_from
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    PenyisihanRateConfigFormSet,
    PiutangAttachmentForm, PiutangDetailFormSet, PiutangHeaderForm,
    PiutangPenerimaanForm, PiutangPenyisihanForm, PiutangReklasifikasiForm, PiutangWriteOffForm,
    PvAccrualForm, PvAdjustmentForm,
    ECLStageUpdateForm, ECLGeneralApproachForm,
    PiutangModifikasiForm, PiutangPemulihanForm, PiutangFactoringForm,
)
from .models import (
    PenyisihanRateConfig,
    PiutangAttachment, PiutangHeader, PiutangPenerimaan, PiutangPenyisihan, PiutangReklasifikasi,
    PiutangECLStagingLog, PiutangModifikasi, PiutangPemulihanWriteOff, PiutangFactoring,
)
from .services import (
    _AGING_BUCKET_KEYS,
    _AGING_BUCKET_LABELS,
    compute_amortization_schedule_pv,
    compute_angsuran_schedule,
    compute_effective_dpd,
    compute_bagian_lancar,
    compute_batch_penyisihan,
    compute_penyisihan_for_piutang,
    compute_present_value,
    create_batch_penyisihan_journal,
    create_manual_piutang, create_piutang_payment,
    create_penyisihan_journal,
    create_pv_adjustment_journal,
    create_reklasifikasi_bagian_lancar,
    get_aging_schedule_report, get_aging_schedule_workbook,
    get_piutang_aging, get_piutang_dashboard_kpi,
    get_piutang_disclosure_report,
    reverse_piutang_payment, reverse_penyisihan_journal,
    update_penyisihan_individual,
    write_off_piutang,
    post_piutang, submit_for_approval, approve_piutang, reject_piutang,
    create_pv_accrual_journal, create_pv_accrual_reversal,
    _pv_carrying_value, _pv_last_amortization_date, _pv_effective_interest_days,
    get_standar_akuntansi, update_ecl_stage, assess_ecl_stage,
    create_penyisihan_ecl_general,
    process_piutang_modification, recover_written_off_piutang, create_factoring_derecognition,
)


def _piutang_deletion_preview(piutang) -> dict:
    """
    Collect every record that will be removed when this piutang is deleted.
    Returns a dict suitable for the confirmation template.
    """
    from apps.jurnal.models import JurnalHeader
    from .models import PiutangPenyisihan

    nom = piutang.nomor_piutang
    jurnal_map: dict[int, JurnalHeader] = {}

    def _add(j):
        if j:
            jurnal_map[j.pk] = j

    # 1. AR posting journal
    posting_journals = list(
        JurnalHeader.objects.filter(uraian_transaksi=f'Pengakuan Piutang {nom}')
    )
    for j in posting_journals:
        _add(j)

    # 2. Payment & payment-reversal journals
    penerimaan_entries = list(
        piutang.penerimaan.select_related('jurnal_header', 'payment_account').all()
    )
    for p in penerimaan_entries:
        _add(p.jurnal_header)

    reversal_payments = list(
        JurnalHeader.objects.filter(uraian_transaksi=f'Reversal Penerimaan {nom}')
    )
    for j in reversal_payments:
        _add(j)

    # 3. PV amortization / accrual / reversal-accrual journals
    from django.db.models import Q
    pv_journals = list(
        JurnalHeader.objects.filter(
            Q(uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom}') |
            Q(uraian_transaksi__startswith=f'Akrual PV Piutang {nom}') |
            Q(uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom}')
        )
    )
    for j in pv_journals:
        _add(j)

    # 4. Reklasifikasi journals + their reversals
    reklasifikasi_entries = list(
        piutang.reklasifikasi_entries.select_related('jurnal', 'dari_akun', 'ke_akun').all()
    )
    for rkl in reklasifikasi_entries:
        _add(rkl.jurnal)
        reversal = JurnalHeader.objects.filter(
            nomor_transaksi=f'TRX-PIU-RKLR-{rkl.pk}'
        ).first()
        _add(reversal)

    # 5. Write-off journal
    write_off = None
    try:
        write_off = piutang.write_off
        _add(write_off.jurnal if write_off.jurnal_id else None)
    except Exception:
        pass

    # 6. Penyisihan records + journals
    penyisihan_entries = list(
        PiutangPenyisihan.objects.filter(piutang_header=piutang)
        .select_related('jurnal_header').all()
    )
    penyisihan_reversal_journals = list(
        JurnalHeader.objects.filter(uraian_transaksi=f'Reversal Penyisihan {nom}')
    )
    for ps in penyisihan_entries:
        _add(ps.jurnal_header)
    for j in penyisihan_reversal_journals:
        _add(j)

    # 7. Lampiran
    lampiran = list(piutang.attachments.all())

    # Sorted journals for display
    journals_sorted = sorted(jurnal_map.values(), key=lambda j: (j.tanggal, j.nomor_transaksi))

    return {
        'posting_journals': posting_journals,
        'penerimaan_entries': penerimaan_entries,
        'reversal_payments': reversal_payments,
        'pv_journals': pv_journals,
        'reklasifikasi_entries': reklasifikasi_entries,
        'write_off': write_off,
        'penyisihan_entries': penyisihan_entries,
        'penyisihan_reversal_journals': penyisihan_reversal_journals,
        'lampiran': lampiran,
        'all_journals': journals_sorted,
        'jurnal_count': len(jurnal_map),
    }


def _pv_next_periode(piutang) -> int:
    """Returns the next unrecorded amortization period number for a piutang.

    Only counts periodic journals ('— Periode N') to avoid false matches with
    pre-payment EIR journals ('— {from_date} s.d. {to_date}').
    """
    if not piutang.is_pv_adjusted:
        return 1
    from apps.jurnal.models import JurnalHeader as _JH
    prefix = f'Amortisasi PV Piutang {piutang.nomor_piutang} — Periode'
    recorded = _JH.objects.filter(uraian_transaksi__startswith=prefix).count()
    return recorded + 1


def _annotate_carrying_awal(schedule: list) -> list:
    """Add carrying_awal to each amortization row: carrying_akhir - EIR + cash_flow."""
    for row in schedule:
        row['carrying_awal'] = row['carrying_value'] - row['bunga_efektif_gross'] + row['cash_flow']
    return schedule


def _pv_has_pending_accrual(piutang) -> bool:
    """True when there is at least one accrual journal not yet reversed."""
    if not piutang.is_pv_adjusted:
        return False
    from apps.jurnal.models import JurnalHeader as _JH
    nom = piutang.nomor_piutang
    n_acc = _JH.objects.filter(uraian_transaksi__startswith=f'Akrual PV Piutang {nom}').count()
    n_rev = _JH.objects.filter(uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom}').count()
    return n_acc > n_rev


@login_required
def piutang_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_piutang_dashboard_kpi()
    due_soon = list(
        PiutangHeader.objects
        .filter(status__in=('open', 'partial'), jatuh_tempo__lte=timezone.now().date())
        .order_by('jatuh_tempo')[:20]
    )
    return render(request, 'piutang/dashboard.html', {
        'kpi': kpi, 'due_soon': due_soon,
    })


@login_required
def piutang_list(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _get_eb_tree, _resolve_eb_selection

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    qs = PiutangHeader.objects.select_related('entitas_bisnis').order_by('-tanggal', '-created_at')
    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(
            Q(nomor_piutang__icontains=search) | Q(debitur__icontains=search) | Q(deskripsi__icontains=search)
        )
    if eb_filter_list:
        lv1_ids = set()
        for sel in eb_filter_list:
            resolved = _resolve_eb_selection(sel, request.user)
            if resolved:
                lv1_ids.add(resolved['lv1_id'])
        if lv1_ids:
            qs = qs.filter(entitas_bisnis_id__in=lv1_ids)

    return render(request, 'piutang/list.html', {
        'piutangs': list(qs),
        'tanggal_dari': tanggal_dari, 'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter, 'search': search,
        'status_choices': PiutangHeader.STATUS_CHOICES,
        'eb_tree': _get_eb_tree(request.user),
        'eb_filter_list': eb_filter_list,
    })


@login_required
def piutang_create(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    from apps.entitas_bisnis.models import EntitasBisnis

    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST)
        formset = PiutangDetailFormSet(request.POST, prefix='details')
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection, request.user) if eb_selection else None
        if form.is_valid() and formset.is_valid():
            details = [
                {'deskripsi': f.cleaned_data.get('deskripsi', ''),
                 'jumlah': f.cleaned_data['jumlah'],
                 'revenue_account': f.cleaned_data.get('revenue_account')}
                for f in formset
                if f.cleaned_data and not f.cleaned_data.get('DELETE', False)
            ]
            if not details:
                form.add_error(None, 'Minimal satu detail diperlukan.')
            else:
                try:
                    cd = form.cleaned_data
                    eb = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
                    piutang = create_manual_piutang(
                        tanggal=cd['tanggal'],
                        entitas_bisnis=eb,
                        debitur=cd.get('debitur', ''),
                        deskripsi=cd.get('deskripsi', ''),
                        coa_piutang_account=cd['coa_piutang_account'],
                        jatuh_tempo=cd.get('jatuh_tempo'),
                        details=details,
                        jenis_jangka_waktu=cd['jenis_jangka_waktu'],
                        jenis_bunga=cd.get('jenis_bunga', 'tanpa_bunga'),
                        suku_bunga=cd.get('suku_bunga') or Decimal('0'),
                        periode_angsuran=cd.get('periode_angsuran', 'bulanan'),
                        is_approval_required=cd.get('is_approval_required', False),
                        pv_discount_rate=cd.get('pv_discount_rate'),
                        interest_income_account=cd.get('interest_income_account'),
                        coa_piutang_lancar_account=cd.get('coa_piutang_lancar_account'),
                        standar_akuntansi=cd.get('standar_akuntansi', ''),
                        kategori_pengukuran=cd.get('kategori_pengukuran', 'amortised_cost'),
                        business_model=cd.get('business_model', ''),
                        sppi_test_passed=cd.get('sppi_test_passed'),
                        biaya_transaksi=cd.get('biaya_transaksi'),
                        biaya_transaksi_account=cd.get('biaya_transaksi_account'),
                        agunan_jenis=cd.get('agunan_jenis', ''),
                        agunan_nilai=cd.get('agunan_nilai'),
                        user=request.user,
                    )
                    dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil dibuat.')
                    return redirect('piutang:detail', pk=piutang.pk)
                except ValueError as exc:
                    form.add_error(None, str(exc))
        from apps.entitas_bisnis.models import EntitasBisnis as _EB
        _eb_standar_map = {
            f'lv1:{row["pk"]}': row['standar_akuntansi']
            for row in _EB.objects.filter(status_aktif=True).values('pk', 'standar_akuntansi')
        }
        return render(request, 'piutang/form.html', {
            'form': form, 'formset': formset, 'mode': 'create',
            'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
            'eb_selected': eb_selection,
            'eb_standar_map_json': safe_json(_eb_standar_map),
        })
    form = PiutangHeaderForm()
    formset = PiutangDetailFormSet(prefix='details', queryset=PiutangHeader.objects.none())
    from apps.entitas_bisnis.models import EntitasBisnis as _EB
    eb_standar_map = {
        f'lv1:{row["pk"]}': row['standar_akuntansi']
        for row in _EB.objects.filter(status_aktif=True).values('pk', 'standar_akuntansi')
    }
    return render(request, 'piutang/form.html', {
        'form': form, 'formset': formset, 'mode': 'create',
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
        'eb_standar_map_json': safe_json(eb_standar_map),
    })


def _collect_riwayat_jurnal(piutang, penyisihan_history) -> list:
    from apps.jurnal.models import JurnalHeader

    entries = []

    # AR posting journal
    for j in JurnalHeader.objects.filter(
        uraian_transaksi=f'Pengakuan Piutang {piutang.nomor_piutang}'
    ):
        entries.append({'jurnal': j, 'jenis': 'Pengakuan Piutang'})

    # Payment journals (prefetched via penerimaan__jurnal_header)
    for p in piutang.penerimaan.all():
        if p.jurnal_header_id:
            entries.append({'jurnal': p.jurnal_header, 'jenis': 'Penerimaan'})

    # Payment reversal journals (standalone — created after penerimaan is deleted)
    for j in JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Reversal Penerimaan {piutang.nomor_piutang}'
    ):
        entries.append({'jurnal': j, 'jenis': 'Reversal Penerimaan'})

    # Write-off journal
    try:
        wo = piutang.write_off
        if wo.jurnal_id:
            entries.append({'jurnal': wo.jurnal, 'jenis': 'Write-Off'})
    except Exception:
        pass

    # Reklasifikasi journals (prefetched) and their reversal counterparts
    rkl_pks = []
    for rkl in piutang.reklasifikasi_entries.all():
        if rkl.jurnal_id:
            entries.append({'jurnal': rkl.jurnal, 'jenis': 'Reklasifikasi'})
        rkl_pks.append(rkl.pk)
    if rkl_pks:
        for j in JurnalHeader.objects.filter(
            nomor_transaksi__in=[f'TRX-PIU-RKLR-{pk}' for pk in rkl_pks]
        ):
            entries.append({'jurnal': j, 'jenis': 'Reversal Reklasifikasi'})

    # Penyisihan journals (reuse already-fetched list)
    for ps in penyisihan_history:
        if ps.jurnal_header_id:
            jenis = 'Penyisihan Batch' if ps.jenis == 'batch' else 'Penyisihan'
            entries.append({'jurnal': ps.jurnal_header, 'jenis': jenis})

    # PV amortization journals
    for j in JurnalHeader.objects.filter(
        nomor_transaksi__startswith='TRX-PIU-PV-',
        uraian_transaksi__startswith=f'Amortisasi PV Piutang {piutang.nomor_piutang}',
    ):
        entries.append({'jurnal': j, 'jenis': 'Amortisasi PV'})

    entries.sort(key=lambda x: (x['jurnal'].tanggal, x['jurnal'].nomor_transaksi))
    return entries


@login_required
def piutang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.master_data.models import Akun
    piutang = get_object_or_404(
        PiutangHeader.objects
        .select_related(
            'entitas_bisnis', 'coa_piutang_account',
            'coa_piutang_lancar_account', 'interest_income_account',
            'approved_by',
        )
        .prefetch_related(
            'details', 'penerimaan__payment_account', 'penerimaan__jurnal_header',
            'attachments', 'audit_logs__user', 'reklasifikasi_entries__jurnal',
        ),
        pk=pk,
    )
    penerimaan_form = PiutangPenerimaanForm(piutang_header=piutang, initial={'tanggal_terima': piutang.tanggal})
    attachment_form = PiutangAttachmentForm()
    bagian_lancar = compute_bagian_lancar(piutang) if piutang.can_reklasifikasi else None
    akun_piutang_list = list(Akun.objects.filter(kategori_id='aset').order_by('kode_akun'))
    akun_all_list = list(Akun.objects.order_by('kode_akun'))

    angsuran_schedule = []
    angsuran_totals = {}
    sisa_total_bayar = piutang.sisa_piutang  # default: principal only (tanpa_bunga)
    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        angsuran_schedule = compute_angsuran_schedule(piutang)
        if angsuran_schedule:
            angsuran_totals = {
                'pokok':     sum(r['pokok']     for r in angsuran_schedule),
                'bunga':     sum(r['bunga']     for r in angsuran_schedule),
                'angsuran':  sum(r['angsuran']  for r in angsuran_schedule),
                'paid':      sum(r['paid']      for r in angsuran_schedule),
                'sisa_bayar':sum(r['sisa_bayar']for r in angsuran_schedule),
            }
            if piutang.jenis_bunga != 'tanpa_bunga':
                sisa_total_bayar = angsuran_totals['sisa_bayar']
    # DPD from earliest unpaid installment (not final maturity) for installment loans
    effective_dpd = compute_effective_dpd(piutang, schedule=angsuran_schedule or None)

    penyisihan_preview = compute_penyisihan_for_piutang(piutang)
    penyisihan_form = PiutangPenyisihanForm(initial={'tanggal': timezone.now().date()})

    _psh_qs = PiutangPenyisihan.objects.select_related(
        'jurnal_header', 'allowance_account', 'expense_account', 'created_by',
    )
    manual_penyisihan = list(
        _psh_qs.filter(piutang_header=piutang).order_by('-tanggal')
    )
    # Batch penyisihan entries that cover this piutang's EB + allowance account group
    batch_penyisihan = []
    if piutang.penyisihan_allowance_account_id:
        batch_penyisihan = list(
            _psh_qs.filter(
                jenis='batch',
                entitas_bisnis=piutang.entitas_bisnis,
                allowance_account_id=piutang.penyisihan_allowance_account_id,
            ).order_by('-tanggal')
        )
    penyisihan_history = sorted(
        manual_penyisihan + batch_penyisihan,
        key=lambda x: (x.tanggal, x.pk),
        reverse=True,
    )

    riwayat_jurnal = _collect_riwayat_jurnal(piutang, penyisihan_history)

    # PSAK 71 / SAK context
    standar_efektif = get_standar_akuntansi(piutang)
    ecl_staging_log = list(
        PiutangECLStagingLog.objects.filter(piutang_header=piutang)
        .select_related('created_by').order_by('-tanggal')
    )
    modifikasi_history = list(
        PiutangModifikasi.objects.filter(piutang_header=piutang)
        .select_related('gain_loss_account', 'created_by').order_by('-tanggal')
    )
    pemulihan_history = list(
        PiutangPemulihanWriteOff.objects.filter(piutang_header=piutang)
        .select_related('kas_account', 'recovery_income_account', 'created_by').order_by('-tanggal')
    )
    factoring_history = list(
        PiutangFactoring.objects.filter(piutang_header=piutang)
        .select_related('created_by').order_by('-tanggal')
    )
    today = timezone.now().date()
    ecl_stage_form = ECLStageUpdateForm(initial={'new_stage': piutang.stage_ecl or 1})
    ecl_general_form = ECLGeneralApproachForm(initial={
        'tanggal': today,
        'forward_looking_adj': '1.0000',
    })
    modifikasi_form = PiutangModifikasiForm(initial={'tanggal': today})
    pemulihan_form = PiutangPemulihanForm(initial={'tanggal': today})
    factoring_form = PiutangFactoringForm(initial={'tanggal': today})

    return render(request, 'piutang/detail.html', {
        'piutang': piutang,
        'penerimaan_form': penerimaan_form,
        'attachment_form': attachment_form,
        'bagian_lancar': bagian_lancar,
        'akun_piutang_list': akun_piutang_list,
        'akun_all_list': akun_all_list,
        'write_off_form': PiutangWriteOffForm(initial={'tanggal': today}),
        'reklasifikasi_form': PiutangReklasifikasiForm(initial={'tanggal': today}),
        'angsuran_schedule': angsuran_schedule,
        'angsuran_totals': angsuran_totals,
        'sisa_total_bayar': sisa_total_bayar,
        'penyisihan_preview': penyisihan_preview,
        'penyisihan_form': penyisihan_form,
        'penyisihan_history': penyisihan_history,
        'pv_form': PvAdjustmentForm(initial={
            'tanggal': today,
            'interest_income_account': piutang.interest_income_account_id,
        }),
        'pv_accrual_form': PvAccrualForm(initial={'tanggal': today}),
        'riwayat_jurnal': riwayat_jurnal,
        'pv_next_periode': _pv_next_periode(piutang),
        'pv_amort_schedule': _annotate_carrying_awal(compute_amortization_schedule_pv(piutang)) if piutang.is_pv_adjusted else [],
        'pv_carrying_value': _pv_carrying_value(piutang) if piutang.is_pv_adjusted else None,
        'pv_last_amort_date': _pv_last_amortization_date(piutang) if piutang.is_pv_adjusted else None,
        'pv_has_pending_accrual': _pv_has_pending_accrual(piutang),
        'today': today,
        'effective_dpd': effective_dpd,
        # PSAK/SAK
        'standar_efektif': standar_efektif,
        'ecl_staging_log': ecl_staging_log,
        'modifikasi_history': modifikasi_history,
        'pemulihan_history': pemulihan_history,
        'factoring_history': factoring_history,
        'ecl_stage_form': ecl_stage_form,
        'ecl_general_form': ecl_general_form,
        'modifikasi_form': modifikasi_form,
        'pemulihan_form': pemulihan_form,
        'factoring_form': factoring_form,
    })


@login_required
def piutang_update(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    from apps.entitas_bisnis.models import EntitasBisnis

    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if piutang.status != 'draft':
        dj_messages.error(request, 'Hanya piutang berstatus Draft yang dapat diedit.')
        return redirect('piutang:detail', pk=pk)
    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST, instance=piutang)
        formset = PiutangDetailFormSet(request.POST, prefix='details', instance=piutang)
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection, request.user) if eb_selection else None
        if form.is_valid() and formset.is_valid():
            instance = form.save()
            formset.save()
            instance.entitas_bisnis = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
            instance.save(update_fields=['entitas_bisnis'])
            dj_messages.success(request, 'Piutang berhasil diperbarui.')
            return redirect('piutang:detail', pk=pk)
        from apps.entitas_bisnis.models import EntitasBisnis as _EB
        eb_standar_map = {
            f'lv1:{row["pk"]}': row['standar_akuntansi']
            for row in _EB.objects.filter(status_aktif=True).values('pk', 'standar_akuntansi')
        }
        return render(request, 'piutang/form.html', {
            'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang,
            'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
            'eb_selected': eb_selection,
            'eb_standar_map_json': safe_json(eb_standar_map),
        })
    form = PiutangHeaderForm(instance=piutang)
    formset = PiutangDetailFormSet(prefix='details', instance=piutang)
    eb_selected = f'lv1:{piutang.entitas_bisnis_id}' if piutang.entitas_bisnis_id else ''
    from apps.entitas_bisnis.models import EntitasBisnis as _EB
    eb_standar_map = {
        f'lv1:{row["pk"]}': row['standar_akuntansi']
        for row in _EB.objects.filter(status_aktif=True).values('pk', 'standar_akuntansi')
    }
    return render(request, 'piutang/form.html', {
        'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang,
        'eb_options_json': safe_json(_get_eb_dropdown_options(request.user)),
        'eb_selected': eb_selected,
        'eb_standar_map_json': safe_json(eb_standar_map),
    })


@login_required
def piutang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    from django.db.models import Q
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        from apps.jurnal.models import JurnalHeader
        from .models import PiutangPenyisihan

        nom = piutang.nomor_piutang
        with transaction.atomic():
            journal_ids = set()

            # AR posting journal
            journal_ids.update(
                JurnalHeader.objects.filter(
                    uraian_transaksi=f'Pengakuan Piutang {nom}'
                ).values_list('pk', flat=True)
            )

            # Payment journals + payment reversal journals
            for penerimaan in piutang.penerimaan.all():
                if penerimaan.jurnal_header_id:
                    journal_ids.add(penerimaan.jurnal_header_id)
            journal_ids.update(
                JurnalHeader.objects.filter(
                    uraian_transaksi=f'Reversal Penerimaan {nom}'
                ).values_list('pk', flat=True)
            )

            # Write-off journal
            try:
                wo = piutang.write_off
                if wo.jurnal_id:
                    journal_ids.add(wo.jurnal_id)
            except Exception:
                pass

            # Reklasifikasi journals and their reversal counterparts
            for rkl in piutang.reklasifikasi_entries.all():
                if rkl.jurnal_id:
                    journal_ids.add(rkl.jurnal_id)
                reversal_pk = (
                    JurnalHeader.objects
                    .filter(nomor_transaksi=f'TRX-PIU-RKLR-{rkl.pk}')
                    .values_list('pk', flat=True)
                    .first()
                )
                if reversal_pk:
                    journal_ids.add(reversal_pk)

            # Penyisihan journals + penyisihan reversal journals
            for ps in PiutangPenyisihan.objects.filter(piutang_header=piutang):
                if ps.jurnal_header_id:
                    journal_ids.add(ps.jurnal_header_id)
            journal_ids.update(
                JurnalHeader.objects.filter(
                    uraian_transaksi=f'Reversal Penyisihan {nom}'
                ).values_list('pk', flat=True)
            )

            # PV amortization / accrual / reversal-accrual journals
            journal_ids.update(
                JurnalHeader.objects.filter(
                    Q(uraian_transaksi__startswith=f'Amortisasi PV Piutang {nom}') |
                    Q(uraian_transaksi__startswith=f'Akrual PV Piutang {nom}') |
                    Q(uraian_transaksi__startswith=f'Balik Akrual PV Piutang {nom}')
                ).values_list('pk', flat=True)
            )

            # Delete penyisihan records (piutang_header is SET_NULL so orphaned otherwise)
            PiutangPenyisihan.objects.filter(piutang_header=piutang).delete()

            nomor = piutang.nomor_piutang
            piutang.delete()

            if journal_ids:
                JurnalHeader.objects.filter(pk__in=journal_ids).delete()

        dj_messages.success(request, f'Piutang {nomor} dan seluruh jurnal terkait dihapus.')
        return redirect('piutang:list')

    preview = _piutang_deletion_preview(piutang)
    return render(request, 'piutang/delete.html', {'piutang': piutang, 'preview': preview})


@login_required
def piutang_terima(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangPenerimaanForm(request.POST, piutang_header=piutang)
        if form.is_valid():
            try:
                create_piutang_payment(piutang, form.cleaned_data, user=request.user)
                dj_messages.success(request, 'Penerimaan berhasil dicatat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_penerimaan_cancel(request: HttpRequest, pk: int, ppk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    penerimaan = get_object_or_404(PiutangPenerimaan, pk=ppk, piutang_header=piutang)
    if request.method == 'POST':
        reverse_piutang_payment(penerimaan, user=request.user)
        dj_messages.success(request, 'Penerimaan berhasil dibatalkan.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_write_off(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangWriteOffForm(request.POST)
        if form.is_valid():
            try:
                write_off_piutang(piutang, form.cleaned_data, user=request.user)
                dj_messages.success(request, f'Piutang {piutang.nomor_piutang} dihapusbukukan.')
                return redirect('piutang:detail', pk=pk)
            except ValueError as exc:
                dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_post(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangReklasifikasiForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            from apps.jurnal.models import JurnalDetail, JurnalHeader
            count = PiutangReklasifikasi.objects.filter(piutang_header=piutang).count() + 1
            nomor = f'TRX-PIU-RKL-{piutang.pk}-{count:04d}'
            jurnal = JurnalHeader.objects.create(
                tanggal=cd['tanggal'],
                nomor_transaksi=nomor,
                uraian_transaksi=f'Reklasifikasi Piutang {piutang.nomor_piutang}',
                entitas_bisnis=piutang.entitas_bisnis,
                is_penyesuaian=False,
            )
            JurnalDetail.objects.bulk_create([
                JurnalDetail(jurnal_header=jurnal, akun=cd['dari_akun'], debit=Decimal('0'), kredit=cd['jumlah']),
                JurnalDetail(jurnal_header=jurnal, akun=cd['ke_akun'], debit=cd['jumlah'], kredit=Decimal('0')),
            ])
            PiutangReklasifikasi.objects.create(
                piutang_header=piutang, tanggal=cd['tanggal'],
                dari_akun=cd['dari_akun'], ke_akun=cd['ke_akun'],
                jumlah=cd['jumlah'], keterangan=cd.get('keterangan', ''),
                jurnal=jurnal, created_by=request.user,
                periode_bulan=cd['tanggal'].month,
                periode_tahun=cd['tanggal'].year,
            )
            dj_messages.success(request, 'Reklasifikasi berhasil dicatat.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_delete(request: HttpRequest, pk: int, rkl_pk: int) -> HttpResponse:
    rkl = get_object_or_404(PiutangReklasifikasi, pk=rkl_pk, piutang_header_id=pk)
    if request.method == 'POST':
        jurnal = rkl.jurnal
        rkl.delete()
        if jurnal:
            jurnal.delete()
        dj_messages.success(request, 'Data reklasifikasi dan jurnal terkait berhasil dihapus.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_reverse(request: HttpRequest, pk: int, rkl_pk: int) -> HttpResponse:
    rkl = get_object_or_404(PiutangReklasifikasi, pk=rkl_pk, piutang_header_id=pk)
    if request.method == 'POST':
        if not rkl.jurnal:
            dj_messages.error(request, 'Tidak ada jurnal untuk dibalik.')
            return redirect('piutang:detail', pk=pk)
        from apps.jurnal.models import JurnalDetail, JurnalHeader
        orig = rkl.jurnal
        rev = JurnalHeader.objects.create(
            tanggal=timezone.now().date(),
            nomor_transaksi=f'TRX-PIU-RKLR-{rkl.pk}',
            uraian_transaksi=f'Reversal Reklasifikasi {rkl.piutang_header.nomor_piutang}',
            entitas_bisnis=rkl.piutang_header.entitas_bisnis,
            is_penyesuaian=True,
        )
        JurnalDetail.objects.bulk_create([
            JurnalDetail(jurnal_header=rev, akun=d.akun, debit=d.kredit, kredit=d.debit)
            for d in orig.details.all()
        ])
        dj_messages.success(request, 'Reklasifikasi dibalik.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_attachment_upload(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.piutang_header = piutang
            att.uploaded_by = request.user
            att.save()
            dj_messages.success(request, 'Lampiran berhasil diunggah.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_attachment_delete(request: HttpRequest, pk: int, apk: int) -> HttpResponse:
    att = get_object_or_404(PiutangAttachment, pk=apk, piutang_header_id=pk)
    if request.method == 'POST':
        att.delete()
        dj_messages.success(request, 'Lampiran dihapus.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_report_aging(request: HttpRequest) -> HttpResponse:
    buckets = get_piutang_aging()
    rates = {r.bucket_key: r.rate_percent for r in PenyisihanRateConfig.objects.all()}
    bucket_summary = []
    grand_total_outstanding = Decimal('0')
    grand_total_penyisihan = Decimal('0')
    for key in _AGING_BUCKET_KEYS:
        entries = buckets[key]
        total = sum(e['jumlah'] for e in entries)
        rate = rates.get(key, Decimal('0'))
        penyisihan = (Decimal(str(total)) * rate / 100).quantize(Decimal('0.01'))
        grand_total_outstanding += Decimal(str(total))
        grand_total_penyisihan += penyisihan
        bucket_summary.append({
            'key': key,
            'label': _AGING_BUCKET_LABELS[key],
            'entries': entries,
            'total': total,
            'rate': rate,
            'penyisihan': penyisihan,
        })
    return render(request, 'piutang/report_aging.html', {
        'bucket_summary': bucket_summary,
        'grand_total_outstanding': grand_total_outstanding,
        'grand_total_penyisihan': grand_total_penyisihan,
    })


@login_required
def piutang_report_subjek(request: HttpRequest) -> HttpResponse:
    from django.db.models import Count, Sum
    rows = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .values('debitur', 'entitas_bisnis__nama')
        .annotate(total=Sum('jumlah_pokok'), terbayar=Sum('jumlah_terbayar'), jumlah_invoice=Count('id'))
        .order_by('-total')
    )
    return render(request, 'piutang/report_subjek.html', {'rows': rows})


@login_required
def piutang_report_jatuh_tempo(request: HttpRequest) -> HttpResponse:
    from datetime import timedelta
    today = timezone.now().date()
    due_30 = list(PiutangHeader.objects.filter(
        status__in=('open', 'partial'), jatuh_tempo__range=(today, today + timedelta(days=30))
    ).order_by('jatuh_tempo'))
    return render(request, 'piutang/report_jatuh_tempo.html', {'due_30': due_30, 'today': today})


@login_required
def piutang_report_write_off(request: HttpRequest) -> HttpResponse:
    from .models import PiutangWriteOff
    write_offs = PiutangWriteOff.objects.select_related('piutang_header', 'created_by').order_by('-tanggal')
    return render(request, 'piutang/report_write_off.html', {'write_offs': write_offs})


@login_required
def piutang_penyisihan_create(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        if piutang.is_specifically_impaired:
            dj_messages.error(request, 'Piutang ini sudah disisihkan secara khusus.')
            return redirect('piutang:detail', pk=pk)
        if piutang.status not in ('open', 'partial', 'overdue'):
            dj_messages.error(request, 'Penyisihan hanya bisa dibuat untuk piutang aktif.')
            return redirect('piutang:detail', pk=pk)
        form = PiutangPenyisihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                create_penyisihan_journal(
                    piutang=piutang,
                    allowance_account=cd['allowance_account'],
                    expense_account=cd['expense_account'],
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Jurnal penyisihan berhasil dibuat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_penyisihan_cancel(request: HttpRequest, pk: int, ppk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    entry = get_object_or_404(PiutangPenyisihan, pk=ppk, piutang_header=piutang)
    if request.method == 'POST':
        try:
            reverse_penyisihan_journal(entry, user=request.user)
            dj_messages.success(request, 'Jurnal penyisihan berhasil dibatalkan.')
        except Exception as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_report_penyisihan(request: HttpRequest) -> HttpResponse:
    from apps.master_data.models import Akun
    from apps.master_data.utils import akun_sorted_queryset

    batch_preview = None
    tanggal_val = timezone.now().date()
    catatan_val = ''
    history = (
        PiutangPenyisihan.objects
        .filter(jenis='batch')
        .select_related('jurnal_header', 'allowance_account', 'expense_account', 'created_by', 'entitas_bisnis')
        .order_by('-tanggal')[:20]
    )

    # Entitas bisnis filter from GET param
    from apps.entitas_bisnis.models import EntitasBisnis
    eb_filter_pk = request.GET.get('eb', '')
    eb_filter_obj = None
    if eb_filter_pk:
        try:
            eb_filter_obj = EntitasBisnis.objects.get(pk=eb_filter_pk)
        except (EntitasBisnis.DoesNotExist, ValueError):
            eb_filter_pk = ''

    eligible_qs = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'), is_specifically_impaired=False)
        .select_related(
            'penyisihan_allowance_account', 'penyisihan_expense_account', 'entitas_bisnis',
        )
        .order_by('nomor_piutang')
    )
    if eb_filter_obj:
        eligible_qs = eligible_qs.filter(entitas_bisnis=eb_filter_obj)
    eligible_piutangs = eligible_qs

    # All distinct entitas bisnis that appear in eligible piutangs (for filter dropdown)
    eb_choices = (
        EntitasBisnis.objects
        .filter(piutang_headers__status__in=('open', 'partial', 'overdue'),
                piutang_headers__is_specifically_impaired=False)
        .distinct()
        .order_by('nama')
    )

    if request.method == 'POST':
        action = request.POST.get('action', '')
        tanggal_str = request.POST.get('tanggal', '')
        catatan_val = request.POST.get('catatan', '')
        try:
            from datetime import date as _date
            tanggal_val = _date.fromisoformat(tanggal_str)
        except (ValueError, TypeError):
            dj_messages.error(request, 'Tanggal tidak valid.')
        else:
            if action == 'preview':
                batch_preview = compute_batch_penyisihan(tanggal_val)
            elif action == 'post':
                batch_data = compute_batch_penyisihan(tanggal_val)
                try:
                    entries = create_batch_penyisihan_journal(
                        batch_data=batch_data,
                        tanggal=tanggal_val,
                        catatan=catatan_val,
                        periode_label=tanggal_val.strftime('%Y-%m'),
                        user=request.user,
                    )
                    n = len(entries)
                    dj_messages.success(
                        request,
                        f'{n} jurnal penyisihan batch berhasil dibuat. '
                        f'Total delta: {batch_data["total_delta"]:,.0f}',
                    )
                    return redirect('piutang:report_penyisihan')
                except ValueError as exc:
                    dj_messages.error(request, str(exc))
                    batch_preview = batch_data

    akun_aset_qs = list(
        akun_sorted_queryset({'kategori_id': 'aset'}).values('id', 'kode_akun', 'nama')
    )
    akun_beban_qs = list(
        akun_sorted_queryset({'kategori_id': 'beban'}).values('id', 'kode_akun', 'nama')
    )

    return render(request, 'piutang/report_penyisihan.html', {
        'tanggal_val': tanggal_val,
        'catatan_val': catatan_val,
        'batch_preview': batch_preview,
        'history': history,
        'eligible_piutangs': eligible_piutangs,
        'eb_choices': eb_choices,
        'eb_filter_pk': eb_filter_pk,
        'akun_aset_json': safe_json(akun_aset_qs),
        'akun_beban_json': safe_json(akun_beban_qs),
    })


@login_required
def piutang_penyisihan_set_accounts(request: HttpRequest, pk: int) -> JsonResponse:
    """AJAX: save penyisihan_allowance_account and penyisihan_expense_account per piutang."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    try:
        body = json.loads(request.body)
        allowance_id = body.get('allowance_account_id') or None
        expense_id = body.get('expense_account_id') or None
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)
    from apps.master_data.models import Akun
    update_fields = []
    if allowance_id is not None:
        try:
            piutang.penyisihan_allowance_account = Akun.objects.get(pk=allowance_id)
        except Akun.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Akun cadangan tidak ditemukan'}, status=400)
    else:
        piutang.penyisihan_allowance_account = None
    update_fields.append('penyisihan_allowance_account')
    if expense_id is not None:
        try:
            piutang.penyisihan_expense_account = Akun.objects.get(pk=expense_id)
        except Akun.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Akun beban tidak ditemukan'}, status=400)
    else:
        piutang.penyisihan_expense_account = None
    update_fields.append('penyisihan_expense_account')
    piutang.save(update_fields=update_fields)
    return JsonResponse({'ok': True})


@login_required
def piutang_batch_penyisihan_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a batch penyisihan entry and its associated journal."""
    from .models import PiutangPenyisihan
    from .services import reverse_batch_penyisihan_journal
    entry = get_object_or_404(PiutangPenyisihan, pk=pk, jenis='batch')
    if request.method == 'POST':
        try:
            reverse_batch_penyisihan_journal(entry, user=request.user)
            dj_messages.success(request, 'Jurnal penyisihan batch berhasil dihapus.')
        except Exception as exc:
            dj_messages.error(request, f'Gagal menghapus jurnal: {exc}')
        return redirect('piutang:report_penyisihan')
    return render(request, 'piutang/batch_penyisihan_delete_confirm.html', {'entry': entry})


@login_required
def piutang_settings_rates(request: HttpRequest) -> HttpResponse:
    qs = PenyisihanRateConfig.objects.all().order_by('urutan')
    if request.method == 'POST':
        formset = PenyisihanRateConfigFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            dj_messages.success(request, 'Rate penyisihan berhasil disimpan.')
            return redirect('piutang:settings_rates')
        dj_messages.error(request, 'Terdapat kesalahan pada form.')
    else:
        formset = PenyisihanRateConfigFormSet(queryset=qs)
    return render(request, 'piutang/settings_rates.html', {'formset': formset, 'rates': qs})


@login_required
def penyisihan_history(request: HttpRequest) -> HttpResponse:
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    jenis_filter = request.GET.get('jenis', '')

    qs = (
        PiutangPenyisihan.objects
        .select_related('piutang_header', 'allowance_account', 'expense_account', 'jurnal_header', 'created_by')
        .order_by('-tanggal', '-created_at')
    )
    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if jenis_filter:
        qs = qs.filter(jenis=jenis_filter)

    return render(request, 'piutang/penyisihan_history.html', {
        'entries': list(qs),
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'jenis_filter': jenis_filter,
    })


@login_required
def aging_schedule_report(request: HttpRequest) -> HttpResponse:
    from datetime import date as date_cls
    as_of_str = request.GET.get('as_of', '')
    try:
        as_of_date = date_cls.fromisoformat(as_of_str) if as_of_str else None
    except ValueError:
        as_of_date = None
    report = get_aging_schedule_report(as_of_date)
    return render(request, 'piutang/aging_schedule_report.html', {
        'report': report,
        'bucket_keys': _AGING_BUCKET_KEYS,
        'bucket_labels': _AGING_BUCKET_LABELS,
        'as_of_str': as_of_str,
        'section_info': [('short_term', 'Jangka Pendek'), ('long_term', 'Jangka Panjang')],
    })


@login_required
@ratelimit(key='user', rate=rate_from('export'), method='GET', block=True)
def aging_schedule_export(request: HttpRequest) -> HttpResponse:
    from datetime import date as date_cls
    from io import BytesIO
    as_of_str = request.GET.get('as_of', '')
    try:
        as_of_date = date_cls.fromisoformat(as_of_str) if as_of_str else None
    except ValueError:
        as_of_date = None
    report = get_aging_schedule_report(as_of_date)
    wb = get_aging_schedule_workbook(report)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f'aging_schedule_{report["as_of_date"].strftime("%Y%m%d")}.xlsx'
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response


@login_required
def piutang_set_akun_lancar(request: HttpRequest, pk: int) -> HttpResponse:
    """Update coa_piutang_lancar_account on any active piutang."""
    from apps.master_data.models import Akun
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if piutang.status in ('cancelled', 'written_off'):
        dj_messages.error(request, 'Piutang ini sudah dibatalkan/dihapusbukukan.')
        return redirect('piutang:detail', pk=pk)
    if request.method == 'POST':
        lancar_id = request.POST.get('coa_piutang_lancar_account') or None
        try:
            piutang.coa_piutang_lancar_account = Akun.objects.get(pk=lancar_id) if lancar_id else None
            piutang.save(update_fields=['coa_piutang_lancar_account'])
            dj_messages.success(request, 'Akun bagian lancar berhasil disimpan.')
        except Akun.DoesNotExist:
            dj_messages.error(request, 'Akun tidak ditemukan.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_bagian_lancar(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        from datetime import date as date_cls
        tanggal_str = request.POST.get('tanggal', '')
        try:
            tanggal = date_cls.fromisoformat(tanggal_str)
        except ValueError:
            dj_messages.error(request, 'Tanggal tidak valid.')
            return redirect('piutang:detail', pk=pk)

        dari_akun = piutang.coa_piutang_account
        ke_akun = piutang.coa_piutang_lancar_account

        if not ke_akun:
            dj_messages.error(
                request,
                'Akun Piutang Bagian Lancar belum diset pada piutang ini. '
                'Edit piutang dan isi kolom tersebut terlebih dahulu.',
            )
            return redirect('piutang:detail', pk=pk)
        try:
            create_reklasifikasi_bagian_lancar(
                piutang=piutang,
                dari_akun=dari_akun,
                ke_akun=ke_akun,
                tanggal=tanggal,
                user=request.user,
            )
            dj_messages.success(request, 'Reklasifikasi bagian lancar berhasil dicatat.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_penyisihan_update(request: HttpRequest, pk: int, ppk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    entry = get_object_or_404(PiutangPenyisihan, pk=ppk, piutang_header=piutang, jenis='manual')
    if request.method == 'POST':
        form = PiutangPenyisihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                update_penyisihan_individual(
                    existing_entry=entry,
                    allowance_account=cd['allowance_account'],
                    expense_account=cd['expense_account'],
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Penyisihan berhasil diperbarui.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_disclosure_report(request: HttpRequest) -> HttpResponse:
    from datetime import date as date_cls
    as_of_str = request.GET.get('as_of', '')
    try:
        as_of_date = date_cls.fromisoformat(as_of_str) if as_of_str else None
    except ValueError:
        as_of_date = None
    report = get_piutang_disclosure_report(as_of_date)
    return render(request, 'piutang/disclosure_report.html', {
        'report': report,
        'as_of_str': as_of_str,
    })


@login_required
def piutang_pv_accrual(request: HttpRequest, pk: int) -> HttpResponse:
    """Create period-end accrual journal for effective interest not yet amortised."""
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PvAccrualForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                create_pv_accrual_journal(
                    piutang=piutang,
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Jurnal akrual bunga efektif berhasil dibuat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_pv_accrual_reversal(request: HttpRequest, pk: int) -> HttpResponse:
    """Reverse the last un-reversed period-end accrual journal."""
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        tanggal_str = request.POST.get('tanggal', '')
        try:
            from datetime import date as date_cls
            tanggal = date_cls.fromisoformat(tanggal_str) if tanggal_str else timezone.now().date()
            create_pv_accrual_reversal(
                piutang=piutang,
                tanggal=tanggal,
                user=request.user,
            )
            dj_messages.success(request, 'Jurnal akrual berhasil dibalik.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_pv_adjustment(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PvAdjustmentForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            income_account = cd.get('interest_income_account') or piutang.interest_income_account
            try:
                create_pv_adjustment_journal(
                    piutang=piutang,
                    interest_income_account=income_account,
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Jurnal amortisasi PV berhasil dibuat.')
            except ValueError as exc:
                dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_post(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        try:
            post_piutang(piutang, user=request.user)
            dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil diposting.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_submit_approval(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        try:
            submit_for_approval(piutang, user=request.user)
            dj_messages.success(request, f'Piutang {piutang.nomor_piutang} disubmit untuk persetujuan.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_approve(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        try:
            approve_piutang(piutang, user=request.user)
            dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil disetujui.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reject(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        alasan = request.POST.get('alasan', '')
        try:
            reject_piutang(piutang, user=request.user, alasan=alasan)
            dj_messages.success(request, f'Piutang {piutang.nomor_piutang} ditolak.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_ecl_stage_update(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = ECLStageUpdateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                update_ecl_stage(
                    piutang=piutang,
                    new_stage=int(cd['new_stage']),
                    alasan=cd['alasan'],
                    is_auto=False,
                    user=request.user,
                )
                dj_messages.success(request, f'ECL Stage diperbarui ke Stage {cd["new_stage"]}.')
            except (ValueError, Exception) as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_ecl_general(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = ECLGeneralApproachForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                from decimal import Decimal as D
                ecl_result = create_penyisihan_ecl_general(
                    piutang=piutang,
                    pd_rate=cd['pd_rate'],
                    lgd_rate=cd['lgd_rate'],
                    forward_looking_adj=cd.get('forward_looking_adj') or D('1'),
                    allowance_account=cd['allowance_account'],
                    expense_account=cd['expense_account'],
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(
                    request,
                    f'Jurnal penyisihan ECL (General Approach) berhasil dibuat. '
                    f'ECL: Rp {ecl_result:,.0f}',
                )
            except (ValueError, Exception) as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_modifikasi(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangModifikasiForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                import json as _json
                new_cashflows = _json.loads(cd['new_cashflows_json'])
                process_piutang_modification(
                    piutang=piutang,
                    new_cashflows=new_cashflows,
                    gain_loss_account=cd['gain_loss_account'],
                    tanggal=cd['tanggal'],
                    deskripsi_perubahan=cd['deskripsi_perubahan'],
                    user=request.user,
                )
                dj_messages.success(request, 'Modifikasi piutang berhasil dicatat.')
            except (_json.JSONDecodeError,):
                dj_messages.error(request, 'Format JSON arus kas baru tidak valid.')
            except (ValueError, Exception) as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_pemulihan(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangPemulihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                recover_written_off_piutang(
                    piutang=piutang,
                    jumlah=cd['jumlah'],
                    kas_account=cd['kas_account'],
                    recovery_income_account=cd['recovery_income_account'],
                    tanggal=cd['tanggal'],
                    catatan=cd.get('catatan', ''),
                    user=request.user,
                )
                dj_messages.success(request, 'Pemulihan piutang berhasil dicatat.')
            except (ValueError, Exception) as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_factoring(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangFactoringForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                create_factoring_derecognition(
                    piutang=piutang,
                    nilai_transfer=cd['nilai_transfer'],
                    hasil_analisis=cd['hasil_analisis'],
                    continuing_involvement_amount=cd.get('continuing_involvement_amount'),
                    pihak_penerima=cd['pihak_penerima'],
                    analisis_detail=cd.get('analisis_detail', ''),
                    gain_loss_account=cd.get('gain_loss_account'),
                    tanggal=cd['tanggal'],
                    user=request.user,
                )
                dj_messages.success(request, 'Factoring/derecognition berhasil dicatat.')
            except (ValueError, Exception) as exc:
                dj_messages.error(request, str(exc))
        else:
            dj_messages.error(request, 'Form tidak valid.')
    return redirect('piutang:detail', pk=pk)
