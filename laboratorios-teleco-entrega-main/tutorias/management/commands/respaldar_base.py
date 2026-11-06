import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Respalda SQLite o MySQL/MariaDB sin incluir claves en los argumentos del proceso."

    def add_arguments(self, parser):
        parser.add_argument("--cliente", help="Ruta a mariadb-dump o mysqldump.")

    def handle(self, *args, **options):
        folder = settings.BASE_DIR / "respaldos"
        folder.mkdir(exist_ok=True, mode=0o700)
        if connection.vendor == "mysql":
            self.respaldar_mysql(folder, options["cliente"])
            return
        if connection.vendor != "sqlite":
            raise CommandError("Este comando admite SQLite y MySQL/MariaDB.")
        source = Path(settings.DATABASES["default"]["NAME"])
        if not source.exists():
            self.stdout.write("No existe una base que respaldar.")
            return
        target = folder / f"laboratorios-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3"
        with sqlite3.connect(source) as origin, sqlite3.connect(target) as backup:
            origin.backup(backup)
        self.stdout.write(self.style.SUCCESS(f"Respaldo: {target}"))

    def respaldar_mysql(self, folder, cliente):
        cliente = cliente or shutil.which("mariadb-dump") or shutil.which("mysqldump")
        if not cliente or not Path(cliente).is_file():
            raise CommandError("Indica --cliente con la ruta de mariadb-dump o mysqldump.")
        config = settings.DATABASES["default"]

        def citar(value):
            value = str(value).replace("\\", "\\\\").replace('"', '\\"')
            return '"' + value.replace("\n", "\\n").replace("\r", "\\r") + '"'

        target = folder / f"laboratorios-{datetime.now():%Y%m%d-%H%M%S-%f}.sql"
        parcial = target.with_suffix(".sql.part")
        try:
            with tempfile.TemporaryDirectory(prefix="laboratorios-backup-") as temporal:
                credenciales = Path(temporal) / "cliente.cnf"
                descriptor = os.open(credenciales, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
                    archivo.write("[client]\n")
                    for key, value in {
                        "host": config.get("HOST") or "localhost",
                        "port": config.get("PORT") or 3306,
                        "user": config["USER"],
                        "password": config.get("PASSWORD", ""),
                    }.items():
                        archivo.write(f"{key}={citar(value)}\n")
                    ca = config.get("OPTIONS", {}).get("ssl", {}).get("ca")
                    if ca:
                        archivo.write(f"ssl-ca={citar(ca)}\n")
                # El archivo parcial privado nunca se entrega como copia terminada.
                descriptor = os.open(parcial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(descriptor)
                resultado = subprocess.run(
                    [
                        str(cliente),
                        f"--defaults-extra-file={credenciales}",
                        "--single-transaction",
                        "--quick",
                        "--skip-lock-tables",
                        "--no-tablespaces",
                        "--triggers",
                        "--hex-blob",
                        "--default-character-set=utf8mb4",
                        f"--result-file={parcial}",
                        "--",
                        config["NAME"],
                    ],
                    capture_output=True,
                    timeout=300,
                    check=False,
                )
                if resultado.returncode or not parcial.stat().st_size:
                    raise CommandError(
                        "No se completo el respaldo. Revisa cliente, conexion y permisos; no se guardo una copia valida."
                    )
            parcial.replace(target)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CommandError(
                "No se pudo ejecutar el respaldo; revisa ruta, permisos y disponibilidad del servidor."
            ) from error
        finally:
            parcial.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Respaldo SQL completo: {target}"))
        self.stdout.write(
            "Contiene datos privados. Verifica la restauracion antes de depender de esta copia."
        )
