import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections

from tutorias.notificaciones import procesar_pendientes


class Command(BaseCommand):
    help = "Envia y reintenta avisos guardados. Mantener activo junto al servidor web."

    def add_arguments(self, parser):
        parser.add_argument("--una-vez", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("Procesando avisos; Ctrl+C para detener.")
        try:
            while True:
                close_old_connections()
                try:
                    total = procesar_pendientes()
                    if total:
                        self.stdout.write(f"Avisos procesados: {total}")
                except OperationalError:
                    if options["una_vez"]:
                        raise
                    self.stderr.write("Base de datos no disponible; reintentando.")
                finally:
                    close_old_connections()
                if options["una_vez"]:
                    break
                time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write("Proceso detenido; los avisos pendientes siguen guardados.")
