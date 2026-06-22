from django.contrib.sessions.models import Session
from django.test import TestCase

from apps.accounts.sessions import revoke_all_sessions
from tests.accounts.factories import make_user


class RevokeAllSessionsTests(TestCase):
    def test_revokes_only_target_users_sessions(self):
        alice = make_user(email='alice@example.com')
        bob = make_user(email='bob@example.com')

        # Two logged-in sessions for alice (two clients), one for bob.
        c1, c2, c3 = self.client_class(), self.client_class(), self.client_class()
        c1.force_login(alice)
        c2.force_login(alice)
        c3.force_login(bob)
        self.assertEqual(Session.objects.count(), 3)

        revoke_all_sessions(alice)

        # Bob's session survives; alice's are gone.
        remaining = [s.get_decoded().get('_auth_user_id') for s in Session.objects.all()]
        self.assertEqual(remaining, [str(bob.pk)])
