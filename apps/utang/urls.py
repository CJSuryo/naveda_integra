from django.urls import path
from . import views

app_name = 'utang'

urlpatterns = [
    path('dashboard/', views.utang_dashboard, name='dashboard'),
    path('', views.utang_list, name='list'),
    path('create/', views.utang_create, name='create'),
    path('<int:pk>/', views.utang_detail, name='detail'),
    path('<int:pk>/edit/', views.utang_update, name='update'),
    path('<int:pk>/delete/', views.utang_delete, name='delete'),
    path('<int:pk>/bayar/', views.utang_pay, name='pay'),
    path('<int:pk>/submit-approval/', views.utang_submit_approval, name='submit_approval'),
    path('<int:pk>/approve/', views.utang_approve, name='approve'),
    path('<int:pk>/reject/', views.utang_reject, name='reject'),
    path('<int:pk>/pembayaran/<int:payment_pk>/cancel/', views.utang_payment_cancel, name='payment_cancel'),
    path('<int:pk>/attachments/upload/', views.utang_attachment_upload, name='attachment_upload'),
    path('<int:pk>/attachments/<int:attachment_pk>/delete/', views.utang_attachment_delete, name='attachment_delete'),
    path('<int:pk>/reklasifikasi/', views.utang_reklasifikasi_post, name='reklasifikasi_post'),
    path('<int:pk>/reklasifikasi/reverse/', views.utang_reklasifikasi_reverse, name='reklasifikasi_reverse'),
    path('reports/subjek/', views.utang_report_subjek, name='report_subjek'),
    path('reports/akun/', views.utang_report_akun, name='report_akun'),
    path('reports/aging/', views.utang_report_aging, name='report_aging'),
    path('reports/jatuh-tempo/', views.utang_report_jatuh_tempo, name='report_jatuh_tempo'),
]
