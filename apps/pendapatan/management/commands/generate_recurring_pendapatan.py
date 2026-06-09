from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate pendapatan headers from active recurring templates due today.'

    def handle(self, *args, **options):
        from apps.pendapatan.models import RecurringTemplate
        from apps.pendapatan.services import generate_from_recurring
        from django.contrib.auth import get_user_model

        User = get_user_model()
        today = timezone.localdate()

        system_user = User.objects.filter(is_superuser=True).first()

        templates = RecurringTemplate.objects.filter(
            is_active=True,
            tanggal_berikutnya__lte=today,
        ).filter(
            models.Q(tanggal_selesai__isnull=True) |
            models.Q(tanggal_berikutnya__lte=models.F('tanggal_selesai'))
        )

        generated = 0
        confirmed = 0
        errors = 0

        for template in templates:
            try:
                header = generate_from_recurring(template, user=system_user)
                generated += 1
                if header.status == 'confirmed':
                    confirmed += 1
            except Exception as e:
                errors += 1
                self.stderr.write(f'Error template {template.pk} ({template.nama}): {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Generated: {generated}, Confirmed: {confirmed}, Errors: {errors}'
            )
        )
