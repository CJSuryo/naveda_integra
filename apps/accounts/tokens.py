"""Single-use token for the email-verified password-change flow."""
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class PasswordChangeTokenGenerator(PasswordResetTokenGenerator):
    """Token whose hash mixes the user's password hash + last_login + timestamp.

    Consequences:
    - Setting a new password changes the hash → outstanding links stop working
      (single-use by construction).
    - The next login changes last_login → also invalidates outstanding links.
    - Expiry is governed by settings.PASSWORD_RESET_TIMEOUT (900s = 15 min).
    """


password_change_token = PasswordChangeTokenGenerator()
