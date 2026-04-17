"""Ekuitas views — Modal Disetor CRUD + journal integration."""
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.entitas_bisnis.models import EntitasBisnis

from .models import ModalDisetor, Pemilik
from .services import create_modal_disetor, delete_modal_disetor


# ── List ─────────────────────────────────────────────────────────────────────

@login_required
def ekuitas_list(request: HttpRequest) -> HttpResponse:
    """List all modal disetor records with optional EB filter."""
    qs = list(ModalDisetor.objects.select_related('entitas_bisnis', 'pemilik', 'jurnal_header').all())

    eb_filter = request.GET.get('entitas_bisnis', '')
    if eb_filter:
        qs = [r for r in qs if str(r.entitas_bisnis_id) == eb_filter]

    # Attach persentase attribute to each record when EB is filtered
    if eb_filter:
        total_all = sum(r.jumlah_modal for r in qs) or Decimal('1')
        for r in qs:
            r.persentase = (r.jumlah_modal / total_all * 100).quantize(Decimal('0.01'))
    else:
        for r in qs:
            r.persentase = None

    eb_list = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
    return render(request, 'ekuitas/ekuitas_list.html', {
        'records': qs,
        'entitas_list': eb_list,
        'eb_filter': eb_filter,
    })


# ── History ──────────────────────────────────────────────────────────────────

@login_required
def ekuitas_history(request: HttpRequest) -> HttpResponse:
    """Show modal disetor history for an EB up to a chosen date."""
    eb_filter = request.GET.get('entitas_bisnis', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')

    records: list = []
    total_modal = Decimal('0')
    selected_eb = None

    if eb_filter:
        qs = ModalDisetor.objects.select_related('entitas_bisnis', 'pemilik', 'jurnal_header').filter(
            entitas_bisnis_id=eb_filter,
        )
        if tanggal_sampai:
            qs = qs.filter(tanggal_setor__lte=tanggal_sampai)
        records = list(qs.order_by('pemilik__nama', 'tanggal_setor'))

        total_modal = sum(r.jumlah_modal for r in records) or Decimal('1')
        for r in records:
            r.persentase = (r.jumlah_modal / total_modal * 100).quantize(Decimal('0.01'))

        try:
            selected_eb = EntitasBisnis.objects.get(pk=eb_filter)
        except EntitasBisnis.DoesNotExist:
            pass

    return render(request, 'ekuitas/ekuitas_history.html', {
        'records': records,
        'total_modal': total_modal,
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'eb_filter': eb_filter,
        'tanggal_sampai': tanggal_sampai,
        'selected_eb': selected_eb,
    })


# ── Detail ───────────────────────────────────────────────────────────────────

@login_required
def ekuitas_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show modal disetor detail with debit lines and journal link."""
    record = get_object_or_404(
        ModalDisetor.objects.select_related('entitas_bisnis', 'pemilik', 'jurnal_header')
                            .prefetch_related('debit_lines__akun'),
        pk=pk,
    )
    # Compute persentase for this record's EB
    total_all = ModalDisetor.objects.filter(
        entitas_bisnis=record.entitas_bisnis,
    ).aggregate(t=Sum('jumlah_modal'))['t'] or Decimal('1')
    persentase = (record.jumlah_modal / total_all * 100).quantize(Decimal('0.01'))

    return render(request, 'ekuitas/ekuitas_detail.html', {
        'record': record,
        'persentase': persentase,
    })


# ── Create ───────────────────────────────────────────────────────────────────

@login_required
def ekuitas_create(request: HttpRequest) -> HttpResponse:
    """Create a new modal disetor record with journal entry."""
    eb_list = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
    pemilik_list = Pemilik.objects.order_by('nama')
    akun_autocomplete_url = reverse('jurnal:akun_autocomplete')

    if request.method == 'POST':
        eb_id = request.POST.get('entitas_bisnis', '').strip()
        pemilik_id = request.POST.get('pemilik', '').strip()
        tanggal = request.POST.get('tanggal', '').strip()
        keterangan = request.POST.get('keterangan', '').strip()
        debit_json = request.POST.get('debit_lines_json', '[]')

        errors: dict = {}
        if not eb_id:
            errors['entitas_bisnis'] = 'Entitas Bisnis wajib dipilih.'
        if not pemilik_id:
            errors['pemilik'] = 'Pemilik wajib dipilih.'
        if not tanggal:
            errors['tanggal'] = 'Tanggal wajib diisi.'

        try:
            debit_lines = json.loads(debit_json)
        except (ValueError, TypeError):
            debit_lines = []
        if not debit_lines:
            errors['debit_lines'] = 'Minimal 1 baris debit akun wajib diisi.'

        jumlah_modal = Decimal('0')
        if not errors:
            try:
                jumlah_modal = sum(
                    Decimal(str(d.get('jumlah', 0))) for d in debit_lines
                )
            except InvalidOperation:
                errors['debit_lines'] = 'Jumlah pada baris debit tidak valid.'

        if not errors:
            try:
                record = create_modal_disetor(
                    entitas_bisnis_id=int(eb_id),
                    pemilik_id=int(pemilik_id),
                    tanggal=tanggal,
                    jumlah_modal=jumlah_modal,
                    keterangan=keterangan,
                    debit_lines=debit_lines,
                )
                messages.success(request, 'Modal disetor berhasil disimpan dan jurnal dibuat.')
                return redirect('ekuitas:detail', pk=record.pk)
            except ValueError as e:
                errors['form'] = str(e)

        return render(request, 'ekuitas/ekuitas_create.html', {
            'eb_list': eb_list,
            'pemilik_list': pemilik_list,
            'errors': errors,
            'posted_eb': eb_id,
            'posted_pemilik': pemilik_id,
            'posted_tanggal': tanggal,
            'posted_keterangan': keterangan,
            'akun_autocomplete_url': akun_autocomplete_url,
        })

    return render(request, 'ekuitas/ekuitas_create.html', {
        'eb_list': eb_list,
        'pemilik_list': pemilik_list,
        'errors': {},
        'posted_tanggal': timezone.now().date().isoformat(),
        'akun_autocomplete_url': akun_autocomplete_url,
    })


# ── Delete ───────────────────────────────────────────────────────────────────

@login_required
def ekuitas_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a modal disetor record and its journal entry."""
    record = get_object_or_404(
        ModalDisetor.objects.select_related('pemilik', 'jurnal_header'),
        pk=pk,
    )
    if request.method == 'POST':
        label = str(record)
        try:
            delete_modal_disetor(record)
            messages.success(request, f'Modal disetor {label} berhasil dihapus.')
        except Exception as e:
            messages.error(request, f'Gagal menghapus: {e}')
        return redirect('ekuitas:list')
    return render(request, 'ekuitas/ekuitas_delete.html', {'record': record})


# ── Pemilik API ───────────────────────────────────────────────────────────────

@login_required
def api_pemilik_search(request: HttpRequest) -> JsonResponse:
    """Autocomplete endpoint for Pemilik — returns [{id, text}]."""
    term = request.GET.get('term', '').strip()
    qs = Pemilik.objects.all()
    if term:
        qs = qs.filter(nama__icontains=term)
    qs = qs.order_by('nama')[:30]
    return JsonResponse([{'id': p.pk, 'text': p.nama} for p in qs], safe=False)


@login_required
@require_POST
def api_pemilik_create(request: HttpRequest) -> JsonResponse:
    """Create a new Pemilik and return {id, text}."""
    nama = request.POST.get('nama', '').strip()
    if not nama:
        return JsonResponse({'error': 'Nama pemilik wajib diisi.'}, status=400)
    if Pemilik.objects.filter(nama__iexact=nama).exists():
        p = Pemilik.objects.get(nama__iexact=nama)
        return JsonResponse({'id': p.pk, 'text': p.nama})
    p = Pemilik.objects.create(nama=nama)
    return JsonResponse({'id': p.pk, 'text': p.nama})
