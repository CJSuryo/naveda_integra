from django.urls import path

from . import views, webhooks

app_name = 'pos_aggregator'

urlpatterns = [
    # ── Wizard (authenticated) ──────────────────────────────────────────────
    path('lv2/<int:lv2_pk>/channels/', views.channel_list, name='channel_list'),
    path('lv2/<int:lv2_pk>/channels/connect/', views.channel_connect, name='channel_connect'),

    path('channel/<int:pk>/', views.wizard, name='wizard'),
    path('channel/<int:pk>/secrets/', views.save_secrets, name='save_secrets'),
    path('channel/<int:pk>/settings/', views.save_settings, name='save_settings'),
    path('channel/<int:pk>/prerequisites/', views.confirm_prerequisites, name='confirm_prerequisites'),
    path('channel/<int:pk>/connect/', views.begin_connect, name='begin_connect'),
    path('channel/<int:pk>/webhooks/', views.register_webhooks, name='register_webhooks'),
    path('channel/<int:pk>/outlets/', views.outlet_picker, name='outlet_picker'),
    path('channel/<int:pk>/branch/<int:store_pk>/link/', views.link_branch, name='link_branch'),
    path('channel/<int:pk>/branch/<int:store_pk>/activate/', views.activate_branch, name='activate_branch'),
    path('channel/<int:pk>/link/<int:link_pk>/unlink/', views.unlink_branch, name='unlink_branch'),
    path('channel/<int:pk>/menu/', views.sync_menus, name='sync_menus'),
    path(
        'channel/<int:pk>/branch-link/<int:store_link_pk>/pull-menu/',
        views.pull_menu, name='pull_menu',
    ),
    path('channel/<int:pk>/checks/', views.run_checks, name='run_checks'),
    path('channel/<int:pk>/go-live/', views.go_live, name='go_live'),
    path('channel/<int:pk>/disconnect/', views.disconnect, name='disconnect'),
    path('channel/<int:pk>/log/', views.webhook_log, name='webhook_log'),

    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),

    # ── Order board ─────────────────────────────────────────────────────────
    path('branch/<int:store_pk>/orders/', views.order_board, name='order_board'),
    path('order/<int:order_pk>/', views.order_detail, name='order_detail'),
    path('order/<int:order_pk>/ready/', views.mark_order_ready, name='mark_order_ready'),
    path('order/<int:order_pk>/repost/', views.repost_order, name='repost_order'),

    # ── Public callbacks (signature-authenticated, no session) ──────────────
    path('webhook/<str:aggregator>/<int:credential_id>/', webhooks.receive, name='webhook'),
    path(
        'webhook/grab/<int:credential_id>/activation/',
        webhooks.grab_activation_callback, name='grab_activation',
    ),
    path(
        'webhook/grab/<int:credential_id>/menu/<int:store_link_id>/',
        webhooks.grab_menu_pull, name='grab_menu_pull',
    ),
]
