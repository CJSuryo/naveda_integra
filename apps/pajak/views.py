from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .exceptions import MasaPajakTerkunciError, PajakStatusError
from .forms import OverridePajakForm, TarifPajakForm
from .models import MasaPajak, PajakTransaksi, TarifPajak
from .services import override_pajak


@login_required
def transaksi_list(request):
    qs = PajakTransaksi.objects.select_related('akun_pajak', 'akun_lawan', 'entitas_bisnis').order_by('-created_at')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'pajak/transaksi_list.html', {
        'transaksi_list': qs,
        'status_filter': status,
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
