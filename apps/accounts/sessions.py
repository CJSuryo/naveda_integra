"""Revoke all active sessions for a user (logout from all devices)."""
from django.contrib.sessions.models import Session
from django.utils import timezone


def revoke_all_sessions(user) -> int:
    """Delete every non-expired session belonging to ``user``.

    Sessions are DB-backed (default engine). Returns the number deleted.
    """
    deleted = 0
    uid = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get('_auth_user_id') == uid:
            session.delete()
            deleted += 1
    return deleted
