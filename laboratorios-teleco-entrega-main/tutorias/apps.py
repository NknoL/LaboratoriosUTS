from django.apps import AppConfig


class TutoriasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tutorias"
    verbose_name = "Reservas de laboratorios"

    def ready(self):
        import tutorias.signals  # noqa: F401
