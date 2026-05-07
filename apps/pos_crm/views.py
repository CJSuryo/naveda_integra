# apps/pos_crm/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages

from apps.accounts.views import _check_perm
from apps.pos_crm.models import Member, MemberPointLog
from apps.pos_crm.forms import MemberRegisterForm
from apps.pos_crm.services.member_service import register_member, lookup_member


def member_list(request):
    denied = _check_perm(request.user, 'pos.manage_members')
    if denied:
        return denied
    merchant_id = request.GET.get('merchant')
    members = Member.objects.select_related('merchant_config').order_by('-joined_at')
    if merchant_id:
        members = members.filter(merchant_config_id=merchant_id)
    return render(request, 'pos_crm/member_list.html', {'members': members})


def member_detail(request, pk):
    denied = _check_perm(request.user, 'pos.manage_members')
    if denied:
        return denied
    member = get_object_or_404(Member, pk=pk)
    logs = member.point_logs.select_related('order').order_by('-created_at')[:50]
    return render(request, 'pos_crm/member_detail.html', {'member': member, 'point_logs': logs})


def member_register(request):
    denied = _check_perm(request.user, 'pos.manage_members')
    if denied:
        return denied
    from apps.pos_config.models import MerchantPOSConfig
    merchant_id = request.GET.get('merchant') or request.POST.get('merchant')
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_id)
    if request.method == 'POST':
        form = MemberRegisterForm(request.POST)
        if form.is_valid():
            try:
                member = register_member(
                    merchant=merchant,
                    name=form.cleaned_data['name'],
                    phone=form.cleaned_data['phone'],
                    email=form.cleaned_data.get('email', ''),
                    birth_date=form.cleaned_data.get('birth_date'),
                    notes=form.cleaned_data.get('notes', ''),
                )
                messages.success(request, f'Member {member.member_id} berhasil didaftarkan.')
                return redirect('pos_member_detail', pk=member.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = MemberRegisterForm()
    return render(request, 'pos_crm/member_register.html', {'form': form, 'merchant': merchant})


def member_lookup_ajax(request):
    """GET /pos/members/lookup/?phone=&merchant="""
    denied = _check_perm(request.user, 'pos.manage_members')
    if denied:
        return JsonResponse({'found': False, 'error': 'Forbidden'}, status=403)
    phone = request.GET.get('phone', '').strip()
    merchant_id = request.GET.get('merchant')
    if not phone or not merchant_id:
        return JsonResponse({'found': False})
    from apps.pos_config.models import MerchantPOSConfig
    merchant = get_object_or_404(MerchantPOSConfig, pk=merchant_id)
    member = lookup_member(phone, merchant)
    if member:
        return JsonResponse({
            'found': True,
            'member_id': member.member_id,
            'name': member.name,
            'phone': member.phone,
            'tier': member.tier,
            'points': member.points,
            'pk': member.pk,
        })
    return JsonResponse({'found': False})
