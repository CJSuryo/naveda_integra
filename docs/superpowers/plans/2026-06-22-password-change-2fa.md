# Email-Verified Password Change (2FA) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user change their own password only after confirming via a 15-minute, single-use, email-verified link; on success revoke all their sessions (logout everywhere) and force re-login. Also fix the admin `FieldError` and remove password editing from the web user form.

**Architecture:** Reuse Django's `PasswordResetTokenGenerator` (subclassed) for a stateless, single-use `uidb64 + token` link (expiry from `PASSWORD_RESET_TIMEOUT=900`). Two own-account-only views: request (re-enter current password → email link) and confirm (validate token → set password → revoke all DB sessions → logout). Branded HTML email with the logo embedded inline via CID.

**Tech Stack:** Django 6, built-in `django.core.mail` (`EmailMultiAlternatives` + `MIMEImage`), `django.contrib.auth.tokens`, DB-backed sessions, Gmail/Workspace SMTP in production.

---

## Conventions

- Run tests from repo root with the project venv active. Test command pattern:
  `python manage.py test tests.accounts -v 2` (settings auto-resolve to
  `naveda_integra.settings.test` via `setup.cfg`).
- During Django tests the email backend is auto-swapped to `locmem`, so
  `django.core.mail.outbox` captures sent messages.
- Tests live under `tests/accounts/` (mirrors `tests/customers/`).
- Commit after each task.

## File Structure

- Create: `apps/accounts/tokens.py` — single-use token generator.
- Create: `apps/accounts/sessions.py` — `revoke_all_sessions(user)` helper.
- Create: `apps/accounts/emails.py` — `send_password_change_email(request, user)`.
- Modify: `apps/accounts/admin.py` — `readonly_fields`.
- Modify: `apps/accounts/forms.py` — drop password from `UserForm`; add `NamedSetPasswordForm`, `CurrentPasswordForm`.
- Modify: `apps/accounts/views.py` — `password_change_request`, `password_change_confirm`.
- Modify: `apps/accounts/urls.py` — 2 routes.
- Modify: `naveda_integra/settings/base.py` — email config + `PASSWORD_RESET_TIMEOUT`.
- Modify: `render.yaml` — email env var placeholders.
- Modify: `templates/accounts/user_form.html` — conditional "Ubah Kata Sandi" button.
- Create: `templates/accounts/password_change_request.html`
- Create: `templates/accounts/password_change_sent.html`
- Create: `templates/accounts/password_change_confirm.html`
- Create: `templates/accounts/password_change_invalid.html`
- Create: `templates/accounts/email/password_change.html`
- Create: `templates/accounts/email/password_change.txt`
- Create: `tests/accounts/__init__.py`, `tests/accounts/factories.py`, and test modules.

---

## Task 0: Test scaffolding

**Files:**
- Create: `tests/accounts/__init__.py`
- Create: `tests/accounts/factories.py`

- [ ] **Step 1: Create the test package init**

Create `tests/accounts/__init__.py` (empty file).

- [ ] **Step 2: Create factories**

Create `tests/accounts/factories.py`:

```python
"""Test factories for the accounts app."""
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(email='user@example.com', name='Test User', password='OldPass123!', **kwargs):
    user = User.objects.create_user(email=email, name=name, password=password, **kwargs)
    return user


def make_admin(email='admin@example.com', name='Admin', password='AdminPass123!'):
    return User.objects.create_superuser(email=email, name=name, password=password)
```

- [ ] **Step 3: Verify the package imports**

Run: `python manage.py test tests.accounts -v 2`
Expected: PASS with "Ran 0 tests" (no test modules yet, package valid).

- [ ] **Step 4: Commit**

```bash
git add tests/accounts/__init__.py tests/accounts/factories.py
git commit -m "test(accounts): add test package scaffolding for password-change flow"
```

---

## Task 1: Fix admin FieldError

**Files:**
- Modify: `apps/accounts/admin.py:27-45`
- Test: `tests/accounts/test_admin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_admin.py`:

```python
from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_admin, make_user


class UserAdminChangeViewTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_change_view_loads_without_fielderror(self):
        target = make_user()
        url = reverse('admin:accounts_user_change', args=[target.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_change_view_shows_readonly_dates(self):
        target = make_user()
        url = reverse('admin:accounts_user_change', args=[target.pk])
        resp = self.client.get(url)
        # date_joined rendered as readonly text, not an editable input named date_joined
        self.assertNotContains(resp, 'name="date_joined"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_admin -v 2`
Expected: FAIL — `FieldError: 'date_joined' cannot be specified for User model form as it is a non-editable field`.

- [ ] **Step 3: Add readonly_fields**

In `apps/accounts/admin.py`, inside `class UserAdmin(DjangoUserAdmin)`, add right after `filter_horizontal = ('ni_permissions',)`:

```python
    readonly_fields = ('last_login', 'date_joined')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_admin -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/admin.py tests/accounts/test_admin.py
git commit -m "fix(accounts): mark last_login/date_joined readonly in UserAdmin"
```

---

## Task 2: Email + token-timeout settings

**Files:**
- Modify: `naveda_integra/settings/base.py` (append after the Channels block, end of file)
- Test: `tests/accounts/test_settings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_settings.py`:

```python
from django.conf import settings
from django.test import TestCase


class EmailSettingsTests(TestCase):
    def test_password_reset_timeout_is_15_minutes(self):
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 900)

    def test_default_from_email_configured(self):
        self.assertTrue(settings.DEFAULT_FROM_EMAIL)

    def test_email_host_is_gmail(self):
        self.assertEqual(settings.EMAIL_HOST, 'smtp.gmail.com')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_settings -v 2`
Expected: FAIL — `PASSWORD_RESET_TIMEOUT` defaults to 259200, and/or `EMAIL_HOST` missing.

- [ ] **Step 3: Add settings**

Append to the end of `naveda_integra/settings/base.py`:

```python
# ── Email + password-change link ─────────────────────────────────────────────
PASSWORD_RESET_TIMEOUT = 900  # 15 min — governs the password-change link

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Naveda Finance <noreply@navedafinance.com>')
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_settings -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add naveda_integra/settings/base.py tests/accounts/test_settings.py
git commit -m "feat(accounts): add email + 15-min PASSWORD_RESET_TIMEOUT settings"
```

---

## Task 3: Single-use token generator

**Files:**
- Create: `apps/accounts/tokens.py`
- Test: `tests/accounts/test_tokens.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_tokens.py`:

```python
from django.test import TestCase

from apps.accounts.tokens import password_change_token
from tests.accounts.factories import make_user


class PasswordChangeTokenTests(TestCase):
    def test_token_validates_for_same_user(self):
        user = make_user()
        token = password_change_token.make_token(user)
        self.assertTrue(password_change_token.check_token(user, token))

    def test_token_invalidated_after_password_change(self):
        user = make_user()
        token = password_change_token.make_token(user)
        user.set_password('BrandNewPass456!')
        user.save()
        self.assertFalse(password_change_token.check_token(user, token))

    def test_bad_token_rejected(self):
        user = make_user()
        self.assertFalse(password_change_token.check_token(user, 'not-a-real-token'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_tokens -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.accounts.tokens'`.

- [ ] **Step 3: Create the token generator**

Create `apps/accounts/tokens.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_tokens -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/tokens.py tests/accounts/test_tokens.py
git commit -m "feat(accounts): add single-use password-change token generator"
```

---

## Task 4: Revoke-all-sessions helper

**Files:**
- Create: `apps/accounts/sessions.py`
- Test: `tests/accounts/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_sessions.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_sessions -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.accounts.sessions'`.

- [ ] **Step 3: Create the helper**

Create `apps/accounts/sessions.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_sessions -v 2`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add apps/accounts/sessions.py tests/accounts/test_sessions.py
git commit -m "feat(accounts): add revoke_all_sessions helper"
```

---

## Task 5: Forms — drop password from UserForm; add flow forms

**Files:**
- Modify: `apps/accounts/forms.py:44-71` (UserForm) and append two new forms
- Test: `tests/accounts/test_forms.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_forms.py`:

```python
from django.test import TestCase

from apps.accounts.forms import UserForm, NamedSetPasswordForm, CurrentPasswordForm
from tests.accounts.factories import make_user


class UserFormTests(TestCase):
    def test_userform_has_no_password_field(self):
        form = UserForm()
        self.assertNotIn('password', form.fields)


class CurrentPasswordFormTests(TestCase):
    def test_accepts_correct_password(self):
        user = make_user(password='OldPass123!')
        form = CurrentPasswordForm(user=user, data={'current_password': 'OldPass123!'})
        self.assertTrue(form.is_valid())

    def test_rejects_wrong_password(self):
        user = make_user(password='OldPass123!')
        form = CurrentPasswordForm(user=user, data={'current_password': 'wrong'})
        self.assertFalse(form.is_valid())


class NamedSetPasswordFormTests(TestCase):
    def test_widgets_have_ni_input_class(self):
        user = make_user()
        form = NamedSetPasswordForm(user)
        self.assertIn('ni-input', form.fields['new_password1'].widget.attrs.get('class', ''))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_forms -v 2`
Expected: FAIL — `ImportError: cannot import name 'NamedSetPasswordForm'`.

- [ ] **Step 3: Edit forms.py**

In `apps/accounts/forms.py`, replace the entire `UserForm` class (lines 44-71) with:

```python
class UserForm(forms.ModelForm):
    """Form for creating/editing users (web CRUD). Password is NOT editable here —
    use the email-verified password-change flow (own account) or the admin panel."""

    class Meta:
        model = User
        fields = ('email', 'name', 'role', 'is_active')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'name': forms.TextInput(attrs={'class': 'ni-input'}),
            'role': forms.Select(attrs={'class': 'ni-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }
```

Then update the imports at the top of `apps/accounts/forms.py`:

```python
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
```

And append to the end of `apps/accounts/forms.py`:

```python
class CurrentPasswordForm(forms.Form):
    """Re-authentication step: user confirms their current password."""
    current_password = forms.CharField(
        label='Kata Sandi Saat Ini',
        widget=forms.PasswordInput(attrs={'class': 'ni-input', 'autofocus': True}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pw = self.cleaned_data['current_password']
        if not self.user or not self.user.check_password(pw):
            raise forms.ValidationError('Kata sandi saat ini salah.')
        return pw


class NamedSetPasswordForm(SetPasswordForm):
    """SetPasswordForm with project input styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('new_password1', 'new_password2'):
            self.fields[name].widget.attrs['class'] = 'ni-input'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_forms -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the existing accounts suite to catch regressions**

Run: `python manage.py test tests.accounts apps.accounts -v 2`
Expected: PASS (no test referenced the removed password field).

- [ ] **Step 6: Commit**

```bash
git add apps/accounts/forms.py tests/accounts/test_forms.py
git commit -m "feat(accounts): remove password from UserForm; add flow forms"
```

---

## Task 6: Branded email sender (CID logo)

**Files:**
- Create: `apps/accounts/emails.py`
- Create: `templates/accounts/email/password_change.html`
- Create: `templates/accounts/email/password_change.txt`
- Test: `tests/accounts/test_emails.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_emails.py`:

```python
from django.core import mail
from django.test import RequestFactory, TestCase

from apps.accounts.emails import send_password_change_email
from tests.accounts.factories import make_user


class SendPasswordChangeEmailTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sends_one_email_to_user(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['target@example.com'])

    def test_email_has_html_alternative_and_inline_logo(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        msg = mail.outbox[0]
        # one text/html alternative
        self.assertTrue(any(ct == 'text/html' for _, ct in msg.alternatives))
        # attachments are MIMEImage objects (Message subclass) with Content-ID <logo>
        has_logo = any(part.get('Content-ID') == '<logo>' for part in msg.attachments)
        self.assertTrue(has_logo)

    def test_email_contains_absolute_link(self):
        user = make_user(email='target@example.com')
        request = self.factory.get('/accounts/password-change/request/')
        send_password_change_email(request, user)
        body = mail.outbox[0].body
        self.assertIn('http', body)
        self.assertIn('/password-change/', body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_emails -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.accounts.emails'`.

- [ ] **Step 3: Create the email sender**

Create `apps/accounts/emails.py`:

```python
"""Send the branded, email-verified password-change message."""
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import password_change_token

LOGO_PATH = settings.BASE_DIR / 'static' / 'logo white background.png'


def build_password_change_link(request, user) -> str:
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_change_token.make_token(user)
    path = reverse('accounts:password_change_confirm', kwargs={'uidb64': uidb64, 'token': token})
    return request.build_absolute_uri(path)


def send_password_change_email(request, user) -> None:
    link = build_password_change_link(request, user)
    context = {'user': user, 'link': link, 'valid_minutes': 15}

    subject = 'Permintaan Ubah Kata Sandi — Naveda Finance'
    text_body = render_to_string('accounts/email/password_change.txt', context)
    html_body = render_to_string('accounts/email/password_change.html', context)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html_body, 'text/html')

    with open(LOGO_PATH, 'rb') as fh:
        logo = MIMEImage(fh.read())
    logo.add_header('Content-ID', '<logo>')
    logo.add_header('Content-Disposition', 'inline', filename='naveda-logo.png')
    msg.attach(logo)

    msg.send()
```

- [ ] **Step 4: Create the plaintext template**

Create `templates/accounts/email/password_change.txt`:

```
Halo {{ user.name }},

Kami menerima permintaan untuk mengubah kata sandi akun Naveda Finance Anda.

Buka tautan berikut untuk menetapkan kata sandi baru:
{{ link }}

Tautan ini berlaku selama {{ valid_minutes }} menit dan hanya dapat digunakan satu kali.

Jika Anda tidak meminta perubahan ini, abaikan email ini — kata sandi Anda tidak akan berubah.

Salam,
Tim Naveda Finance
```

- [ ] **Step 5: Create the HTML template (table layout, inline CSS, CID logo)**

Create `templates/accounts/email/password_change.html`:

```html
{% autoescape on %}<!DOCTYPE html>
<html lang="id">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
          <!-- Header / logo band -->
          <tr>
            <td align="center" style="background-color:#ffffff;padding:28px 24px 12px;border-bottom:1px solid #e2e8f0;">
              <img src="cid:logo" width="160" alt="Naveda Finance" style="display:block;border:0;outline:none;text-decoration:none;height:auto;">
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px 32px 8px;">
              <p style="margin:0 0 16px;font-size:16px;">Halo <strong>{{ user.name }}</strong>,</p>
              <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#334155;">
                Kami menerima permintaan untuk mengubah kata sandi akun Naveda Finance Anda.
                Klik tombol di bawah untuk menetapkan kata sandi baru.
              </p>
            </td>
          </tr>
          <!-- CTA -->
          <tr>
            <td align="center" style="padding:8px 32px 24px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="border-radius:8px;background-color:#0054a6;">
                    <a href="{{ link }}" style="display:inline-block;padding:14px 32px;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:8px;">Ubah Kata Sandi</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Notices -->
          <tr>
            <td style="padding:0 32px 24px;">
              <p style="margin:0 0 12px;font-size:13px;color:#64748b;">
                Tautan ini berlaku selama <strong>{{ valid_minutes }} menit</strong> dan hanya dapat digunakan satu kali.
              </p>
              <p style="margin:0 0 12px;font-size:13px;color:#64748b;">
                Jika Anda tidak meminta perubahan ini, abaikan email ini — kata sandi Anda tidak akan berubah.
              </p>
              <p style="margin:16px 0 0;font-size:12px;color:#94a3b8;word-break:break-all;">
                Jika tombol tidak berfungsi, salin tautan ini ke peramban Anda:<br>{{ link }}
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td align="center" style="background-color:#f8fafc;padding:18px 24px;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:12px;color:#94a3b8;">&copy; Naveda Finance</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>{% endautoescape %}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_emails -v 2`
Expected: PASS (3 tests).

> Note: `test_emails` depends on the `accounts:password_change_confirm` URL name,
> which is added in Task 8. If running this task in isolation before Task 8, the
> `reverse()` call will raise `NoReverseMatch`. Implement Task 7 + 8 URLs together,
> or temporarily expect failure here until Task 8 lands. Recommended: run the full
> `tests.accounts` suite after Task 8.

- [ ] **Step 7: Commit**

```bash
git add apps/accounts/emails.py templates/accounts/email/ tests/accounts/test_emails.py
git commit -m "feat(accounts): branded password-change email with CID logo"
```

---

## Task 7: Request view + URL + templates

**Files:**
- Modify: `apps/accounts/views.py` (add imports + `password_change_request`)
- Modify: `apps/accounts/urls.py`
- Create: `templates/accounts/password_change_request.html`
- Create: `templates/accounts/password_change_sent.html`
- Test: `tests/accounts/test_request_view.py`

- [ ] **Step 1: Add the URL routes (both routes now, confirm view lands in Task 8)**

In `apps/accounts/urls.py`, add inside `urlpatterns` (after the eb-access line):

```python
    # Email-verified password change (own account only)
    path('password-change/request/', views.password_change_request, name='password_change_request'),
    path('password-change/<uidb64>/<token>/', views.password_change_confirm, name='password_change_confirm'),
```

- [ ] **Step 2: Write the failing test**

Create `tests/accounts/test_request_view.py`:

```python
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_user


class PasswordChangeRequestTests(TestCase):
    def setUp(self):
        self.user = make_user(password='OldPass123!')
        self.url = reverse('accounts:password_change_request')

    def test_requires_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_get_renders_current_password_form(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'current_password')

    def test_wrong_current_password_sends_no_email(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {'current_password': 'wrong'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_correct_password_sends_email_and_shows_sent_page(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {'current_password': 'OldPass123!'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resp, 'Periksa email')
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_request_view -v 2`
Expected: FAIL — `AttributeError: module ... has no attribute 'password_change_request'`.

- [ ] **Step 4: Add imports + the view**

At the top of `apps/accounts/views.py`, extend the forms import and add new imports:

```python
from .forms import (
    LoginForm, RegisterForm, UserForm, UserPermissionForm,
    CurrentPasswordForm, NamedSetPasswordForm,
)
from .emails import send_password_change_email
from .sessions import revoke_all_sessions
from .tokens import password_change_token
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
```

Add the view (place after `home_view`, before the `# ── User CRUD` section):

```python
@login_required
def password_change_request(request: HttpRequest) -> HttpResponse:
    """Step 1: user re-enters current password; on success email a change link."""
    form = CurrentPasswordForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        send_password_change_email(request, request.user)
        return render(request, 'accounts/password_change_sent.html', {'email': request.user.email})
    return render(request, 'accounts/password_change_request.html', {'form': form})
```

- [ ] **Step 5: Create the request template**

Create `templates/accounts/password_change_request.html`:

```html
{% extends 'base.html' %}
{% block title %}Ubah Kata Sandi{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Ubah Kata Sandi</h1>
    <p class="ni-page-header__subtitle">Konfirmasi kata sandi Anda saat ini untuk melanjutkan</p>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <p>Demi keamanan, kami akan mengirim tautan ubah kata sandi ke email Anda setelah Anda mengonfirmasi kata sandi saat ini.</p>
    <form method="post">
      {% csrf_token %}
      {% for field in form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}</label>
          {{ field }}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
      {% endfor %}
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Kirim Tautan ke Email</button>
        <a href="{% url 'accounts:user_detail' pk=request.user.pk %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Create the sent-confirmation template**

Create `templates/accounts/password_change_sent.html`:

```html
{% extends 'base.html' %}
{% block title %}Periksa Email Anda{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Periksa email Anda</h1>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <p>Kami telah mengirim tautan ubah kata sandi ke <strong>{{ email }}</strong>.</p>
    <p>Tautan berlaku selama 15 menit dan hanya dapat digunakan satu kali. Setelah kata sandi diubah, Anda akan keluar dari semua perangkat dan harus masuk kembali.</p>
    <p>Tidak menerima email? Periksa folder spam Anda.</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_request_view -v 2`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add apps/accounts/views.py apps/accounts/urls.py templates/accounts/password_change_request.html templates/accounts/password_change_sent.html tests/accounts/test_request_view.py
git commit -m "feat(accounts): password-change request view (re-auth + email link)"
```

---

## Task 8: Confirm view + templates (set password, revoke sessions, logout)

**Files:**
- Modify: `apps/accounts/views.py` (add `password_change_confirm`)
- Create: `templates/accounts/password_change_confirm.html`
- Create: `templates/accounts/password_change_invalid.html`
- Test: `tests/accounts/test_confirm_view.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_confirm_view.py`:

```python
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.tokens import password_change_token
from tests.accounts.factories import make_user


def confirm_url(user, token=None):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = token or password_change_token.make_token(user)
    return reverse('accounts:password_change_confirm', kwargs={'uidb64': uidb64, 'token': token})


class PasswordChangeConfirmTests(TestCase):
    def setUp(self):
        self.user = make_user(password='OldPass123!')

    def test_valid_token_get_renders_set_password_form(self):
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(self.user))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'new_password1')

    def test_invalid_token_renders_invalid_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(self.user, token='bad-token'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tidak valid')

    def test_other_users_link_is_rejected(self):
        other = make_user(email='other@example.com')
        self.client.force_login(self.user)
        resp = self.client.get(confirm_url(other))
        self.assertContains(resp, 'tidak valid')

    def test_post_sets_password_revokes_sessions_and_logs_out(self):
        # Two devices logged in.
        self.client.force_login(self.user)
        other_device = self.client_class()
        other_device.force_login(self.user)
        self.assertEqual(Session.objects.count(), 2)

        resp = self.client.post(confirm_url(self.user), {
            'new_password1': 'BrandNewPass456!',
            'new_password2': 'BrandNewPass456!',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))
        # All sessions revoked (both devices).
        self.assertEqual(Session.objects.count(), 0)

    def test_weak_password_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(confirm_url(self.user), {
            'new_password1': '123',
            'new_password2': '123',
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_confirm_view -v 2`
Expected: FAIL — `AttributeError: ... has no attribute 'password_change_confirm'`.

- [ ] **Step 3: Add the confirm view**

Add to `apps/accounts/views.py` right after `password_change_request`:

```python
def _get_user_from_uidb64(uidb64: str):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


@login_required
def password_change_confirm(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    """Step 2: validate the emailed link, set new password, revoke all sessions."""
    target = _get_user_from_uidb64(uidb64)
    valid = (
        target is not None
        and target.pk == request.user.pk
        and password_change_token.check_token(target, token)
    )
    if not valid:
        return render(request, 'accounts/password_change_invalid.html')

    form = NamedSetPasswordForm(target, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()                       # sets + saves new password
        revoke_all_sessions(target)       # logout from all devices
        logout(request)                   # clear current request session
        dj_messages.success(request, 'Kata sandi berhasil diubah. Silakan masuk kembali.')
        return redirect('login')
    return render(request, 'accounts/password_change_confirm.html', {'form': form})
```

- [ ] **Step 4: Create the confirm template**

Create `templates/accounts/password_change_confirm.html`:

```html
{% extends 'base.html' %}
{% block title %}Tetapkan Kata Sandi Baru{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Tetapkan Kata Sandi Baru</h1>
    <p class="ni-page-header__subtitle">Setelah disimpan, Anda akan keluar dari semua perangkat</p>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <form method="post">
      {% csrf_token %}
      {% for field in form %}
        <div class="ni-form-group">
          <label class="ni-form-label">{{ field.label }}</label>
          {{ field }}
          {% if field.help_text %}<p style="font-size:0.8rem;color:var(--ni-text-muted);margin:4px 0 0;">{{ field.help_text|safe }}</p>{% endif %}
          {% if field.errors %}<div class="ni-form-error">{{ field.errors }}</div>{% endif %}
        </div>
      {% endfor %}
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan Kata Sandi Baru</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create the invalid-link template**

Create `templates/accounts/password_change_invalid.html`:

```html
{% extends 'base.html' %}
{% block title %}Tautan Tidak Valid{% endblock %}
{% block content %}
<div class="ni-page-header">
  <div>
    <h1 class="ni-page-header__title">Tautan tidak valid</h1>
  </div>
</div>
<div class="ni-card ni-animate-fade-in">
  <div class="ni-card__body">
    <p>Tautan ubah kata sandi ini tidak valid, telah kedaluwarsa, atau sudah digunakan.</p>
    <p><a class="ni-btn ni-btn--primary" href="{% url 'accounts:password_change_request' %}">Minta Tautan Baru</a></p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_confirm_view -v 2`
Expected: PASS (5 tests).

- [ ] **Step 7: Run the full accounts suite (includes Task 6 email test now that URLs exist)**

Run: `python manage.py test tests.accounts apps.accounts -v 2`
Expected: PASS (all accounts tests, including `test_emails`).

- [ ] **Step 8: Commit**

```bash
git add apps/accounts/views.py templates/accounts/password_change_confirm.html templates/accounts/password_change_invalid.html tests/accounts/test_confirm_view.py
git commit -m "feat(accounts): password-change confirm view (set pw, revoke sessions, logout)"
```

---

## Task 9: "Ubah Kata Sandi" button on the edit page

**Files:**
- Modify: `templates/accounts/user_form.html`
- Test: `tests/accounts/test_button.py`

- [ ] **Step 1: Write the failing test**

Create `tests/accounts/test_button.py`:

```python
from django.test import TestCase
from django.urls import reverse

from tests.accounts.factories import make_user


class ChangePasswordButtonTests(TestCase):
    def _give_user_update_perm(self, user):
        from apps.accounts.models import NiPermission
        perm, _ = NiPermission.objects.get_or_create(code='user_update', defaults={'name': 'Update User'})
        user.ni_permissions.add(perm)

    def test_button_shown_on_own_edit_page(self):
        user = make_user()
        self._give_user_update_perm(user)
        self.client.force_login(user)
        resp = self.client.get(reverse('accounts:user_update', args=[user.pk]))
        self.assertContains(resp, reverse('accounts:password_change_request'))

    def test_button_hidden_on_other_users_edit_page(self):
        user = make_user(email='editor@example.com')
        other = make_user(email='victim@example.com')
        self._give_user_update_perm(user)
        self.client.force_login(user)
        resp = self.client.get(reverse('accounts:user_update', args=[other.pk]))
        self.assertNotContains(resp, reverse('accounts:password_change_request'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test tests.accounts.test_button -v 2`
Expected: FAIL — page does not contain the password-change URL.

- [ ] **Step 3: Add the conditional button**

In `templates/accounts/user_form.html`, change the `ni-btn-row` block from:

```html
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'accounts:user_list' %}" class="ni-btn ni-btn--secondary">Batal</a>
      </div>
```

to:

```html
      <div class="ni-btn-row" style="margin-top:24px;">
        <button type="submit" class="ni-btn ni-btn--primary">Simpan</button>
        <a href="{% url 'accounts:user_list' %}" class="ni-btn ni-btn--secondary">Batal</a>
        {% if user_obj and user_obj.pk == request.user.pk %}
        <a href="{% url 'accounts:password_change_request' %}" class="ni-btn ni-btn--secondary">Ubah Kata Sandi</a>
        {% endif %}
      </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test tests.accounts.test_button -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add templates/accounts/user_form.html tests/accounts/test_button.py
git commit -m "feat(accounts): show Change Password button only on own edit page"
```

---

## Task 10: Production email env vars in render.yaml

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1: Add email env vars to the web service**

In `render.yaml`, under the web service `envVars:` list (after `CSRF_TRUSTED_ORIGINS`), add:

```yaml
      - key: EMAIL_BACKEND
        value: django.core.mail.backends.smtp.EmailBackend
      - key: EMAIL_HOST_USER
        sync: false          # Google Workspace mailbox, e.g. noreply@navedafinance.com
      - key: EMAIL_HOST_PASSWORD
        sync: false          # 16-char Gmail App Password
      - key: DEFAULT_FROM_EMAIL
        sync: false          # e.g. Naveda Finance <noreply@navedafinance.com>
```

- [ ] **Step 2: Validate YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('render.yaml')); print('OK')"`
Expected: `OK`
(If PyYAML is absent, skip — Render validates on deploy.)

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "chore(deploy): add SMTP email env vars to render.yaml"
```

---

## Final verification

- [ ] **Run the complete accounts test suite**

Run: `python manage.py test tests.accounts apps.accounts -v 2`
Expected: PASS — all tests green.

- [ ] **Manual smoke test (console email backend, local)**

1. `python manage.py runserver`
2. Log in, open your own edit page `/accounts/users/<your-pk>/edit/`.
3. Click "Ubah Kata Sandi" → enter current password → submit.
4. Copy the link printed in the runserver terminal → open it.
5. Set a new password → confirm you are redirected to `/login/` with the success
   message and that re-visiting any page requires logging in again.
6. Verify the old emailed link no longer works (single-use): reopen it → "Tautan
   tidak valid" page.

---

## Post-deploy manual steps (not code — operator checklist)

1. Add the logo file if you want a transparent-background version:
   replace/keep `static/logo white background.png`. Email reads it at send time.
2. Render dashboard → set `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `DEFAULT_FROM_EMAIL` (the `sync: false` vars).
3. Google account: enable 2-Step Verification, generate a 16-char App Password.
4. DNS on navedafinance.com:
   - SPF TXT: `v=spf1 include:_spf.google.com ~all`
   - DKIM: enable in Workspace Admin, add the generated TXT record.
   - DMARC TXT: `v=DMARC1; p=none; rua=mailto:dmarc@navedafinance.com`
5. Use Google Workspace (not consumer Gmail) so `From:` keeps @navedafinance.com.
```
