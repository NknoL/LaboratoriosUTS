from smtplib import SMTPAuthenticationError, SMTPException

from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError

from tutorias.notificaciones import destinatarios
from tutorias.recovery import recuperacion_habilitada


class Command(BaseCommand):
    help = "Comprueba el correo sin mostrar secretos ni enviar mensajes."

    def add_arguments(self, parser):
        parser.add_argument("--conectar", action="store_true", help="Prueba la autenticacion SMTP.")

    def handle(self, *args, **options):
        self.stdout.write(f"Transporte: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Recuperacion habilitada: {recuperacion_habilitada()}")
        self.stdout.write(f"Destinatarios de avisos: {', '.join(destinatarios()) or 'ninguno'}")
        if settings.EMAIL_BACKEND.endswith(
            ("filebased.EmailBackend", "console.EmailBackend", "locmem.EmailBackend")
        ):
            raise CommandError("Modo de pruebas: NO se entregan correos a Internet.")
        if not options["conectar"]:
            return
        if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
            raise CommandError("La prueba de conexion solo aplica a SMTP.")
        try:
            with get_connection() as connection:
                if connection.connection is None:
                    raise CommandError("No se pudo abrir la conexion SMTP.")
        except SMTPAuthenticationError as error:
            raise CommandError(
                f"SMTP rechazo las credenciales (codigo {error.smtp_code}). "
                "En Gmail usa una contrasena de aplicacion, no la clave de tu cuenta."
            ) from None
        except (SMTPException, OSError, ValueError):
            raise CommandError(
                "No se pudo conectar: revisa host, puerto, TLS y acceso de red."
            ) from None
        self.stdout.write(
            self.style.SUCCESS(
                "SMTP acepto la conexion y las credenciales. No se envio ningun correo."
            )
        )
