from django.urls import path
from apps.pos_promotions import views

urlpatterns = [
    path('promotions/campaigns/', views.campaign_list, name='pos_campaign_list'),
    path('promotions/campaigns/new/', views.campaign_form, name='pos_campaign_create'),
    path('promotions/campaigns/<int:pk>/', views.campaign_form, name='pos_campaign_edit'),
    path('promotions/campaigns/<int:campaign_pk>/vouchers/', views.voucher_list, name='pos_voucher_list'),
    path('promotions/campaigns/<int:campaign_pk>/vouchers/generate/', views.voucher_generate, name='pos_voucher_generate'),
    path('promotions/apply-voucher/', views.apply_voucher_ajax, name='pos_apply_voucher'),
]
