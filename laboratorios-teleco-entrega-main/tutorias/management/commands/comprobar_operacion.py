import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.utils import timezone

from tutorias.models import AvisoReserva


class Command(BaseCommand):
    help = "Verifica la base y detecta avisos atrasados, sin enviar correos ni mostrar datos personales."

    def add_arguments(self, parser):
        parser.add_argument("--minutos", type=int, default=5, help="Umbral de aviso atrasado.")

    def handle(self, *args, **options):
        if options["minutos"] < 1:
            raise CommandError("El umbral debe ser al menos un minuto.")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            pendientes = AvisoReserva.objects.filter(completado__isnull=True)
            atrasados = pendientes.filter(
                creado__lt=timezone.now() - timedelta(minutes=options["minutos"])
            ).count()
            self.stdout.write(
                json.dumps(
                    {
                        "base": "ok",
                        "avisos_pendientes": pendientes.count(),
                        "avisos_atrasados": atrasados,
                    }
                )
            )
        except DatabaseError:
            raise CommandError(
                "La base no responde o faltan tablas. Revisar conexion y migraciones."
            ) from None
        if atrasados:
            raise CommandError("Hay avisos atrasados. Revisar trabajador y proveedor de correo.")
