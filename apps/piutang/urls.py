from django.urls import path
from . import views

app_name = 'piutang'

urlpatterns = [
    path('dashboard/', views.piutang_dashboard, name='dashboard'),
    path('', views.piutang_list, name='list'),
    path('create/', views.piutang_create, name='create'),
    path('<int:pk>/', views.piutang_detail, name='detail'),
    path('<int:pk>/edit/', views.piutang_update, name='update'),
    path('<int:pk>/delete/', views.piutang_delete, name='delete'),
    path('<int:pk>/terima/', views.piutang_terima, name='terima'),
    path('<int:pk>/submit-approval/', views.piutang_submit_approval, name='submit_approval'),
    path('<int:pk>/approve/', views.piutang_approve, name='approve'),
    path('<int:pk>/reject/', views.piutang_reject, name='reject'),
    path('<int:pk>/penerimaan/<int:ppk>/cancel/', views.piutang_penerimaan_cancel, name='penerimaan_cancel'),
    path('<int:pk>/write-off/', views.piutang_write_off, name='write_off'),
    path('<int:pk>/reklasifikasi/', views.piutang_reklasifikasi_post, name='reklasifikasi_post'),
    path('<int:pk>/reklasifikasi/<int:rkl_pk>/reverse/', views.piutang_reklasifikasi_reverse, name='reklasifikasi_reverse'),
    path('<int:pk>/attachments/upload/', views.piutang_attachment_upload, name='attachment_upload'),
    path('<int:pk>/attachments/<int:apk>/delete/', views.piutang_attachment_delete, name='attachment_delete'),
    path('reports/aging/', views.piutang_report_aging, name='report_aging'),
    path('reports/subjek/', views.piutang_report_subjek, name='report_subjek'),
    path('reports/jatuh-tempo/', views.piutang_report_jatuh_tempo, name='report_jatuh_tempo'),
    path('reports/write-off/', views.piutang_report_write_off, name='report_write_off'),
]
