"""
Nightly database backup management command.

Dumps the PostgreSQL database to a timestamped .dump file. Designed to run
as a cron job on Render (via cron-job service) or any scheduler.

Usage:
    python manage.py backup_db
    python manage.py backup_db --output-dir /tmp/backups
    python manage.py backup_db --keep 14   # keep last 14 days of backups
"""
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger('apps.jurnal')


class Command(BaseCommand):
    help = 'Create a pg_dump backup of the database and prune old backups.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default=os.environ.get('BACKUP_DIR', str(settings.BASE_DIR / 'backups')),
            help='Directory to store backup files (default: $BACKUP_DIR or <project>/backups/).',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=int(os.environ.get('BACKUP_KEEP_DAYS', '7')),
            help='Number of days of backups to keep (default: 7).',
        )

    def handle(self, *args, **options):
        db_config = settings.DATABASES['default']
        engine = db_config.get('ENGINE', '')

        if 'postgresql' not in engine and 'postgis' not in engine:
            raise CommandError(
                f'backup_db only supports PostgreSQL. Current engine: {engine}'
            )

        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'naveda_integra_{timestamp}.dump'
        filepath = output_dir / filename

        # Build pg_dump command
        env = os.environ.copy()
        env['PGPASSWORD'] = db_config.get('PASSWORD', '')

        host = db_config.get('HOST', 'localhost')
        port = str(db_config.get('PORT', '5432'))
        user = db_config.get('USER', 'postgres')
        name = db_config.get('NAME', 'naveda_integra')

        cmd = [
            'pg_dump',
            '-h', host,
            '-p', port,
            '-U', user,
            '-Fc',               # custom format (compressed, restorable)
            '--no-owner',        # portable across users
            '-f', str(filepath),
            name,
        ]

        # For Neon SSL connections
        database_url = os.environ.get('DATABASE_URL', '')
        if 'sslmode=require' in database_url or 'neon.tech' in database_url:
            env['PGSSLMODE'] = 'require'

        self.stdout.write(f'Backing up database "{name}" → {filepath}')
        logger.info('Starting database backup to %s', filepath)

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10-minute timeout
            )
            if result.returncode != 0:
                logger.error('pg_dump failed: %s', result.stderr)
                raise CommandError(f'pg_dump failed:\n{result.stderr}')
        except FileNotFoundError:
            raise CommandError(
                'pg_dump not found. Install PostgreSQL client tools:\n'
                '  Ubuntu/Debian: sudo apt install postgresql-client\n'
                '  macOS:         brew install libpq'
            )

        size_mb = filepath.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f'Backup complete: {filepath} ({size_mb:.1f} MB)'
        ))
        logger.info('Backup complete: %s (%.1f MB)', filepath, size_mb)

        # Prune old backups
        keep_days = options['keep']
        cutoff = datetime.now() - timedelta(days=keep_days)
        pruned = 0
        for old_file in output_dir.glob('naveda_integra_*.dump'):
            if old_file == filepath:
                continue
            # Parse timestamp from filename
            try:
                name_part = old_file.stem.replace('naveda_integra_', '')
                file_date = datetime.strptime(name_part, '%Y%m%d_%H%M%S')
                if file_date < cutoff:
                    old_file.unlink()
                    pruned += 1
                    logger.info('Pruned old backup: %s', old_file.name)
            except ValueError:
                continue

        if pruned:
            self.stdout.write(f'Pruned {pruned} backup(s) older than {keep_days} days.')
