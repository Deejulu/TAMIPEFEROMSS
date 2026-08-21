from django.apps import AppConfig


class FarmManagementConfig(AppConfig):
    name = 'farm_management'

    def ready(self):
        import farm_management.signals  # noqa: F401
