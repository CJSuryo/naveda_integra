"""Emit security response headers not covered by Django's SecurityMiddleware.

Currently sets Permissions-Policy from settings.PERMISSIONS_POLICY. This module
is also the intended home for a Content-Security-Policy header once inline
scripts have been migrated to external files (see security hardening plan).
"""
from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.permissions_policy = getattr(settings, 'PERMISSIONS_POLICY', '')

    def __call__(self, request):
        response = self.get_response(request)
        if self.permissions_policy and 'Permissions-Policy' not in response:
            response['Permissions-Policy'] = self.permissions_policy
        return response
