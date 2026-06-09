from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.pendapatan.deferred_services import recognize_deferred_entry
from apps.pendapatan.models import DeferredRevenueEntry


class Command(BaseCommand):
    help = 'Recognize all pending deferred revenue entries for a given period (YYYY-MM).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--period', type=str, required=True,
            help='Period in YYYY-MM format (e.g. 2026-01)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print entries that would be recognized without saving.',
        )

    def handle(self, *args, **options):
        period_str = options['period']
        try:
            year, month = period_str.split('-')
            period_date = date(int(year), int(month), 1)
        except (ValueError, TypeError):
            raise CommandError(f'Format periode tidak valid: {period_str}. Gunakan YYYY-MM.')

        entries = DeferredRevenueEntry.objects.filter(
            periode=period_date, status='pending',
        ).select_related(
            'schedule__recognition_account', 'schedule__deferred_account',
            'schedule__pendapatan_item__pendapatan_eb__pendapatan_header',
        )

        if not entries.exists():
            self.stdout.write(f'Tidak ada entry pending untuk periode {period_str}.')
            return

        ok = 0
        err = 0
        for entry in entries:
            if options['dry_run']:
                self.stdout.write(
                    f'[DRY-RUN] Entry {entry.pk} — {entry.jumlah} — '
                    f'{entry.schedule.pendapatan_item.pendapatan_eb.pendapatan_header.transaction_id}'
                )
                continue
            try:
                recognize_deferred_entry(entry)
                ok += 1
            except Exception as e:
                self.stderr.write(f'Error entry {entry.pk}: {e}')
                err += 1

        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'Selesai: {ok} diakui, {err} error.'))
