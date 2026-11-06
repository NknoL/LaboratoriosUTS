import json
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tutorias.db_lock import escritura_atomica
from tutorias.models import (
    ArchivoMigracion,
    FranjaLaboratorio,
    HorarioClase,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)

from .exportar_traslado import MODELOS


class Command(BaseCommand):
    help = "Importa el traslado en un destino nuevo. Rechaza bases con usuarios o reservas."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--confirmar", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["archivo"]).resolve()
        if not options["confirmar"]:
            raise CommandError("Revisa el destino y añade --confirmar.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or any(item.get("model") not in MODELOS for item in data):
            raise CommandError("El archivo contiene modelos no permitidos.")
        users = [item for item in data if item["model"] == "auth.user"]
        if (
            len(users) != 1
            or not users[0]["fields"].get("is_superuser")
            or not users[0]["fields"].get("is_active")
        ):
            raise CommandError(
                "Se requiere exactamente un administrador activo en este traslado inicial."
            )
        with escritura_atomica():
            if User.objects.exists() or ReservaLaboratorio.objects.exists():
                raise CommandError(
                    "El destino ya tiene usuarios o reservas. No se sobrescribió nada."
                )
            # Remove only the catalog seeded by migrations in a new destination.
            HorarioClase.objects.all().delete()
            FranjaLaboratorio.objects.all().delete()
            Laboratorio.objects.all().delete()
            Materia.objects.all().delete()
            PeriodoAcademico.objects.all().delete()
            ArchivoMigracion.objects.all().delete()
            call_command("loaddata", str(path), verbosity=0)
        self.stdout.write(
            self.style.SUCCESS(
                "Administrador y programación importados. No vuelvas a importar sobre esta base."
            )
        )
