# apps/pos_crm/urls.py
from django.urls import path
from apps.pos_crm import views

urlpatterns = [
    path('members/', views.member_list, name='pos_member_list'),
    path('members/register/', views.member_register, name='pos_member_register'),
    path('members/lookup/', views.member_lookup_ajax, name='pos_member_lookup'),
    path('members/<int:pk>/', views.member_detail, name='pos_member_detail'),
]
