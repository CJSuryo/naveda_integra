"""Inventory views — CRUD for InventoryRecord."""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import InventoryRecord


@login_required
def inventory_list(request: HttpRequest) -> HttpResponse:
    """List all inventory records with optional filters."""
    qs = InventoryRecord.objects.select_related('item', 'entitas_bisnis').all()

    tanggal_dari = request.GET.get('tanggal_dari', '')
    tanggal_sampai = request.GET.get('tanggal_sampai', '')
    item_filter = request.GET.get('item', '')
    eb_filter = request.GET.get('entitas_bisnis', '')

    if tanggal_dari:
        qs = qs.filter(tanggal__gte=tanggal_dari)
    if tanggal_sampai:
        qs = qs.filter(tanggal__lte=tanggal_sampai)
    if item_filter:
        qs = qs.filter(item_id=item_filter)
    if eb_filter:
        qs = qs.filter(entitas_bisnis_id=eb_filter)

    from apps.purchase.models import ItemMasterPurchase
    from apps.entitas_bisnis.models import EntitasBisnis

    return render(request, 'inventory/inventory_list.html', {
        'records': qs,
        'items': ItemMasterPurchase.objects.all().order_by('item_id'),
        'entitas_list': EntitasBisnis.objects.filter(status_aktif=True).order_by('nama'),
        'tanggal_dari': tanggal_dari,
        'tanggal_sampai': tanggal_sampai,
        'item_filter': item_filter,
        'eb_filter': eb_filter,
    })


@login_required
def inventory_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Show inventory record detail."""
    record = get_object_or_404(
        InventoryRecord.objects.select_related('item', 'entitas_bisnis', 'purchase_item'),
        pk=pk,
    )
    return render(request, 'inventory/inventory_detail.html', {'record': record})
