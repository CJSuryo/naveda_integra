from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages as dj_messages


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
