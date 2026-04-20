"""Aset Tetap views — CRUD for AsetTetapRecord."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase, KategoriItem

from .forms import AsetTetapRecordForm
from .models import AsetTetapRecord
from .services import calculate_depreciation, process_depreciation

DEFAULT_DAYS = 30  # monthly processing default


@login_required
def aset_tetap_list(request: HttpRequest) -> HttpResponse:
    """List all fixed asset records with optional filters."""
    qs = AsetTetapRecord.objects.select_related(
        'item', 'item__kategori', 'item__coa_account', 'entitas_bisnis',
    ).all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')
    kondisi_filter = request.GET.get('kondisi', '')
    kategori_filter = request.GET.get('kategori', '')
    akun_filter = request.GET.get('coa_account', '')

    if tanggal_dari:
        qs = qs.filter(tanggal_perolehan__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal_perolehan__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)
    if kondisi_filter:
        qs = qs.filter(kondisi=kondisi_filter)
    if kategori_filter:
        qs = qs.filter(item__kategori_id=kategori_filter)
    if akun_filter:
        qs = qs.filter(item__coa_account_id=akun_filter)

    # Build dropdown lists scoped to ATP items
    kategori_list = KategoriItem.objects.filter(
        items__tipe_item='ATP'
    ).distinct().order_by('nama')
    akun_atp_list = Akun.objects.filter(
        item_masters__tipe_item='ATP'
    ).distinct().order_by('kode_akun')

    return render(request, 'aset_tetap/aset_tetap_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.filter(tipe_item='ATP').order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'kondisi_choices': AsetTetapRecord.KONDISI_CHOICES,
        'metode_choices': AsetTetapRecord.METODE_PENYUSUTAN_CHOICES,
        'kategori_list': kategori_list,
        'akun_atp_list': akun_atp_list,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
        'kondisi_filter': kondisi_filter,
        'kategori_filter': kategori_filter,
        'akun_filter': akun_filter,
    })


@login_required
def aset_tetap_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show fixed asset record detail with depreciation preview."""
    from decimal import Decimal
    record = get_object_or_404(
        AsetTetapRecord.objects.select_related('item', 'entitas_bisnis', 'purchase_item'),
        pk=pk,
    )

    # Calculate depreciation preview
    metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
    masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
    needs_activity_input = metode in ('service_hours', 'units_of_production')

    # For time-based methods, calculate current year number
    if masa > 0 and record.tanggal_perolehan:
        from datetime import date
        years_elapsed = (date.today() - record.tanggal_perolehan).days / Decimal('365.25')
        tahun_ke = int(years_elapsed) + 1
    else:
        tahun_ke = 1

    # Preview amount (for time-based methods), default 30 days
    preview_amount = Decimal('0')
    if not needs_activity_input:
        preview_amount = calculate_depreciation(record, tahun_ke=tahun_ke, days=DEFAULT_DAYS)

    # Depreciation journal history
    from apps.jurnal.models import JurnalHeader, JurnalDetail
    from django.db.models import Sum as _Sum
    from datetime import date as date_cls, timedelta
    dep_journals = list(
        JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Penyusutan {record.aset_number}',
        ).order_by('-tanggal')
    )

    # Build a map of journal pk -> depreciation amount (debit on akun 5.1.19.xx)
    dep_amounts = {}
    if dep_journals:
        journal_pks = [j.pk for j in dep_journals]
        amounts_qs = (
            JurnalDetail.objects
            .filter(jurnal_header_id__in=journal_pks, akun__kode_akun__startswith='5.1.19')
            .values('jurnal_header_id')
            .annotate(total=_Sum('debit'))
        )
        dep_amounts = {row['jurnal_header_id']: row['total'] for row in amounts_qs}

    last_dep = dep_journals[0] if dep_journals else None
    last_dep_date = last_dep.tanggal if last_dep else None

    # Build combined list for template: [{journal, amount}]
    dep_journal_data = [
        {'journal': j, 'amount': dep_amounts.get(j.pk, Decimal('0'))}
        for j in dep_journals
    ]
    if last_dep_date:
        suggested_start_date = last_dep_date + timedelta(days=1)
    else:
        suggested_start_date = record.tanggal_perolehan

    today = date_cls.today()
    suggested_days = (today - suggested_start_date).days + 1 if today >= suggested_start_date else 0

    return render(request, 'aset_tetap/aset_tetap_detail.html', {
        'record': record,
        'preview_amount': preview_amount,
        'tahun_ke': tahun_ke,
        'needs_activity_input': needs_activity_input,
        'metode': metode,
        'can_depreciate': record.nilai_buku > record.nilai_residu,
        'dep_journal_data': dep_journal_data,
        'default_days': DEFAULT_DAYS,
        'last_dep_date': last_dep_date,
        'suggested_start_date': suggested_start_date,
        'suggested_days': suggested_days,
        'today': today,
    })


@login_required
def aset_tetap_create(request: HttpRequest) -> HttpResponse:
    """Create a new fixed asset record."""
    if request.method == 'POST':
        form = AsetTetapRecordForm(request.POST)
        if form.is_valid():
            record = form.save()
            messages.success(request, f'Aset tetap {record.aset_number} berhasil dibuat.')
            return redirect('aset_tetap:detail', pk=record.pk)
    else:
        form = AsetTetapRecordForm()
    return render(request, 'aset_tetap/aset_tetap_form.html', {'form': form, 'title': 'Tambah Aset Tetap'})


@login_required
def aset_tetap_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit an existing fixed asset record."""
    record = get_object_or_404(AsetTetapRecord, pk=pk)
    if request.method == 'POST':
        form = AsetTetapRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, f'Aset tetap {record.aset_number} berhasil diperbarui.')
            return redirect('aset_tetap:detail', pk=record.pk)
    else:
        form = AsetTetapRecordForm(instance=record)
    return render(request, 'aset_tetap/aset_tetap_form.html', {
        'form': form,
        'record': record,
        'title': f'Edit {record.aset_number}',
    })


@login_required
def aset_tetap_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a fixed asset record, removing all associated depreciation journals."""
    from apps.jurnal.models import JurnalHeader
    from apps.jurnal.utils import log_jurnal_terhapus

    record = get_object_or_404(AsetTetapRecord.objects.select_related('item', 'entitas_bisnis'), pk=pk)

    # Find all depreciation journals for this asset
    dep_journals = list(
        JurnalHeader.objects.filter(
            uraian_transaksi__startswith=f'Penyusutan {record.aset_number}'
        ).order_by('tanggal')
    )

    if request.method == 'POST':
        from django.db import transaction as db_transaction
        number = record.aset_number
        with db_transaction.atomic():
            for journal in dep_journals:
                log_jurnal_terhapus(journal, 'aset_tetap', request)
                journal.details.all().delete()
                journal.delete()
            record.delete()
        messages.success(request, f'Aset tetap {number} dan {len(dep_journals)} jurnal penyusutan berhasil dihapus.')
        return redirect('aset_tetap:list')

    return render(request, 'aset_tetap/aset_tetap_delete.html', {
        'record': record,
        'dep_journals': dep_journals,
    })


@login_required
def aset_tetap_process_depreciation(request: HttpRequest, pk: int) -> HttpResponse:
    """Process depreciation for a fixed asset record, creating a journal entry."""
    from decimal import Decimal, InvalidOperation

    record = get_object_or_404(
        AsetTetapRecord.objects.select_related('item', 'entitas_bisnis'),
        pk=pk,
    )

    if request.method != 'POST':
        return redirect('aset_tetap:detail', pk=pk)

    metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
    tanggal_str = request.POST.get('tanggal', '')

    try:
        from datetime import date as date_cls
        tanggal = date_cls.fromisoformat(tanggal_str) if tanggal_str else None
    except ValueError:
        tanggal = None

    # For activity-based methods, get input values
    if metode == 'service_hours':
        try:
            jam_aktual = Decimal(request.POST.get('jam_aktual', '0'))
        except InvalidOperation:
            messages.error(request, 'Jam kerja aktual harus berupa angka.')
            return redirect('aset_tetap:detail', pk=pk)
        depreciation = calculate_depreciation(record, jam_aktual=jam_aktual)
    elif metode == 'units_of_production':
        try:
            unit_aktual = Decimal(request.POST.get('unit_aktual', '0'))
        except InvalidOperation:
            messages.error(request, 'Unit produksi aktual harus berupa angka.')
            return redirect('aset_tetap:detail', pk=pk)
        depreciation = calculate_depreciation(record, unit_aktual=unit_aktual)
    else:
        # Auto-calculate days from the appropriate start date to tanggal_jurnal
        from apps.jurnal.models import JurnalHeader as _JH
        from datetime import timedelta as _td
        last_dep = _JH.objects.filter(
            uraian_transaksi__startswith=f'Penyusutan {record.aset_number}',
        ).order_by('-tanggal').first()
        if last_dep:
            start_date = last_dep.tanggal + _td(days=1)
        else:
            start_date = record.tanggal_perolehan

        if tanggal is None:
            messages.error(request, 'Tanggal jurnal wajib diisi.')
            return redirect('aset_tetap:detail', pk=pk)
        if tanggal < start_date:
            messages.error(
                request,
                f'Tanggal jurnal ({tanggal}) tidak boleh sebelum tanggal mulai perhitungan ({start_date}).',
            )
            return redirect('aset_tetap:detail', pk=pk)

        hari = (tanggal - start_date).days + 1
        masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
        if masa > 0 and record.tanggal_perolehan:
            from datetime import date as d
            years_elapsed = (tanggal - record.tanggal_perolehan).days / Decimal('365.25')
            tahun_ke = min(int(years_elapsed) + 1, masa)
        else:
            tahun_ke = 1
        depreciation = calculate_depreciation(record, tahun_ke=tahun_ke, days=hari)

    try:
        header = process_depreciation(record, depreciation, tanggal)
        messages.success(
            request,
            f'Penyusutan {record.aset_number} sebesar Rp {depreciation:,.0f} berhasil diproses. '
            f'Jurnal: {header.nomor_transaksi}',
        )
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('aset_tetap:detail', pk=pk)


@login_required
def aset_tetap_bulk_depreciation(request: HttpRequest) -> HttpResponse:
    """Process depreciation for selected fixed assets in one batch."""
    from datetime import date as date_cls, timedelta as _td

    if request.method != 'POST':
        return redirect('aset_tetap:list')

    tanggal_str = request.POST.get('tanggal', '')
    try:
        tanggal = date_cls.fromisoformat(tanggal_str) if tanggal_str else date_cls.today()
    except ValueError:
        tanggal = date_cls.today()

    # Entitas bisnis filter (required in UI but handled gracefully here)
    eb_id = request.POST.get('entitas_bisnis', '')

    # Selected asset IDs from checkboxes
    selected_ids = request.POST.getlist('record_ids')

    records = AsetTetapRecord.objects.select_related('item', 'entitas_bisnis')
    if selected_ids:
        records = records.filter(pk__in=selected_ids)
    else:
        records = records.all()
    if eb_id:
        records = records.filter(entitas_bisnis_id=eb_id)

    success_count = 0
    skip_count = 0
    error_msgs = []

    for record in records:
        if record.nilai_buku <= record.nilai_residu:
            skip_count += 1
            continue

        metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
        if metode in ('service_hours', 'units_of_production'):
            skip_count += 1
            continue

        # Calculate days from last depreciation or acquisition date
        from apps.jurnal.models import JurnalHeader
        last_dep = (
            JurnalHeader.objects
            .filter(
                nomor_transaksi__startswith='TRX-DEP-',
                uraian_transaksi__contains=record.aset_number,
            )
            .order_by('-tanggal')
            .first()
        )
        start_date = (last_dep.tanggal + _td(days=1)) if last_dep else record.tanggal_perolehan
        if tanggal < start_date:
            skip_count += 1
            continue

        hari = (tanggal - start_date).days + 1

        masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
        tahun_ke = 1
        if masa > 0 and record.tanggal_perolehan:
            years_elapsed = (tanggal - record.tanggal_perolehan).days / Decimal('365.25')
            tahun_ke = min(int(years_elapsed) + 1, masa)

        depreciation = calculate_depreciation(record, tahun_ke=tahun_ke, days=hari)
        if depreciation <= 0:
            skip_count += 1
            continue

        try:
            process_depreciation(record, depreciation, tanggal)
            success_count += 1
        except ValueError as e:
            error_msgs.append(f'{record.aset_number}: {e}')

    if success_count:
        messages.success(
            request,
            f'Bulk penyusutan selesai: {success_count} aset diproses, '
            f'{skip_count} dilewati.',
        )
    else:
        messages.warning(request, f'Tidak ada aset yang diproses. {skip_count} dilewati.')

    for msg in error_msgs[:5]:
        messages.error(request, msg)

    return redirect('aset_tetap:list')


@login_required
def aset_tetap_bulk_preview(request: HttpRequest) -> JsonResponse:
    """AJAX preview: calculate depreciation amounts for all eligible assets."""
    from datetime import date as date_cls, timedelta as _td

    tanggal_str = request.GET.get('tanggal', '')
    try:
        tanggal = date_cls.fromisoformat(tanggal_str) if tanggal_str else None
    except ValueError:
        tanggal = None

    if not tanggal:
        return JsonResponse({'error': 'Tanggal wajib diisi.'}, status=400)

    eb_id = request.GET.get('entitas_bisnis', '')
    metode_filter = request.GET.getlist('metode')  # optional list of metode codes

    from apps.jurnal.models import JurnalHeader

    records = AsetTetapRecord.objects.select_related('item', 'entitas_bisnis').all()
    if eb_id:
        records = records.filter(entitas_bisnis_id=eb_id)
    if metode_filter:
        # Filter by records whose effective metode is in the list
        records = records.filter(
            models.Q(metode_penyusutan__in=metode_filter) |
            models.Q(metode_penyusutan='', item__metode_penyusutan__in=metode_filter) |
            models.Q(metode_penyusutan__isnull=True, item__metode_penyusutan__in=metode_filter)
        )
    preview = []

    for record in records:
        if record.nilai_buku <= record.nilai_residu:
            continue
        metode = record.metode_penyusutan or (record.item.metode_penyusutan if record.item else '')
        if metode in ('service_hours', 'units_of_production'):
            continue

        last_dep = (
            JurnalHeader.objects
            .filter(
                nomor_transaksi__startswith='TRX-DEP-',
                uraian_transaksi__contains=record.aset_number,
            )
            .order_by('-tanggal')
            .first()
        )
        start_date = (last_dep.tanggal + _td(days=1)) if last_dep else record.tanggal_perolehan
        if tanggal < start_date:
            continue

        hari = (tanggal - start_date).days + 1

        masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
        tahun_ke = 1
        if masa > 0 and record.tanggal_perolehan:
            years_elapsed = (tanggal - record.tanggal_perolehan).days / Decimal('365.25')
            tahun_ke = min(int(years_elapsed) + 1, masa)

        depreciation = calculate_depreciation(record, tahun_ke=tahun_ke, days=hari)
        if depreciation <= 0:
            continue

        new_book_value = record.nilai_buku - depreciation
        preview.append({
            'id': record.pk,
            'aset_number': record.aset_number,
            'item_nama': record.item.nama if record.item else '-',
            'metode': record.get_metode_penyusutan_display(),
            'nilai_buku': float(record.nilai_buku),
            'hari': hari,
            'depreciation': float(depreciation),
            'new_book_value': float(new_book_value),
            'entitas_bisnis': record.entitas_bisnis.nama if record.entitas_bisnis else '-',
        })

    return JsonResponse({'records': preview})


@login_required
def delete_depreciation_journal(request: HttpRequest, pk: int, jurnal_pk: int) -> HttpResponse:
    """Delete a single depreciation journal and reverse its akumulasi_penyusutan."""
    from apps.jurnal.models import JurnalHeader, JurnalDetail
    from apps.jurnal.utils import log_jurnal_terhapus
    from django.db import transaction as db_transaction
    from django.db.models import Sum as _Sum

    record = get_object_or_404(
        AsetTetapRecord.objects.select_related('item', 'entitas_bisnis'),
        pk=pk,
    )
    journal = get_object_or_404(
        JurnalHeader,
        pk=jurnal_pk,
        uraian_transaksi__startswith=f'Penyusutan {record.aset_number}',
    )

    # Get the depreciation amount from the beban penyusutan (debit on 5.1.19.xx)
    agg = (
        JurnalDetail.objects
        .filter(jurnal_header=journal, akun__kode_akun__startswith='5.1.19')
        .aggregate(total=_Sum('debit'))
    )
    dep_amount = agg['total'] or Decimal('0')

    if request.method == 'POST':
        with db_transaction.atomic():
            log_jurnal_terhapus(journal, 'aset_tetap', request)
            journal.details.all().delete()
            journal.delete()
            # Reverse accumulated depreciation
            record.akumulasi_penyusutan = max(
                Decimal('0'),
                record.akumulasi_penyusutan - dep_amount,
            )
            record.save(update_fields=['akumulasi_penyusutan'])
        messages.success(
            request,
            f'Jurnal {journal.nomor_transaksi} dihapus. '
            f'Akumulasi penyusutan dikurangi Rp {dep_amount:,.0f}.',
        )
        return redirect('aset_tetap:detail', pk=pk)

    return render(request, 'aset_tetap/delete_dep_journal_confirm.html', {
        'record': record,
        'journal': journal,
        'dep_amount': dep_amount,
    })
