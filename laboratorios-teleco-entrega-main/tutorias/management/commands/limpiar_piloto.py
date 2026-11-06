from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tutorias.db_lock import escritura_atomica
from tutorias.models import (
    ArchivoMigracion,
    LimiteRecuperacion,
    RegistroSeguridad,
    ReservaLaboratorio,
    VisitaReservas,
)


class Command(BaseCommand):
    help = "Limpia datos personales y reservas locales; conserva un administrador y toda la programación."

    def add_arguments(self, parser):
        parser.add_argument("--administrador", required=True)
        parser.add_argument("--confirmar", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            raise CommandError("Esta limpieza solo se permite en la base local SQLite.")
        admin = User.objects.filter(
            username=options["administrador"], is_superuser=True, is_active=True
        ).first()
        if not admin:
            raise CommandError("No existe ese administrador activo. No se cambió ningún dato.")
        self.stdout.write(
            f"Se conservará: {admin.username}. Usuarios a borrar: {User.objects.exclude(pk=admin.pk).count()}. Reservas: {ReservaLaboratorio.objects.count()}."
        )
        if not options["confirmar"]:
            self.stdout.write("Simulación. Añade --confirmar después de revisar.")
            return
        call_command("respaldar_base", stdout=self.stdout)
        with escritura_atomica():
            ReservaLaboratorio.objects.all().delete()
            VisitaReservas.objects.all().delete()
            ArchivoMigracion.objects.all().delete()
            LimiteRecuperacion.objects.all().delete()
            RegistroSeguridad.objects.all().delete()
            LogEntry.objects.all().delete()
            Session.objects.all().delete()
            User.objects.exclude(pk=admin.pk).delete()
        self.stdout.write(
            self.style.SUCCESS("Limpieza completa. Administrador y programación conservados.")
        )
