def pos_nav_context(request):
    if not request.user.is_authenticated:
        return {}
    try:
        from pos_config.models import MerchantPOSConfig, StorePOSConfig
        if request.user.is_superuser or getattr(request.user, 'is_admin', False):
            merchant = MerchantPOSConfig.objects.select_related('entitas_bisnis').first()
        else:
            from apps.accounts.models import UserEntitasBisnis
            ub = (
                UserEntitasBisnis.objects
                .filter(user=request.user)
                .select_related('entitas_bisnis')
                .first()
            )
            if not ub:
                return {}
            merchant = MerchantPOSConfig.objects.filter(
                entitas_bisnis=ub.entitas_bisnis
            ).select_related('entitas_bisnis').first()
        if not merchant:
            return {}
        store = StorePOSConfig.objects.filter(merchant_config=merchant, is_active=True).first()
        return {'pos_merchant': merchant, 'pos_first_store': store, 'pos_cashier_url': '/sales/pos/'}
    except Exception:
        return {}
