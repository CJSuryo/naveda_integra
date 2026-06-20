import datetime
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages as dj_messages
from django.views.decorators.http import require_POST
from .models import (
    PendapatanHeader, PendapatanEventLog, RecurringTemplate,
    KewajibabPelaksanaan, JadwalPengakuan, EntriPengakuan, AsetKontrak,
)
from .services import (
    confirm_pendapatan, create_pendapatan_header, void_pendapatan,
    get_pendapatan_dashboard_kpi, generate_from_recurring,
    recognize_entry, konversi_aset_kontrak_ke_piutang,
    recognize_percentage_completion,
)
from .forms import PendapatanHeaderForm, PendapatanItemForm, KewajibabPelaksanaanForm, RecurringTemplateForm, KPTaxLineForm


@login_required
def stt_defaults(request: HttpRequest) -> JsonResponse:
    from apps.purchase.models import SubTransactionType
    stt_id = request.GET.get('stt_id')
    if not stt_id:
        return JsonResponse({'error': 'stt_id required'}, status=400)
    try:
        stt = SubTransactionType.objects.select_related(
            'default_offset_account'
        ).get(pk=stt_id, module='pendapatan')
    except SubTransactionType.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({
        'revenue_account_id': stt.default_offset_account_id,
        'revenue_account_nama': str(stt.default_offset_account) if stt.default_offset_account else '',
    })


@login_required
def pendapatan_dashboard(request: HttpRequest) -> HttpResponse:
    kpi = get_pendapatan_dashboard_kpi()
    return render(request, 'pendapatan/dashboard.html', {'kpi': kpi})


@login_required
def pendapatan_list(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q
    qs = PendapatanHeader.objects.order_by('-tanggal', '-created_at')
    status_filter = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(transaction_id__icontains=search) | Q(deskripsi__icontains=search))
    return render(request, 'pendapatan/list.html', {
        'pendapatans': list(qs),
        'status_filter': status_filter,
        'search': search,
        'status_choices': PendapatanHeader.STATUS_CHOICES,
    })


def _parse_tax_lines_from_post(post, item_idx: int) -> list:
    """Parse tax line POST fields for item at position item_idx."""
    from decimal import Decimal, InvalidOperation
    from apps.master_data.models import Akun

    tax_count = int(post.get(f'item_{item_idx}_tax_count', '0') or '0')
    tax_lines = []
    for j in range(tax_count):
        tax_type = post.get(f'item_{item_idx}_tax_{j}_tax_type', '').strip()
        if not tax_type:
            continue
        tax_account_raw = post.get(f'item_{item_idx}_tax_{j}_tax_account', '').strip()
        tax_payment_account_raw = post.get(f'item_{item_idx}_tax_{j}_tax_payment_account', '').strip()
        if not tax_account_raw or not tax_payment_account_raw:
            continue
        try:
            tax_account = Akun.objects.get(pk=int(tax_account_raw))
            tax_payment_account = Akun.objects.get(pk=int(tax_payment_account_raw))
        except (Akun.DoesNotExist, ValueError):
            continue
        tax_raw = post.get(f'item_{item_idx}_tax_{j}_tax', '').strip()
        try:
            tax = Decimal(tax_raw) if tax_raw else None
        except InvalidOperation:
            tax = None
        tax_lines.append({
            'tax_type': tax_type,
            'tax': tax,
            'tax_account': tax_account,
            'tax_payment_account': tax_payment_account,
        })
    return tax_lines


@login_required
def pendapatan_create(request: HttpRequest) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    from apps.entitas_bisnis.models import EntitasBisnis

    if request.method == 'POST':
        form = PendapatanHeaderForm(request.POST)
        item_count = max(int(request.POST.get('item_count', '1')), 1)
        item_forms = [KewajibabPelaksanaanForm(request.POST, prefix=f'item_{i}') for i in range(item_count)]
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None

        if form.is_valid() and all(f.is_valid() for f in item_forms):
            cd = form.cleaned_data
            items = []
            for i, f in enumerate(item_forms):
                item_data = f.cleaned_data.copy()
                item_data['tax_lines'] = _parse_tax_lines_from_post(request.POST, i)
                items.append(item_data)
            try:
                eb = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
                pay_acct = items[0].get('payment_account')
                header = create_pendapatan_header(
                    tanggal=cd['tanggal'],
                    deskripsi=cd.get('deskripsi', ''),
                    payment_type=cd['payment_type'],
                    entitas_bisnis=eb,
                    payment_account=pay_acct,
                    items=items,
                    user=request.user,
                )
                dj_messages.success(request, f'Pendapatan {header.transaction_id} berhasil dibuat.')
                return redirect('pendapatan:detail', pk=header.pk)
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        form = PendapatanHeaderForm()
        item_forms = [KewajibabPelaksanaanForm(prefix='item_0')]

    return render(request, 'pendapatan/form.html', {
        'form': form,
        'item_forms': item_forms,
        'mode': 'create',
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'tax_lines_initial_json': '{}',
    })


@login_required
def pendapatan_edit(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.purchase.views import _get_eb_dropdown_options, _resolve_eb_selection
    from apps.entitas_bisnis.models import EntitasBisnis
    from django.db import transaction

    header = get_object_or_404(PendapatanHeader, pk=pk)
    if header.status != 'draft':
        dj_messages.error(request, 'Hanya pendapatan berstatus draft yang dapat diedit.')
        return redirect('pendapatan:detail', pk=pk)

    eb_group = header.entitas_groups.select_related('entitas_bisnis').prefetch_related('items').first()
    existing_items = list(eb_group.items.all()) if eb_group else []
    tax_lines_initial: dict = {}

    if request.method == 'POST':
        form = PendapatanHeaderForm(request.POST, instance=header)
        item_count = max(int(request.POST.get('item_count', '1')), 1)
        item_forms = [KewajibabPelaksanaanForm(request.POST, prefix=f'item_{i}') for i in range(item_count)]
        eb_selection = request.POST.get('eb_selection', '')
        resolved_eb = _resolve_eb_selection(eb_selection) if eb_selection else None

        if form.is_valid() and all(f.is_valid() for f in item_forms):
            try:
                with transaction.atomic():
                    form.save()
                    eb = EntitasBisnis.objects.get(pk=resolved_eb['lv1_id']) if resolved_eb else None
                    items_data = [f.cleaned_data for f in item_forms]
                    for i, item in enumerate(items_data):
                        item['tax_lines'] = _parse_tax_lines_from_post(request.POST, i)
                    pay_acct = items_data[0].get('payment_account')

                    if eb_group:
                        eb_group.entitas_bisnis = eb
                        eb_group.payment_account = pay_acct
                        eb_group.save(update_fields=['entitas_bisnis_id', 'payment_account_id'])
                        eb_group.items.all().delete()
                    else:
                        from .models import PendapatanEntitasBisnis
                        eb_group_new = PendapatanEntitasBisnis.objects.create(
                            pendapatan_header=header,
                            entitas_bisnis=eb,
                            payment_account=pay_acct,
                        )
                        eb_group = eb_group_new

                    from .models import KewajibabPelaksanaan as _KP, KPTaxLine as _TL

                    for item in items_data:
                        kp = _KP.objects.create(
                            pendapatan_eb=eb_group,
                            deskripsi_item=item['deskripsi_item'],
                            kategori=item['kategori'],
                            sub_transaction_type=item['sub_transaction_type'],
                            nilai_kontrak=item.get('nilai_kontrak') or item.get('jumlah_bruto'),
                            revenue_account=item['revenue_account'],
                            payment_account=item.get('payment_account'),
                            recognition_type=item.get('recognition_type', 'point_in_time'),
                            ot_tipe_aliran=item.get('ot_tipe_aliran', ''),
                            ot_progress_method=item.get('ot_progress_method', ''),
                            ot_tanggal_mulai=item.get('ot_tanggal_mulai'),
                            ot_tanggal_selesai=item.get('ot_tanggal_selesai'),
                            ot_liabilitas_kontrak_acct=item.get('ot_liabilitas_kontrak_acct'),
                            ot_aset_kontrak_acct=item.get('ot_aset_kontrak_acct'),
                            ot_biaya_estimasi_total=item.get('ot_biaya_estimasi_total'),
                        )
                        for tl in item.get('tax_lines', []):
                            _TL.objects.create(
                                kp=kp,
                                tax_type=tl['tax_type'],
                                tax=tl.get('tax'),
                                tax_account=tl['tax_account'],
                                tax_payment_account=tl['tax_payment_account'],
                            )

                dj_messages.success(request, f'Pendapatan {header.transaction_id} berhasil diperbarui.')
                return redirect('pendapatan:detail', pk=header.pk)
            except (ValueError, Exception) as exc:
                form.add_error(None, str(exc))
    else:
        form = PendapatanHeaderForm(instance=header)
        item_forms = [
            KewajibabPelaksanaanForm(prefix=f'item_{i}', initial={
                'deskripsi_item': item.deskripsi_item,
                'kategori': item.kategori,
                'sub_transaction_type': item.sub_transaction_type_id,
                'nilai_kontrak': item.nilai_kontrak,
                'revenue_account': item.revenue_account_id,
                'payment_account': item.payment_account_id,
                'recognition_type': item.recognition_type,
                'ot_tipe_aliran': item.ot_tipe_aliran,
                'ot_progress_method': item.ot_progress_method,
                'ot_tanggal_mulai': item.ot_tanggal_mulai,
                'ot_tanggal_selesai': item.ot_tanggal_selesai,
                'ot_liabilitas_kontrak_acct': item.ot_liabilitas_kontrak_acct_id,
                'ot_aset_kontrak_acct': item.ot_aset_kontrak_acct_id,
                'ot_biaya_estimasi_total': item.ot_biaya_estimasi_total,
            })
            for i, item in enumerate(existing_items)
        ] or [KewajibabPelaksanaanForm(prefix='item_0')]

        for i, item in enumerate(existing_items):
            tax_lines_initial[i] = [
                {
                    'tax_type': tl.tax_type,
                    'tax': str(tl.tax) if tl.tax else '',
                    'tax_account_id': tl.tax_account_id,
                    'tax_payment_account_id': tl.tax_payment_account_id,
                }
                for tl in item.tax_lines.all()
            ]

    eb_selected = f'lv1:{eb_group.entitas_bisnis_id}' if eb_group and eb_group.entitas_bisnis_id else ''

    return render(request, 'pendapatan/form.html', {
        'form': form,
        'item_forms': item_forms,
        'mode': 'edit',
        'header': header,
        'eb_options_json': json.dumps(_get_eb_dropdown_options()),
        'eb_selected': eb_selected,
        'tax_lines_initial_json': json.dumps(tax_lines_initial),
    })


@login_required
def pendapatan_detail(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(
        PendapatanHeader.objects
        .select_related('created_by', 'source_recurring', 'source_sales')
        .prefetch_related(
            'entitas_groups__entitas_bisnis',
            'entitas_groups__payment_account',
            'entitas_groups__items__revenue_account',
            'entitas_groups__items__sub_transaction_type',
            'entitas_groups__items__tax_lines__tax_account',
            'entitas_groups__items__tax_lines__tax_payment_account',
            'entitas_groups__items__jadwal__entri__jurnal_header',
            'entitas_groups__items__aset_kontrak',
            'event_logs__actor',
        ),
        pk=pk,
    )
    from apps.jurnal.models import JurnalHeader
    journals = list(
        JurnalHeader.objects
        .filter(uraian_transaksi__icontains=header.transaction_id)
        .prefetch_related('details__akun')
        .order_by('tanggal', 'id')
    )
    from apps.piutang.models import PiutangHeader
    piutang_list = list(
        PiutangHeader.objects
        .filter(source_pendapatan=header)
        .select_related('entitas_bisnis')
        .order_by('tanggal', 'id')
    )
    total_nilai = sum(
        kp.nilai_kontrak
        for eg in header.entitas_groups.all()
        for kp in eg.items.all()
    )
    # Annotate each KP with its linked PajakTransaksi records
    from apps.pajak.models import PajakTransaksi
    kp_ids = [kp.pk for eg in header.entitas_groups.all() for kp in eg.items.all()]
    pajak_per_kp: dict[int, list] = {}
    if kp_ids:
        for pt in (
            PajakTransaksi.objects
            .filter(source_type='pendapatan_kp', source_id__in=kp_ids)
            .select_related('akun_pajak', 'akun_lawan', 'jurnal_header')
            .order_by('created_at')
        ):
            pajak_per_kp.setdefault(pt.source_id, []).append(pt)
    for eg in header.entitas_groups.all():
        for kp in eg.items.all():
            kp.pajak_list = pajak_per_kp.get(kp.pk, [])

    # Merge pajak journals into the main journal history
    pajak_jurnal_ids = [
        pt.jurnal_header_id
        for pts in pajak_per_kp.values()
        for pt in pts
        if pt.jurnal_header_id
    ]
    for jh in journals:
        jh.source_label = 'pendapatan'
    if pajak_jurnal_ids:
        pajak_journals = list(
            JurnalHeader.objects
            .filter(pk__in=pajak_jurnal_ids)
            .prefetch_related('details__akun')
        )
        for jh in pajak_journals:
            jh.source_label = 'pajak'
        journals = sorted(journals + pajak_journals, key=lambda j: (j.tanggal, j.id))

    return render(request, 'pendapatan/detail.html', {
        'header': header,
        'journals': journals,
        'piutang_list': piutang_list,
        'total_nilai': total_nilai,
    })


@login_required
def pendapatan_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            confirm_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} berhasil dikonfirmasi.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)


@login_required
def pendapatan_void(request: HttpRequest, pk: int) -> HttpResponse:
    header = get_object_or_404(PendapatanHeader, pk=pk)
    if request.method == 'POST':
        try:
            void_pendapatan(header, user=request.user)
            dj_messages.success(request, f'{header.transaction_id} dibatalkan.')
        except ValueError as exc:
            dj_messages.error(request, str(exc))
    return redirect('pendapatan:detail', pk=pk)


@login_required
def pendapatan_hapus(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.jurnal.models import JurnalHeader, JurnalDetail
    from apps.piutang.models import PiutangHeader
    from apps.pajak.models import PajakTransaksi

    header = get_object_or_404(PendapatanHeader, pk=pk)
    if header.is_locked:
        dj_messages.error(request, 'Transaksi terkunci tidak dapat dihapus.')
        return redirect('pendapatan:detail', pk=pk)

    from .models import KewajibabPelaksanaan as KP, AsetKontrak
    kp_qs = list(KP.objects.filter(pendapatan_eb__pendapatan_header=header).select_related('revenue_account'))
    kp_ids = [kp.pk for kp in kp_qs]

    journals = list(
        JurnalHeader.objects
        .filter(uraian_transaksi__icontains=header.transaction_id)
        .prefetch_related('details__akun')
        .order_by('tanggal', 'id')
    )
    piutang_list = list(
        PiutangHeader.objects
        .filter(source_pendapatan=header)
        .select_related('entitas_bisnis')
        .order_by('tanggal', 'id')
    )
    aset_qs = AsetKontrak.objects.filter(kp__pendapatan_eb__pendapatan_header=header)
    jurnal_detail_count = sum(j.details.count() for j in journals)

    pajak_trx_list = list(
        PajakTransaksi.objects
        .filter(source_type='pendapatan_kp', source_id__in=kp_ids)
        .select_related('akun_pajak', 'akun_lawan', 'jurnal_header')
        .order_by('created_at')
    ) if kp_ids else []

    if request.method == 'POST' and request.POST.get('konfirmasi') == header.transaction_id:
        from django.db import transaction as db_transaction
        transaction_id = header.transaction_id
        with db_transaction.atomic():
            # Delete tax journals then PajakTransaksi
            pajak_jurnal_ids = [pt.jurnal_header_id for pt in pajak_trx_list if pt.jurnal_header_id]
            if pajak_jurnal_ids:
                JurnalDetail.objects.filter(jurnal_header_id__in=pajak_jurnal_ids).delete()
                JurnalHeader.objects.filter(pk__in=pajak_jurnal_ids).delete()
            if kp_ids:
                PajakTransaksi.objects.filter(source_type='pendapatan_kp', source_id__in=kp_ids).delete()
            # Delete piutang records (cascades to details, penerimaan, write-off, etc.)
            piutang_ids = [p.pk for p in piutang_list]
            if piutang_ids:
                PiutangHeader.objects.filter(pk__in=piutang_ids).delete()
            # Delete revenue journals (not cascade-linked)
            journal_ids = [j.pk for j in journals]
            JurnalDetail.objects.filter(jurnal_header_id__in=journal_ids).delete()
            JurnalHeader.objects.filter(pk__in=journal_ids).delete()
            # Cascade deletes everything else: EB groups, KPs, jadwal, entri, aset kontrak, event logs
            header.delete()
        dj_messages.success(request, f'Transaksi {transaction_id} dan semua data terkait berhasil dihapus.')
        return redirect('pendapatan:list')

    return render(request, 'pendapatan/hapus_konfirmasi.html', {
        'header': header,
        'journals': journals,
        'piutang_list': piutang_list,
        'kp_list': kp_qs,
        'aset_list': aset_qs,
        'jurnal_detail_count': jurnal_detail_count,
        'pajak_trx_list': pajak_trx_list,
    })


# ── PSAK 72 Action Views ─────────────────────────────────────────────────────

@login_required
@require_POST
def recognize_entry_view(request, entry_id):
    entri = get_object_or_404(EntriPengakuan, pk=entry_id)
    date_str = request.POST.get('journal_date')
    journal_date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    try:
        recognize_entry(entri.id, request.user, journal_date=journal_date)
        dj_messages.success(request, f'Pendapatan {entri.nilai} berhasil diakui.')
    except (ValueError, AssertionError) as e:
        dj_messages.error(request, str(e))
    header_id = entri.jadwal.kp.pendapatan_eb.pendapatan_header_id
    return redirect('pendapatan:detail', pk=header_id)


@login_required
@require_POST
def recognize_percentage_view(request: HttpRequest, jadwal_id: int) -> HttpResponse:
    jadwal = get_object_or_404(
        __import__('apps.pendapatan.models', fromlist=['JadwalPengakuan']).JadwalPengakuan,
        pk=jadwal_id,
    )
    from decimal import Decimal, InvalidOperation
    progress_str = request.POST.get('progress_pct', '').strip()
    date_str = request.POST.get('journal_date', '').strip()
    try:
        progress_pct = Decimal(progress_str)
    except (InvalidOperation, ValueError):
        dj_messages.error(request, 'Progress harus berupa angka antara 0 dan 100.')
        header_id = jadwal.kp.pendapatan_eb.pendapatan_header_id
        return redirect('pendapatan:detail', pk=header_id)
    journal_date = datetime.date.fromisoformat(date_str) if date_str else None
    try:
        recognize_percentage_completion(jadwal.pk, progress_pct, request.user, journal_date)
        dj_messages.success(request, f'Progress {progress_pct}% berhasil diakui.')
    except (ValueError, AssertionError) as e:
        dj_messages.error(request, str(e))
    header_id = jadwal.kp.pendapatan_eb.pendapatan_header_id
    return redirect('pendapatan:detail', pk=header_id)


@login_required
@require_POST
def konversi_aset_kontrak_view(request, aset_id):
    aset = get_object_or_404(AsetKontrak, pk=aset_id)
    try:
        konversi_aset_kontrak_ke_piutang(aset.id, request.user)
        dj_messages.success(request, 'Aset kontrak berhasil dikonversi.')
    except (ValueError, AssertionError) as e:
        dj_messages.error(request, str(e))
    header_id = aset.kp.pendapatan_eb.pendapatan_header_id
    return redirect('pendapatan:detail', pk=header_id)


# ── Recurring Template Views ──────────────────────────────────────────────────

@login_required
def recurring_list(request):
    templates = RecurringTemplate.objects.select_related('entitas_bisnis').filter(is_active=True)
    inactive = RecurringTemplate.objects.select_related('entitas_bisnis').filter(is_active=False)
    return render(request, 'pendapatan/recurring_list.html', {
        'templates': templates,
        'inactive': inactive,
    })


@login_required
def recurring_create(request):
    form = RecurringTemplateForm(request.POST or None)
    if form.is_valid():
        template = form.save(commit=False)
        template.created_by = request.user
        template.save()
        dj_messages.success(request, f'Template "{template.nama}" berhasil dibuat.')
        return redirect('pendapatan:recurring_detail', pk=template.pk)
    return render(request, 'pendapatan/recurring_form.html', {'form': form, 'title': 'Buat Template Recurring'})


@login_required
def recurring_detail(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    generated = template.generated_headers.order_by('-tanggal')[:20]
    return render(request, 'pendapatan/recurring_detail.html', {
        'template': template,
        'generated': generated,
    })


@login_required
def recurring_edit(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    form = RecurringTemplateForm(request.POST or None, instance=template)
    if form.is_valid():
        updated = form.save()
        if updated.tanggal_mulai > updated.tanggal_berikutnya:
            updated.tanggal_berikutnya = updated.tanggal_mulai
            updated.save(update_fields=['tanggal_berikutnya', 'updated_at'])
        dj_messages.success(request, 'Template berhasil diperbarui.')
        return redirect('pendapatan:recurring_detail', pk=template.pk)
    return render(request, 'pendapatan/recurring_form.html', {'form': form, 'title': 'Edit Template Recurring'})


@login_required
def recurring_delete(request, pk):
    template = get_object_or_404(RecurringTemplate, pk=pk)
    if request.method == 'POST':
        template.is_active = False
        template.save(update_fields=['is_active', 'updated_at'])
        dj_messages.success(request, f'Template "{template.nama}" dinonaktifkan.')
        return redirect('pendapatan:recurring_list')
    return redirect('pendapatan:recurring_detail', pk=pk)


@login_required
def recurring_generate(request, pk):
    if request.method != 'POST':
        return redirect('pendapatan:recurring_detail', pk=pk)
    template = get_object_or_404(RecurringTemplate, pk=pk, is_active=True)
    try:
        header = generate_from_recurring(template, user=request.user)
        dj_messages.success(request, f'Pendapatan {header.transaction_id} berhasil dibuat.')
    except ValueError as e:
        dj_messages.error(request, f'Gagal generate: {e}')
    return redirect('pendapatan:recurring_detail', pk=pk)


@login_required
def recurring_calendar(request):
    from datetime import date
    from dateutil.relativedelta import relativedelta

    today = date.today()
    end_date = today + relativedelta(months=3)
    templates = RecurringTemplate.objects.select_related('entitas_bisnis').filter(
        is_active=True,
        tanggal_berikutnya__gte=today,
        tanggal_berikutnya__lte=end_date,
    ).order_by('tanggal_berikutnya')
    return render(request, 'pendapatan/recurring_calendar.html', {
        'templates': templates,
        'today': today,
        'end_date': end_date,
    })
