from decimal import Decimal

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    PiutangAttachmentForm, PiutangDetailFormSet, PiutangHeaderForm,
    PiutangPenerimaanForm, PiutangReklasifikasiForm, PiutangWriteOffForm,
)
from .models import PiutangAttachment, PiutangHeader, PiutangPenerimaan, PiutangReklasifikasi
from .services import (
    compute_angsuran_schedule, compute_bagian_lancar,
    create_manual_piutang, create_piutang_payment,
    get_piutang_aging, get_piutang_dashboard_kpi,
    reverse_piutang_payment, write_off_piutang,
)


@login_required
def piutang_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_piutang_dashboard_kpi()
    buckets = get_piutang_aging()
    due_soon = list(
        PiutangHeader.objects
        .filter(status__in=('open', 'partial'), jatuh_tempo__lte=timezone.now().date())
        .order_by('jatuh_tempo')[:20]
    )
    return render(request, 'piutang/dashboard.html', {
        'kpi': kpi, 'buckets': buckets, 'due_soon': due_soon,
    })


@login_required
def piutang_list(request: HttpRequest) -> HttpResponse:
    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()

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
    return render(request, 'piutang/list.html', {
        'piutangs': list(qs),
        'tanggal_dari': tanggal_dari, 'tanggal_sampai': tanggal_sampai,
        'status_filter': status_filter, 'search': search,
        'status_choices': PiutangHeader.STATUS_CHOICES,
    })


@login_required
def piutang_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST)
        formset = PiutangDetailFormSet(request.POST, prefix='details')
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
                    piutang = create_manual_piutang(
                        tanggal=cd['tanggal'], entitas_bisnis=None,
                        debitur=cd.get('debitur', ''), deskripsi=cd.get('deskripsi', ''),
                        coa_piutang_account=cd['coa_piutang_account'],
                        jatuh_tempo=cd.get('jatuh_tempo'),
                        details=details,
                        jenis_jangka_waktu=cd['jenis_jangka_waktu'],
                        requires_approval=cd.get('requires_approval', False),
                        jenis_bunga=cd.get('jenis_bunga', 'tanpa_bunga'),
                        bunga_persen=cd.get('bunga_persen') or Decimal('0'),
                        jumlah_angsuran=cd.get('jumlah_angsuran'),
                        periode_angsuran=cd.get('periode_angsuran', 'bulanan'),
                        user=request.user,
                    )
                    dj_messages.success(request, f'Piutang {piutang.nomor_piutang} berhasil dibuat.')
                    return redirect('piutang:detail', pk=piutang.pk)
                except ValueError as exc:
                    form.add_error(None, str(exc))
        return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'create'})
    form = PiutangHeaderForm()
    formset = PiutangDetailFormSet(prefix='details', queryset=PiutangHeader.objects.none())
    return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'create'})


@login_required
def piutang_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.master_data.models import Akun
    piutang = get_object_or_404(
        PiutangHeader.objects
        .select_related('entitas_bisnis', 'coa_piutang_account', 'approved_by')
        .prefetch_related(
            'details', 'penerimaan__payment_account', 'penerimaan__jurnal_header',
            'attachments', 'audit_logs__user', 'reklasifikasi_entries__jurnal',
        ),
        pk=pk,
    )
    penerimaan_form = PiutangPenerimaanForm(piutang_header=piutang, initial={'tanggal_terima': piutang.tanggal})
    attachment_form = PiutangAttachmentForm()
    angsuran_schedule = compute_angsuran_schedule(piutang) if piutang.jumlah_angsuran else []
    bagian_lancar = compute_bagian_lancar(piutang) if piutang.can_reklasifikasi else None
    akun_piutang_list = list(Akun.objects.filter(kategori_id='aset').order_by('kode_akun'))
    return render(request, 'piutang/detail.html', {
        'piutang': piutang,
        'penerimaan_form': penerimaan_form,
        'attachment_form': attachment_form,
        'angsuran_schedule': angsuran_schedule,
        'bagian_lancar': bagian_lancar,
        'akun_piutang_list': akun_piutang_list,
        'write_off_form': PiutangWriteOffForm(initial={'tanggal': timezone.now().date()}),
        'reklasifikasi_form': PiutangReklasifikasiForm(initial={'tanggal': timezone.now().date()}),
    })


@login_required
def piutang_update(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if piutang.status != 'draft':
        dj_messages.error(request, 'Hanya piutang berstatus Draft yang dapat diedit.')
        return redirect('piutang:detail', pk=pk)
    if request.method == 'POST':
        form = PiutangHeaderForm(request.POST, instance=piutang)
        formset = PiutangDetailFormSet(request.POST, prefix='details', instance=piutang)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            dj_messages.success(request, 'Piutang berhasil diperbarui.')
            return redirect('piutang:detail', pk=pk)
        return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang})
    form = PiutangHeaderForm(instance=piutang)
    formset = PiutangDetailFormSet(prefix='details', instance=piutang)
    return render(request, 'piutang/form.html', {'form': form, 'formset': formset, 'mode': 'edit', 'piutang': piutang})


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
def piutang_submit_approval(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        if piutang.status != 'draft' or not piutang.requires_approval:
            dj_messages.error(request, 'Tidak dapat diajukan.')
        else:
            piutang.approval_status = 'pending'
            piutang.save(update_fields=['approval_status'])
            dj_messages.success(request, 'Diajukan untuk persetujuan.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_approve(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        piutang.approval_status = 'approved'
        piutang.approved_by = request.user
        piutang.approved_at = timezone.now()
        piutang.status = 'open'
        piutang.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'status'])
        dj_messages.success(request, 'Piutang disetujui.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reject(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        piutang.approval_status = 'rejected'
        piutang.save(update_fields=['approval_status'])
        dj_messages.warning(request, 'Piutang ditolak.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_post(request: HttpRequest, pk: int) -> HttpResponse:
    piutang = get_object_or_404(PiutangHeader, pk=pk)
    if request.method == 'POST':
        form = PiutangReklasifikasiForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            from apps.jurnal.models import JurnalDetail, JurnalHeader
            nomor = f'TRX-PIU-RKL-{piutang.pk}'
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
            )
            dj_messages.success(request, 'Reklasifikasi berhasil dicatat.')
    return redirect('piutang:detail', pk=pk)


@login_required
def piutang_reklasifikasi_reverse(request: HttpRequest, pk: int, rkl_pk: int) -> HttpResponse:
    rkl = get_object_or_404(PiutangReklasifikasi, pk=rkl_pk, piutang_header_id=pk)
    if request.method == 'POST':
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
    return render(request, 'piutang/report_aging.html', {'buckets': buckets})


@login_required
def piutang_report_subjek(request: HttpRequest) -> HttpResponse:
    from django.db.models import Sum
    rows = (
        PiutangHeader.objects
        .filter(status__in=('open', 'partial', 'overdue'))
        .values('debitur', 'entitas_bisnis__nama')
        .annotate(total=Sum('jumlah_pokok'), terbayar=Sum('jumlah_terbayar'))
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
