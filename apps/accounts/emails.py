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
