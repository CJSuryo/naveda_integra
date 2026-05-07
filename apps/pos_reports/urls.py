from django.urls import path
from apps.pos_reports import views

urlpatterns = [
    path('reports/', views.dashboard, name='pos_reports_dashboard'),
    path('reports/daily/', views.daily_report, name='pos_reports_daily'),
    path('reports/top-products/', views.top_products_report, name='pos_reports_top_products'),
    path('reports/payments/', views.payment_breakdown_report, name='pos_reports_payments'),
    path('reports/laba-rugi/', views.laba_rugi_report, name='pos_reports_laba_rugi'),
    path('reports/snapshot/', views.snapshot_trigger, name='pos_reports_snapshot'),
]
