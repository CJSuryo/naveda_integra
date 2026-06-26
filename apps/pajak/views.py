import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .exceptions import MasaPajakTerkunciError, PajakStatusError, TarifPajakTidakDitemukan
from .forms import OverridePajakForm, TarifPajakForm
from .models import MasaPajak, PajakTransaksi, TarifPajak
from .services import batal_pajak, compute_pajak, override_pajak

TAX_TYPE_MAP = {
    'ppn_keluaran': 'ppn_umum',
    'pph_23': 'pph_23_jasa',
    'pph_21': 'pph_21_bukan_pegawai',
    'pph_4_2': 'pph_4_2_sewa',
}


@login_required
def hitung_pajak(request):
    """AJAX endpoint: compute tax given tax_type (pendapatan choices), dpp, tanggal."""
    tax_type_kp = request.GET.get('tax_type', '')
    dpp_raw = request.GET.get('dpp', '')
    tanggal_raw = request.GET.get('tanggal', '')

    jenis_pajak = TAX_TYPE_MAP.get(tax_type_kp)
    if not jenis_pajak:
        return JsonResponse({'error': f'Tipe pajak "{tax_type_kp}" tidak dikenali.'}, status=400)

    try:
        dpp = Decimal(dpp_raw)
    except (InvalidOperation, ValueError):
        return JsonResponse({'error': 'DPP tidak valid.'}, status=400)

    try:
        tanggal = datetime.strptime(tanggal_raw, '%Y-%m-%d').date() if tanggal_raw else date.today()
    except ValueError:
        return JsonResponse({'error': 'Format tanggal tidak valid (YYYY-MM-DD).'}, status=400)

    try:
        result = compute_pajak(jenis_pajak, dpp, tanggal)
    except TarifPajakTidakDitemukan as e:
        return JsonResponse({'error': str(e)}, status=404)

    return JsonResponse({
        'jumlah_pajak': str(result['jumlah_pajak'].quantize(Decimal('0.01'))),
        'tarif_persen': str(result['tarif_persen']),
        'dpp_efektif': str(result['dpp_efektif'].quantize(Decimal('0.01'))),
    })


@login_required
def transaksi_list(request):
    from apps.purchase.views import _get_eb_tree, _resolve_eb_selection
    from django.urls import reverse

    status = request.GET.get('status', '')
    eb_filter_list = [v for v in request.GET.getlist('entitas_bisnis') if v]

    qs = PajakTransaksi.objects.select_related(
        'akun_pajak', 'akun_lawan', 'entitas_bisnis',
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)
    if eb_filter_list:
        lv1_ids = set()
        for sel in eb_filter_list:
            resolved = _resolve_eb_selection(sel, request.user)
            if resolved:
                lv1_ids.add(resolved['lv1_id'])
        if lv1_ids:
            qs = qs.filter(entitas_bisnis_id__in=lv1_ids)

    trx_list = list(qs)

    # Resolve source transaction label and URL for display
    kp_ids = [pt.source_id for pt in trx_list if pt.source_type == 'pendapatan_kp']
    kp_to_header = {}
    if kp_ids:
        from apps.pendapatan.models import KewajibabPelaksanaan
        for kp in KewajibabPelaksanaan.objects.filter(pk__in=kp_ids).select_related(
            'pendapatan_eb__pendapatan_header'
        ):
            kp_to_header[kp.pk] = kp.pendapatan_eb.pendapatan_header

    for pt in trx_list:
        if pt.source_type == 'pendapatan_kp' and pt.source_id in kp_to_header:
            h = kp_to_header[pt.source_id]
            pt.source_label = h.transaction_id
            pt.source_url = reverse('pendapatan:detail', args=[h.pk])
        else:
            pt.source_label = f'{pt.get_source_type_display()} #{pt.source_id}'
            pt.source_url = None

    return render(request, 'pajak/transaksi_list.html', {
        'transaksi_list': trx_list,
        'status_filter': status,
        'eb_tree': _get_eb_tree(request.user),
        'eb_filter_list': eb_filter_list,
    })


@login_required
def transaksi_edit(request, pk):
    pajak_trx = get_object_or_404(PajakTransaksi, pk=pk)
    if pajak_trx.status not in ('draft', 'final'):
        return HttpResponseForbidden('Hanya transaksi berstatus "draft" atau "final" yang dapat diubah.')
    if request.method == 'POST':
        form = OverridePajakForm(request.POST)
        if form.is_valid():
            try:
                override_pajak(pajak_trx, form.cleaned_data['jumlah_baru'], modified_by=request.user)
                return redirect('pajak:transaksi_list')
            except (PajakStatusError, MasaPajakTerkunciError) as e:
                form.add_error(None, str(e))
    else:
        form = OverridePajakForm(initial={'jumlah_baru': pajak_trx.jumlah_pajak})
    return render(request, 'pajak/transaksi_edit.html', {
        'pajak_trx': pajak_trx,
        'form': form,
    })


@login_required
def transaksi_detail(request, pk):
    pajak_trx = get_object_or_404(
        PajakTransaksi.objects.select_related(
            'akun_pajak', 'akun_lawan', 'entitas_bisnis',
            'jurnal_header', 'modified_by',
        ),
        pk=pk,
    )
    jurnal_details = []
    if pajak_trx.jurnal_header_id:
        from apps.jurnal.models import JurnalDetail
        jurnal_details = list(
            JurnalDetail.objects
            .filter(jurnal_header=pajak_trx.jurnal_header)
            .select_related('akun')
            .order_by('id')
        )
    return render(request, 'pajak/transaksi_detail.html', {
        'pajak_trx': pajak_trx,
        'jurnal_details': jurnal_details,
    })


@login_required
@require_POST
def transaksi_hapus(request, pk):
    """Physical delete — removes the record from DB regardless of journal state."""
    pajak_trx = get_object_or_404(PajakTransaksi, pk=pk)
    if pajak_trx.status == 'disetor':
        return HttpResponseForbidden('Transaksi yang sudah disetor tidak dapat dihapus.')
    pajak_trx.delete()
    dj_messages.success(request, 'Transaksi pajak berhasil dihapus.')
    return redirect('pajak:transaksi_list')


@login_required
@require_POST
def transaksi_batalkan(request, pk):
    """Accounting cancellation — posts a reversal journal and sets status to 'dibatalkan'."""
    pajak_trx = get_object_or_404(PajakTransaksi, pk=pk)
    if pajak_trx.status != 'final':
        return HttpResponseForbidden('Hanya transaksi berstatus "final" yang dapat dibatalkan.')
    try:
        batal_pajak(pajak_trx)
        dj_messages.success(request, 'Transaksi pajak dibatalkan dan jurnal pembalik telah dibuat.')
    except (PajakStatusError, MasaPajakTerkunciError) as e:
        dj_messages.error(request, str(e))
    return redirect('pajak:transaksi_detail', pk=pk)


@login_required
def masa_list(request):
    qs = MasaPajak.objects.all()
    return render(request, 'pajak/masa_list.html', {
        'masa_list': qs,
    })


@login_required
def masa_detail(request, pk):
    masa = get_object_or_404(MasaPajak, pk=pk)
    transaksi = PajakTransaksi.objects.select_related(
        'akun_pajak', 'akun_lawan', 'entitas_bisnis',
    ).filter(
        masa_pajak__year=masa.tahun,
        masa_pajak__month=masa.bulan,
    ).order_by('-created_at')
    return render(request, 'pajak/masa_detail.html', {
        'masa': masa,
        'transaksi_list': transaksi,
    })


@login_required
def tarif_list(request):
    qs = TarifPajak.objects.order_by('jenis_pajak', 'berlaku_mulai')
    return render(request, 'pajak/tarif_list.html', {
        'tarif_list': qs,
    })


@login_required
def tarif_form(request, pk=None):
    instance = get_object_or_404(TarifPajak, pk=pk) if pk else None
    if request.method == 'POST':
        form = TarifPajakForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return redirect('pajak:tarif_list')
    else:
        form = TarifPajakForm(instance=instance)
    return render(request, 'pajak/tarif_form.html', {
        'form': form,
        'instance': instance,
    })
