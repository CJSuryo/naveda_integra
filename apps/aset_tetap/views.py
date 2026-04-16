"""Aset Tetap views — CRUD for AsetTetapRecord."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .forms import AsetTetapRecordForm
from .models import AsetTetapRecord
from .services import calculate_depreciation, process_depreciation


@login_required
def aset_tetap_list(request: HttpRequest) -> HttpResponse:
    """List all fixed asset records with optional filters."""
    qs = AsetTetapRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')
    kondisi_filter = request.GET.get('kondisi', '')

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

    return render(request, 'aset_tetap/aset_tetap_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.filter(tipe_item='ATP').order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'kondisi_choices': AsetTetapRecord.KONDISI_CHOICES,
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
        'kondisi_filter': kondisi_filter,
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

    # Preview amount (for time-based methods)
    preview_amount = Decimal('0')
    if not needs_activity_input:
        preview_amount = calculate_depreciation(record, tahun_ke=tahun_ke)

    # Depreciation journal history
    from apps.jurnal.models import JurnalHeader
    dep_journals = JurnalHeader.objects.filter(
        uraian_transaksi__startswith=f'Penyusutan {record.aset_number}',
    ).order_by('-tanggal')

    return render(request, 'aset_tetap/aset_tetap_detail.html', {
        'record': record,
        'preview_amount': preview_amount,
        'tahun_ke': tahun_ke,
        'needs_activity_input': needs_activity_input,
        'metode': metode,
        'can_depreciate': record.nilai_buku > record.nilai_residu,
        'dep_journals': dep_journals,
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
    """Delete a fixed asset record."""
    record = get_object_or_404(AsetTetapRecord, pk=pk)
    if request.method == 'POST':
        number = record.aset_number
        record.delete()
        messages.success(request, f'Aset tetap {number} berhasil dihapus.')
        return redirect('aset_tetap:list')
    return redirect('aset_tetap:list')


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
        # Allow manual override
        manual_amount = request.POST.get('amount', '')
        if manual_amount:
            try:
                depreciation = Decimal(manual_amount)
            except InvalidOperation:
                messages.error(request, 'Jumlah penyusutan harus berupa angka.')
                return redirect('aset_tetap:detail', pk=pk)
        else:
            masa = record.masa_manfaat or (record.item.masa_manfaat if record.item else 0) or 0
            if masa > 0 and record.tanggal_perolehan:
                from datetime import date as d
                years_elapsed = (d.today() - record.tanggal_perolehan).days / Decimal('365.25')
                tahun_ke = int(years_elapsed) + 1
            else:
                tahun_ke = 1
            depreciation = calculate_depreciation(record, tahun_ke=tahun_ke)

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
