from django.apps import AppConfig


class EnhancerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "enhancer"
    verbose_name = "Photo Enhancer"

    def ready(self):
        # Ensures the background worker pool is created lazily on first use.
        from . import tasks  # noqa: F401
