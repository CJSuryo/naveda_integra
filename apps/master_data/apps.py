from django.apps import AppConfig

class MasterDataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.master_data'
    label = 'master_data'

    def ready(self):
        import apps.master_data.signals  # noqa: F401
