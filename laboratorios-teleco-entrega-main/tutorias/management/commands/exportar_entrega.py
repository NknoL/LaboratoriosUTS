import hashlib
import os
import shutil
import subprocess
import tempfile
from datetime import timezone as datetime_timezone
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

TABLAS_DATOS = (
    "django_migrations",
    "django_content_type",
    "auth_permission",
    "tutorias_periodoacademico",
    "tutorias_materia",
    "tutorias_laboratorio",
    "tutorias_laboratorio_materias",
    "tutorias_horarioclase",
    "tutorias_franjalaboratorio",
)
CLAVES_DEMO = ("Admin12345*", "Coord12345*", "Estudiante12345*")


def citar_configuracion(value):
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + value.replace("\n", "\\n").replace("\r", "\\r") + '"'


class Command(BaseCommand):
    help = "Exporta esquema, programacion y solo admin a un SQL privado, sin modificar el origen."

    def add_arguments(self, parser):
        parser.add_argument("--cliente", help="Ruta al cliente mariadb-dump o mysqldump.")
        parser.add_argument(
            "--confirmar-copia-admin",
            action="store_true",
            help="Confirma que la copia incluye el hash de admin y solo se compartira de forma privada.",
        )

    def handle(self, *args, **options):
        if not options["confirmar_copia_admin"]:
            raise CommandError("La copia contiene un hash privado; usa --confirmar-copia-admin.")
        if connection.vendor != "mysql":
            raise CommandError("La entrega SQL requiere MySQL/MariaDB.")
        try:
            admin = User.objects.get(username="admin", is_superuser=True, is_active=True)
        except User.DoesNotExist as error:
            raise CommandError("No existe el administrador activo llamado admin.") from error
        if not admin.has_usable_password() or any(admin.check_password(p) for p in CLAVES_DEMO):
            raise CommandError(
                "Cambia primero la clave de admin en tu terminal: manage.py changepassword admin."
            )
        cliente = options["cliente"] or shutil.which("mariadb-dump") or shutil.which("mysqldump")
        if not cliente or not Path(cliente).is_file():
            raise CommandError("Indica --cliente con la ruta de mariadb-dump o mysqldump.")
        existentes = set(connection.introspection.table_names())
        tablas = {
            model._meta.db_table
            for model in apps.get_models(include_auto_created=True)
            if model._meta.managed
        } | {"django_migrations"}
        if not tablas.issubset(existentes) or not set(TABLAS_DATOS).issubset(tablas):
            raise CommandError("Faltan tablas. Revisa las migraciones antes de exportar.")
        config = settings.DATABASES["default"]
        folder = settings.BASE_DIR / "base_datos"
        folder.mkdir(exist_ok=True)
        salida = folder / "laboratorios_inicial.sql"
        parcial = folder / "laboratorios_inicial.sql.tmp"
        try:
            with tempfile.TemporaryDirectory(prefix="uts-entrega-") as temporal:
                cnf = Path(temporal) / "cliente.cnf"
                descriptor = os.open(cnf, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
                    archivo.write("[client]\n")
                    valores = {
                        "host": config.get("HOST") or "localhost",
                        "port": config.get("PORT") or 3306,
                        "user": config["USER"],
                        "password": config.get("PASSWORD", ""),
                    }
                    ca = config.get("OPTIONS", {}).get("ssl", {}).get("ca")
                    if ca:
                        valores["ssl-ca"] = ca
                    for key, value in valores.items():
                        archivo.write(f"{key}={citar_configuracion(value)}\n")
                base = [
                    str(cliente),
                    f"--defaults-extra-file={cnf}",
                    "--single-transaction",
                    "--quick",
                    "--skip-lock-tables",
                    "--skip-add-locks",
                    "--no-tablespaces",
                    "--skip-triggers",
                    "--skip-comments",
                    "--hex-blob",
                    "--default-character-set=utf8mb4",
                ]
                with parcial.open("wb") as output:
                    output.write(
                        b"-- ENTREGA PRIVADA: incluye hash de admin. Importar solo en base vacia.\n"
                    )
                    for modo, nombres in (
                        ("--no-data", sorted(tablas)),
                        ("--no-create-info", TABLAS_DATOS),
                    ):
                        resultado = subprocess.run(
                            base + [modo, "--", config["NAME"], *nombres],
                            stdout=output,
                            stderr=subprocess.PIPE,
                            timeout=300,
                            check=False,
                        )
                        if resultado.returncode:
                            raise CommandError("No se completo el SQL. Revisa cliente y permisos.")
                        output.write(b"\n")
                    self.escribir_admin(output, admin)
            if not User.objects.filter(pk=admin.pk, password=admin.password).exists():
                raise CommandError("La clave cambio durante la exportacion. Vuelve a intentarlo.")
            parcial.replace(salida)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CommandError(
                "No se completo la exportacion; no se modifico la base original."
            ) from error
        finally:
            parcial.unlink(missing_ok=True)
        suma = hashlib.sha256(salida.read_bytes()).hexdigest()
        salida.with_suffix(".sql.sha256").write_text(
            f"{suma}  base_datos/{salida.name}\n", encoding="ascii"
        )
        self.stdout.write(
            "SQL de entrega creado; origen intacto. Revisar restauracion antes de subir."
        )
        self.stdout.write(
            "Solo admin; sin contactos, sesiones, reservas ni historiales personales."
        )

    def escribir_admin(self, output, admin):
        fecha = admin.date_joined
        if timezone.is_aware(fecha):
            fecha = timezone.make_naive(fecha, datetime_timezone.utc)
        # El conector SQL escapa los valores. No se copian contactos ni datos del perfil original.
        with connection.connection.cursor() as cursor:
            consultas = (
                (
                    "INSERT INTO auth_user "
                    "(id,password,last_login,is_superuser,username,first_name,last_name,email,"
                    "is_staff,is_active,date_joined) VALUES (%s,%s,NULL,1,%s,'','','',1,1,%s)",
                    (admin.pk, admin.password, admin.username, fecha),
                ),
                (
                    "INSERT INTO tutorias_perfilusuario "
                    "(usuario_id,rol,cedula,programa,semestre,revision,notas_revision,revisado_por_id,"
                    "revisado_el,debe_cambiar_clave,clave_temporal_expira) "
                    "VALUES (%s,'COORDINADOR',NULL,'',NULL,'PENDIENTE','',NULL,NULL,1,NULL)",
                    (admin.pk,),
                ),
            )
            for sql, parametros in consultas:
                output.write((cursor.mogrify(sql, parametros) + ";\n").encode("utf-8"))
