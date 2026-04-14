"""Management command to sync roles and permissions from TOML config."""
import tomllib
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.accounts.models import Role, NiPermission


class Command(BaseCommand):
    help = 'Sync roles and permissions from config/roles_permissions.toml into the database.'

    def handle(self, *args, **options):
        toml_path = Path(__file__).resolve().parents[4] / 'config' / 'roles_permissions.toml'
        if not toml_path.exists():
            self.stderr.write(self.style.ERROR(f'TOML config not found: {toml_path}'))
            return

        with open(toml_path, 'rb') as f:
            config = tomllib.load(f)

        # Sync permissions
        perm_codes = set()
        for perm_data in config.get('permissions', []):
            code = perm_data['code']
            perm_codes.add(code)
            NiPermission.objects.update_or_create(
                code=code,
                defaults={
                    'name': perm_data['name'],
                    'module': perm_data.get('module', ''),
                },
            )
        self.stdout.write(self.style.SUCCESS(f'Synced {len(perm_codes)} permissions.'))

        # Sync roles
        for role_data in config.get('roles', []):
            Role.objects.update_or_create(
                kode=role_data['code'],
                defaults={
                    'nama': role_data['name'],
                    'deskripsi': role_data.get('description', ''),
                },
            )
        self.stdout.write(self.style.SUCCESS(f'Synced {len(config.get("roles", []))} roles.'))
