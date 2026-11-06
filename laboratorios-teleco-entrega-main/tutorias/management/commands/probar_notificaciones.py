from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from tutorias.models import ReservaLaboratorio
from tutorias.notificaciones import (
    correo_configurado,
    destinatarios,
    enviar_aviso_solicitud,
    enviar_telegram,
    telegram_configurado,
)


class Command(BaseCommand):
    help = (
        "Envía un aviso de prueba a coordinación por los canales configurados (correo y Telegram)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reserva", type=int, help="Reenvía el aviso real de esta solicitud.")

    def handle(self, *args, **options):
        para = destinatarios()
        self.stdout.write(
            f"Correo configurado: {'sí' if correo_configurado() else 'no'} ({settings.EMAIL_BACKEND})"
        )
        self.stdout.write(
            f"Destinatarios: {', '.join(para) or 'ninguno (define UTS_NOTIFICAR_CORREOS o el correo del coordinador)'}"
        )
        self.stdout.write(f"Telegram configurado: {'sí' if telegram_configurado() else 'no'}")
        if options["reserva"]:
            self.stdout.write(str(enviar_aviso_solicitud(options["reserva"])))
            return
        if correo_configurado() and para:
            try:
                enviados = send_mail(
                    "Prueba de avisos · Laboratorios UTS",
                    "Si recibes este correo, el transporte de avisos esta funcionando. "
                    "El aviso dira: Nueva reserva de laboratorio. "
                    "Ingresa al aplicativo para revisar la solicitud.",
                    settings.DEFAULT_FROM_EMAIL,
                    para,
                )
                if enviados != 1:
                    raise OSError
            except Exception:
                raise CommandError(
                    "El proveedor no acepto el correo. Ejecuta diagnosticar_correo --conectar."
                ) from None
            if settings.EMAIL_BACKEND.endswith("filebased.EmailBackend"):
                self.stdout.write(
                    f"Modo local: el correo quedó como archivo en {settings.EMAIL_FILE_PATH}"
                )
            elif settings.EMAIL_BACKEND.endswith(("console.EmailBackend", "locmem.EmailBackend")):
                self.stdout.write("Simulacion local: no se entrego a Internet.")
            else:
                self.stdout.write(
                    self.style.SUCCESS("Proveedor acepto el correo. Comprueba la bandeja y spam.")
                )
        else:
            raise CommandError("Falta configurar remitente, transporte o destinatario.")
        if telegram_configurado():
            enviar_telegram("✅ Prueba de avisos de Laboratorios UTS")
            self.stdout.write(self.style.SUCCESS("Mensaje de Telegram enviado."))
        ultima = ReservaLaboratorio.objects.order_by("-pk").first()
        if ultima:
            self.stdout.write(
                f"Para ver el formato real: manage.py probar_notificaciones --reserva {ultima.pk}"
            )
