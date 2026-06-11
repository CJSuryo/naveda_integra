import json
from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BatchPenyisihanForm,
    PenyisihanRateConfigFormSet,
    PiutangAttachmentForm, PiutangDetailFormSet, PiutangHeaderForm,
    PiutangPenerimaanForm, PiutangPenyisihanForm, PiutangReklasifikasiForm, PiutangWriteOffForm,
)
from .models import (
    PenyisihanRateConfig,
    PiutangAttachment, PiutangHeader, PiutangPenerimaan, PiutangPenyisihan, PiutangReklasifikasi,
)
from .services import (
    _AGING_BUCKET_KEYS,
    _AGING_BUCKET_LABELS,
    compute_angsuran_schedule,
    compute_bagian_lancar,
    compute_batch_penyisihan,
    compute_penyisihan_for_piutang,
    create_batch_penyisihan_journal,
    create_manual_piutang, create_piutang_payment,
    create_penyisihan_journal,
    create_reklasifikasi_bagian_lancar,
    get_aging_schedule_report, get_aging_schedule_workbook,
    get_piutang_aging, get_piutang_dashboard_kpi,
    get_piutang_disclosure_report,
    reverse_piutang_payment, reverse_penyisihan_journal,
    update_penyisihan_individual,
    write_off_piutang,
)


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
            resolved = _resolve_eb_selection(sel)
            if resolved:
                lv1_ids.add(resolved['lv1_id'])
        if lv1_ids:
            qs = qs.filter(entitas_bisnis_id__in=lv1_ids)

    return render(request, 'piutang/list.html', {
        'piutangs': list(qs),
        'tanggal_dari': tanggal_dari, 'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter, 'search': search,
        'status_choices': PiutangHeader.STATUS_CHOICES,
        'eb_tree': _get_eb_tree(),
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
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None
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
                        user=request.user,
                    )
                    dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil dibuat.')
                    return redirect('piutang:detail', pk=piutang.pk)
                except ValueError as exc:
                    form.add_error(None, str(exc))
        return render(request, 'piutang/form.html', {
            'form': form, 'formset': formset, 'mode': 'create',
            'eb_options_json': json.dumps(_get_eb_dropdown_options()),
            'eb_selected': eb_selection,
        })
    form = PiutangHeaderForm()
    formset = PiutangDetailFormSet(prefix='details', queryset=PiutangHeader.objects.none())
    return render(request, 'piutang/form.html', {
        'form': form, 'formset': formset, 'mode': 'create',
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
    })


@login_required
def piutang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.master_data.models import Akun
    piutang = get_object_or_404(
        PiutangHeader.objects
        .select_related('entitas_bisnis', 'coa_piutang_account')
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

    angsuran_schedule = []
    if piutang.jenis_jangka_waktu == 'long_term' and piutang.jatuh_tempo:
        angsuran_schedule = compute_angsuran_schedule(piutang)

    penyisihan_preview = compute_penyisihan_for_piutang(piutang)
    penyisihan_form = PiutangPenyisihanForm(initial={'tanggal': timezone.now().date()})
    penyisihan_history = (
        PiutangPenyisihan.objects
        .filter(piutang_header=piutang)
        .select_related('jurnal_header', 'allowance_account', 'expense_account', 'created_by')
        .order_by('-tanggal')
    )

    return render(request, 'piutang/detail.html', {
        'piutang': piutang,
        'penerimaan_form': penerimaan_form,
        'attachment_form': attachment_form,
        'bagian_lancar': bagian_lancar,
        'akun_piutang_list': akun_piutang_list,
        'write_off_form': PiutangWriteOffForm(initial={'tanggal': timezone.now().date()}),
        'reklasifikasi_form': PiutangReklasifikasiForm(initial={'tanggal': timezone.now().date()}),
        'angsuran_schedule': angsuran_schedule,
        'penyisihan_preview': penyisihan_preview,
        'penyisihan_form': penyisihan_form,
        'penyisihan_history': penyisihan_history,
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
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None
        if form.is_valid() and formset.is_valid():
            instance = form.save()
            formset.save()
            instance.entitas_bisnis = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
            instance.save(update_fields=['entitas_bisnis'])
            dj_messages.success(request, 'Piutang berhasil diperbarui.')
            return redirect('piutang:detail', pk=pk)
        return render(request, 'piutang/form.html', {
            'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang,
            'eb_options_json': json.dumps(_get_eb_dropdown_options()),
            'eb_selected': eb_selection,
        })
    form = PiutangHeaderForm(instance=piutang)
    formset = PiutangDetailFormSet(prefix='details', instance=piutang)
    eb_selected = f'lv1:{piutang.entitas_bisnis_id}' if piutang.entitas_bisnis_id else ''
    return render(request, 'piutang/form.html', {
        'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang,
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': eb_selected,
    })


@login_required
def piutang_delete(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        nomor = piutang.nomor_piutang
        piutang.delete()
        dj_messages.success(request, f'Piutang {nomor} dihapus.')
        return redirect('piutang:list')
    return render(request, 'piutang/delete.html', {'piutang': piutang})


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
    batch_preview = None
    form = BatchPenyisihanForm(initial={'tanggal': timezone.now().date()})
    history = (
        PiutangPenyisihan.objects
        .filter(jenis='batch')
        .select_related('jurnal_header', 'allowance_account', 'expense_account', 'created_by')
        .order_by('-tanggal')[:20]
    )

    if request.method == 'POST':
        action = request.POST.get('action', '')
        form = BatchPenyisihanForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            if action == 'preview':
                batch_preview = compute_batch_penyisihan(cd['tanggal'], cd['allowance_account'])
            elif action == 'post':
                batch_data = compute_batch_penyisihan(cd['tanggal'], cd['allowance_account'])
                try:
                    create_batch_penyisihan_journal(
                        batch_data=batch_data,
                        allowance_account=cd['allowance_account'],
                        expense_account=cd['expense_account'],
                        tanggal=cd['tanggal'],
                        catatan=cd.get('catatan', ''),
                        periode_label=cd['tanggal'].strftime('%Y-%m'),
                        user=request.user,
                    )
                    dj_messages.success(request, f'Jurnal penyisihan batch berhasil dibuat. Delta: {batch_data["delta"]}')
                    return redirect('piutang:report_penyisihan')
                except ValueError as exc:
                    dj_messages.error(request, str(exc))
                    batch_preview = batch_data

    return render(request, 'piutang/report_penyisihan.html', {
        'form': form, 'batch_preview': batch_preview, 'history': history,
    })


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
def piutang_reklasifikasi_bagian_lancar(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangReklasifikasiForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                create_reklasifikasi_bagian_lancar(
                    piutang=piutang,
                    dari_akun=cd['dari_akun'],
                    ke_akun=cd['ke_akun'],
                    tanggal=cd['tanggal'],
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
