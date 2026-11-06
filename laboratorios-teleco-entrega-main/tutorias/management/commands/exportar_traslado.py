from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

MODELOS = (
    "auth.user",
    "auth.group",
    "tutorias.perfilusuario",
    "tutorias.periodoacademico",
    "tutorias.materia",
    "tutorias.laboratorio",
    "tutorias.horarioclase",
    "tutorias.franjalaboratorio",
)


class Command(BaseCommand):
    help = "Exporta cuentas y programación a un archivo privado, sin sesiones, reservas ni archivos históricos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida", default=str(settings.BASE_DIR / ".private" / "traslado.json")
        )

    def handle(self, *args, **options):
        target = Path(options["salida"]).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        with transaction.atomic(), temporary.open("w", encoding="utf-8") as output:
            call_command(
                "dumpdata", *MODELOS, natural_foreign=True, indent=2, stdout=output, verbosity=0
            )
        temporary.replace(target)
        self.stdout.write(
            f"Exportación privada: {target}. Contiene hashes de contraseña: no subir a GitHub."
        )
