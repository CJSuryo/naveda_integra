"""naveda_integra URL Configuration."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('entitas-bisnis/', include('apps.entitas_bisnis.urls')),
    path('master-data/', include('apps.master_data.urls')),
    path('jurnal/', include('apps.jurnal.urls')),
    path('purchase/', include('apps.purchase.urls')),
    path('utang/', include('apps.utang.urls')),
    path('sales/', include('apps.sales.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('aset-tetap/', include('apps.aset_tetap.urls')),
    path('aset-lainnya/', include('apps.aset_lainnya.urls')),
    path('ekuitas/', include('apps.ekuitas.urls')),
    path('manufacturing/', include('apps.manufacturing.urls')),
    path('pos/', include('pos_config.urls', namespace='pos_config')),
    path('pos/catalog/', include('pos_catalog.urls', namespace='pos_catalog')),
    path('pos/', include('pos_orders.urls', namespace='pos_orders')),
    path('pos/', include('apps.pos_crm.urls')),
    path('pos/', include('apps.pos_promotions.urls')),
    path('pos/', include('apps.pos_reports.urls')),
    path('piutang/', include('apps.piutang.urls', namespace='piutang')),
    path('pendapatan/', include('apps.pendapatan.urls', namespace='pendapatan')),
    path('pajak/', include('apps.pajak.urls', namespace='pajak')),
    path('dashboard/', include('apps.dashboard.urls', namespace='dashboard')),
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('', include('apps.accounts.urls_home')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
