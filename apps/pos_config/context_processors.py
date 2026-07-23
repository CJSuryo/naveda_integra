def pos_nav_context(request):
    """Expose the user's first accessible merchant/store to the sidebar.

    Swallows errors on purpose: a context processor that raises breaks every
    page, and the navigation degrades gracefully without these keys.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    try:
        from pos_config.access import accessible_merchant_qs
        from pos_config.models import StorePOSConfig
        merchant = (
            accessible_merchant_qs(request.user)
            .select_related('entitas_bisnis_lv2__entitas_bisnis')
            .first()
        )
        if not merchant:
            return {}
        store = (
            StorePOSConfig.objects
            .filter(merchant_config=merchant, is_active=True)
            .select_related('entitas_bisnis_lv3')
            .first()
        )
        return {
            'pos_merchant': merchant,
            'pos_first_store': store,
            'pos_cashier_url': '/sales/pos/',
        }
    except Exception:
        return {}
