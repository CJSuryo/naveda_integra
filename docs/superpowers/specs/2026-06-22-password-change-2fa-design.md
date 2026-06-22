# Email-Verified Password Change (2FA) — Design Spec

**Date:** 2026-06-22
**Status:** Approved, ready for implementation plan
**App:** `apps/accounts`

## Problem

1. Admin panel for `User` (`/admin/accounts/user/<id>/change/`) crashes with
   `FieldError: 'date_joined' cannot be specified for User model form as it is a
   non-editable field`. The custom `User` model declares
   `date_joined = DateTimeField(auto_now_add=True)` (non-editable), but
   `UserAdmin.fieldsets` lists it as an editable field.
2. The web user-edit form (`UserForm`) exposes a plaintext password field. We want
   passwords changed only through a secure, email-verified flow (own account only)
   or through the Django admin panel (admins only).
3. New requirement: changing a password must be confirmed by clicking an
   encrypted, time-limited link sent to the user's email. After a successful
   change, all of the user's sessions are revoked (logout from all devices) and
   the user must log in again.

## Goals

- Fix the admin `FieldError`.
- Remove password editing from the web `UserForm`.
- Email-verified, own-account-only password change with a 15-minute single-use link.
- On success: revoke ALL sessions for the user (every device, including current),
  then force re-login.
- Professional, branded HTML email with the company logo embedded.

## Non-Goals

- TOTP/authenticator-app 2FA for login (this is 2FA *for the password-change
  action only*).
- Password reset for users who are locked out / not logged in (separate future
  flow). This spec covers an authenticated user changing their own password.
- Changing how admins manage other users' passwords (still via Django admin).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Production email provider | Google **Workspace** SMTP (`smtp.gmail.com`, app password) |
| Require current password before sending link | **Yes** |
| Link lifetime | **15 minutes** |
| Token mechanism | Django `PasswordResetTokenGenerator` subclass (`uidb64 + token`) |
| Logo source | `static/logo white background.png` (white bg) |
| Brand color | `--ni-primary` = `#0054a6` |

## Architecture

### 1. Admin fix — `apps/accounts/admin.py`

Add to `UserAdmin`:
```python
readonly_fields = ('last_login', 'date_joined')
```
`date_joined` (auto_now_add) and `last_login` are non-editable, so they must be
read-only display fields, not form fields. The Django `UserAdmin` password change
link / `set_password` mechanism is retained — admins still change passwords here.

### 2. Web form — `apps/accounts/forms.py`

`UserForm`: remove the `password` field and the `set_password` logic in `save()`.
Fields become `('email', 'name', 'role', 'is_active')`. No password editing via web
CRUD. `RegisterForm` is unchanged (initial password set at registration is fine).

### 3. Token generator — new `apps/accounts/tokens.py`

```python
from django.contrib.auth.tokens import PasswordResetTokenGenerator

class PasswordChangeTokenGenerator(PasswordResetTokenGenerator):
    """Token for the email-verified password-change flow.

    Hash inputs include the user's password hash and last_login, so the token
    becomes invalid (single-use) once the password changes or the user logs in
    again. Expiry governed by settings.PASSWORD_RESET_TIMEOUT (900s)."""
    pass  # default _make_hash_value already mixes password + last_login + timestamp

password_change_token = PasswordChangeTokenGenerator()
```
Single-use is structural: after the password is set, the hash changes → the link
no longer validates. Re-login also changes `last_login` → invalidates outstanding
links.

### 4. Views — `apps/accounts/views.py` (4 endpoints, all `@login_required`, own-account only)

**a. `password_change_request` (GET/POST)** — `password-change/request/`
- GET: render form asking for the user's **current password**.
- POST: verify current password via `request.user.check_password(...)`. On
  mismatch → form error. On success:
  - `uid = urlsafe_base64_encode(force_bytes(user.pk))`
  - `token = password_change_token.make_token(user)`
  - build absolute link with `request.build_absolute_uri(reverse(...))`
  - send branded email (see §5)
  - render "check your email" confirmation page.

**b. `password_change_confirm` (GET/POST)** — `password-change/<uidb64>/<token>/`
- Decode `uidb64` → user. If decode fails, user not found, **user != request.user**,
  or `password_change_token.check_token(user, token)` is False → render
  "invalid or expired link" page (HTTP 200, no form).
- GET (valid token): render `SetPasswordForm(user)`.
- POST (valid token): validate `SetPasswordForm` (runs `AUTH_PASSWORD_VALIDATORS`).
  On success:
  1. `form.save()` (sets new password).
  2. **Revoke all sessions** for this user (see §6).
  3. `logout(request)` for the current request.
  4. Redirect to `login` with a success message ("Kata sandi diubah. Silakan
     masuk kembali.").

Authorization note: both endpoints enforce `user.pk == request.user.pk`. An admin
cannot drive another user's change through this flow; that stays in the admin panel.

### 5. Email — `templates/accounts/email/password_change.{html,txt}`

Sent with `EmailMultiAlternatives`; logo embedded inline via CID so it renders
without "show images".

```python
from email.mime.image import MIMEImage
from django.conf import settings

msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
msg.attach_alternative(html_body, 'text/html')
logo_path = settings.BASE_DIR / 'static' / 'logo white background.png'
with open(logo_path, 'rb') as f:
    img = MIMEImage(f.read())
img.add_header('Content-ID', '<logo>')
img.add_header('Content-Disposition', 'inline', filename='naveda-logo.png')
msg.attach(img)
msg.send()
```

HTML email is **table-based** with **inline CSS** (email clients strip `<style>`
and external CSS — this is the sanctioned exception to the project's
no-inline-styles rule). Structure:
- White header band, centered `<img src="cid:logo" width="160" alt="Naveda Finance">`.
- Greeting `Halo {{ user.name }},` + Indonesian body explaining the request.
- CTA button background `#0054a6`, text "Ubah Kata Sandi", links to the confirm URL.
- "Tautan berlaku 15 menit." + "Abaikan email ini jika Anda tidak meminta perubahan."
- Plaintext fallback copy of the URL.
- Footer: `© Naveda Finance`.

`.txt` part: plain greeting, the raw URL, the 15-minute notice, the ignore notice.

Logo: use existing `static/logo white background.png` (read server-side at send
time; the space in the filename is fine since it's a filesystem path, not a URL).
Recommend a transparent-bg PNG ~200px wide later, but the white-bg file works on
the white header band now.

### 6. Revoke all sessions — helper in `apps/accounts/views.py` (or `utils`)

Sessions are DB-backed (default engine, no `SESSION_ENGINE` override).
```python
from django.contrib.sessions.models import Session
from django.utils import timezone

def _revoke_all_sessions(user):
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.get_decoded().get('_auth_user_id') == str(user.pk):
            session.delete()
```
Deletes every active session for the user → logged out everywhere. Acceptable
O(active-sessions) scan for current app scale.

### 7. Settings — `naveda_integra/settings/base.py`

```python
PASSWORD_RESET_TIMEOUT = 900  # 15 min — governs the password-change link

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Naveda Finance <noreply@navedafinance.com>')
EMAIL_BACKEND  = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST     = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT     = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS  = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
```
Default backend = console → local dev prints the email/link to the terminal; no
SMTP needed locally.

### 8. URLs — `apps/accounts/urls.py`

```python
path('password-change/request/', views.password_change_request, name='password_change_request'),
path('password-change/<uidb64>/<token>/', views.password_change_confirm, name='password_change_confirm'),
```

### 9. Templates (new, under `templates/accounts/`)

- `password_change_request.html` — current-password form.
- `password_change_sent.html` — "check your email" page.
- `password_change_confirm.html` — `SetPasswordForm` page.
- `password_change_invalid.html` — invalid/expired link page.
- `email/password_change.html` + `email/password_change.txt`.

All page templates extend the app's base and use existing CSS classes
(`ni-input`, `ni-btn--primary`, etc.) — no inline styles except inside the email.

### 10. "Change Password" entry point

On `templates/accounts/user_form.html` (edit view), show a "Ubah Kata Sandi" button
linking to `password_change_request` **only when** `user_obj.pk == request.user.pk`.

## Deployment / Config Changes

### Pip / requirements
None. Everything used is built into Django (`core.mail`, auth tokens, sessions).

### Local
No changes required — console email backend prints the link to the runserver
terminal. To test real SMTP locally, set `EMAIL_BACKEND=...smtp.EmailBackend` plus
the Gmail vars below in `.env`.

### Production — Render.com
Add env vars (dashboard, and to `render.yaml` with `sync: false`):
```
EMAIL_BACKEND       = django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST_USER     = <workspace-mailbox>@navedafinance.com
EMAIL_HOST_PASSWORD = <16-char Gmail App Password>
DEFAULT_FROM_EMAIL  = Naveda Finance <<workspace-mailbox>@navedafinance.com>
```

### Gmail / Google Workspace one-time setup (outside code)
1. Enable 2-Step Verification on the Google account (required for app passwords).
2. Generate an **App Password** → 16-char value → `EMAIL_HOST_PASSWORD`.
3. DNS on `navedafinance.com` for deliverability:
   - SPF TXT: `v=spf1 include:_spf.google.com ~all`
   - DKIM: enable in Workspace Admin, add the generated TXT record.
   - DMARC TXT: `v=DMARC1; p=none; rua=mailto:dmarc@navedafinance.com`
4. Use Google **Workspace** (not consumer Gmail) so `From:` keeps the
   `@navedafinance.com` address; consumer Gmail rewrites `From` and caps ~500/day.

### Migrations
None — no model changes. Token is stateless; sessions already DB-backed.

## Security Considerations

- Current-password re-entry blocks a hijacked live session from starting a takeover.
- Email click is the second factor (proves control of the inbox).
- 15-min single-use link limits exposure; token auto-invalidates on password change
  and on next login.
- All sessions revoked on success → an attacker's stolen session dies immediately.
- Endpoints are own-account-only; admins use the admin panel for others.
- New-password runs through `AUTH_PASSWORD_VALIDATORS`.

## Testing

- Admin: `/admin/accounts/user/<id>/change/` loads without `FieldError`;
  `date_joined`/`last_login` shown read-only.
- `UserForm` no longer renders/accepts a password field.
- Request flow: wrong current password → error; correct → email sent (console).
- Token: tampered/expired/reused token → invalid-link page.
- Confirm flow: weak password rejected; valid password sets, revokes all sessions,
  logs out, redirects to login.
- Session revocation: create 2 sessions for a user, complete change, assert both
  `Session` rows gone.
- Authorization: user A cannot open user B's confirm link (pk mismatch → invalid).

## Files Touched

- `apps/accounts/admin.py` — `readonly_fields`
- `apps/accounts/forms.py` — drop password from `UserForm`
- `apps/accounts/tokens.py` — new token generator
- `apps/accounts/views.py` — 4 views + session-revoke helper
- `apps/accounts/urls.py` — 2 routes
- `templates/accounts/password_change_*.html` (4)
- `templates/accounts/email/password_change.{html,txt}`
- `templates/accounts/user_form.html` — conditional button
- `naveda_integra/settings/base.py` — email + `PASSWORD_RESET_TIMEOUT`
- `render.yaml` — email env var placeholders
- `static/logo white background.png` — existing logo, embedded in email
