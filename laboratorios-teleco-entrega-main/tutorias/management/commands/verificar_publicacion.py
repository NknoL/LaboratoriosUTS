from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.models import User
from django.core.checks import ERROR, WARNING, run_checks
from django.core.management.base import BaseCommand, CommandError

from tutorias.notificaciones import correo_configurado, destinatarios


class Command(BaseCommand):
    help = "Rechaza publicar sin administrador o con claves conocidas de demostración."

    def add_arguments(self, parser):
        parser.add_argument(
            "--produccion",
            action="store_true",
            help="Exige configuracion publica, HTTPS y correo; no envia mensajes.",
        )

    def handle(self, *args, **options):
        if options["produccion"]:
            if not settings.PRODUCTION or settings.DEBUG:
                raise CommandError(
                    "Aun estas en desarrollo. Ejecuta --produccion en el servidor con su archivo de entorno."
                )
            problemas = run_checks(include_deployment_checks=True)
            bloqueantes = [
                p.id
                for p in problemas
                if p.level >= WARNING
                and p.id not in {"security.W005", "security.W021", "models.W036"}
            ]
            if any(p.level >= ERROR for p in problemas) or bloqueantes:
                raise CommandError("Configuracion insegura: " + ", ".join(bloqueantes))
            sitio = urlsplit(settings.SITIO_URL)
            if (
                sitio.scheme != "https"
                or sitio.hostname not in settings.ALLOWED_HOSTS
                or sitio.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise CommandError(
                    "UTS_SITIO_URL debe ser HTTPS y coincidir con el dominio publico permitido."
                )
            if (
                not correo_configurado()
                or not destinatarios()
                or settings.EMAIL_BACKEND.endswith(
                    ("filebased.EmailBackend", "console.EmailBackend", "locmem.EmailBackend")
                )
            ):
                raise CommandError("Falta un transporte de correo real o destinatario de avisos.")
        if not User.objects.filter(is_superuser=True, is_active=True).exists():
            raise CommandError(
                "Importa primero el administrador y la programación desde tu equipo."
            )
        examples = ("Admin12345*", "Coord12345*", "Estudiante12345*")
        for user in User.objects.filter(is_active=True):
            if any(user.check_password(password) for password in examples):
                raise CommandError(
                    "Hay una cuenta con clave de demostración. Ejecuta cambiar_claves_demo y sigue el procedimiento privado."
                )
        self.stdout.write("Comprobaciones de publicación correctas.")
