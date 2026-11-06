"""Copia los datos de SQLite o PostgreSQL a la base actual (MySQL) y los valida.

Uso (la base MySQL debe estar vacía y migrada):
    DATABASE_URL=mysql://...           -> destino
    DATABASE_URL_ORIGEN=sqlite:///db.sqlite3 -> origen local (solo lectura)
    # Tambien admite un origen PostgreSQL con postgres://...
    python manage.py migrate --noinput
    python manage.py trasladar_base              # simulación: comprobaciones previas
    python manage.py trasladar_base --confirmar  # copia + validación
    python manage.py trasladar_base --solo-validar
"""

import hashlib
import json
import unicodedata
from collections import defaultdict
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DEFAULT_DB_ALIAS, connections, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder

ORIGEN = "origen"
# Se regeneran con `migrate` en el destino (contenttypes/permisos) o no conviene copiarlos (sesiones).
EXCLUIDOS = ("contenttypes", "auth.permission", "sessions")
# Filas que las migraciones 0002/0003 siembran en una base nueva; se reemplazan por las del origen.
SEMBRADOS = (
    "tutorias.HorarioClase",
    "tutorias.FranjaLaboratorio",
    "tutorias.Laboratorio",
    "tutorias.Materia",
    "tutorias.PeriodoAcademico",
    "tutorias.ArchivoMigracion",
)


def modelos_trasladables():
    result = []
    for model in apps.get_models():
        label = model._meta.label_lower
        if model._meta.proxy or not model._meta.managed:
            continue
        if label.split(".")[0] in EXCLUIDOS or label in EXCLUIDOS:
            continue
        result.append(model)
    return result


def clave_mysql(value):
    """Aproxima la comparación de utf8mb4_unicode_ci: sin mayúsculas, sin tildes y sin espacios finales."""
    if not isinstance(value, str):
        return value
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )
    return sin_tildes.casefold().rstrip(" ")


def conjuntos_unicos(model):
    opts = model._meta
    for field in opts.concrete_fields:
        if field.unique and not field.primary_key:
            yield (field.attname,), None
    for fields in opts.unique_together:
        yield tuple(opts.get_field(f).attname for f in fields), None
    for constraint in opts.constraints:
        if isinstance(constraint, models.UniqueConstraint) and constraint.fields:
            yield tuple(opts.get_field(f).attname for f in constraint.fields), constraint.condition


def normalizar(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt_timezone.utc)
        return value.isoformat()
    if isinstance(value, dict):
        return {k: normalizar(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [normalizar(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True, cls=DjangoJSONEncoder))
    return value


def huella(model, alias):
    """Cantidad de filas y hash SHA-256 del contenido serializado, ordenado por pk."""
    digest = hashlib.sha256()
    total = 0
    queryset = model._default_manager.using(alias).order_by("pk")
    for chunk_start in range(0, queryset.count(), 500):
        chunk = list(queryset[chunk_start : chunk_start + 500])
        for row in serializers.serialize("python", chunk, use_natural_foreign_keys=True):
            fila = {"pk": row["pk"], "fields": normalizar(row["fields"])}
            digest.update(json.dumps(fila, sort_keys=True, cls=DjangoJSONEncoder).encode("utf-8"))
            total += 1
    return total, digest.hexdigest()


class Command(BaseCommand):
    help = "Traslada los datos de DATABASE_URL_ORIGEN (SQLite o PostgreSQL) a MySQL y valida el resultado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Ejecuta la copia. Sin esta opción solo comprueba.",
        )
        parser.add_argument(
            "--solo-validar", action="store_true", help="Compara origen y destino sin copiar nada."
        )

    def handle(self, *args, **options):
        if ORIGEN not in settings.DATABASES:
            raise CommandError(
                "Define DATABASE_URL_ORIGEN; para SQLite local usa sqlite:///db.sqlite3."
            )
        destino = connections[DEFAULT_DB_ALIAS]
        origen = connections[ORIGEN]
        if destino.vendor != "mysql":
            raise CommandError("El destino (DATABASE_URL) debe ser MySQL/MariaDB.")
        self.stdout.write(
            f"Origen: {origen.vendor} · {origen.settings_dict['NAME']}  →  Destino: {destino.vendor} · {destino.settings_dict['NAME']}"
        )

        if options["solo_validar"]:
            self.validar()
            return

        self.comprobar_migraciones()
        self.comprobar_colisiones()
        from django.contrib.auth.models import User

        from tutorias.models import ReservaLaboratorio

        if (
            User.objects.using(DEFAULT_DB_ALIAS).exists()
            or ReservaLaboratorio.objects.using(DEFAULT_DB_ALIAS).exists()
        ):
            raise CommandError(
                "El destino ya tiene usuarios o reservas. Usa una base MySQL nueva; no se modificó nada."
            )
        resumen = {
            m._meta.label: m._default_manager.using(ORIGEN).count() for m in modelos_trasladables()
        }
        for label, count in resumen.items():
            self.stdout.write(f"  {label:<35} {count:>7} filas")
        if not options["confirmar"]:
            self.stdout.write(
                self.style.WARNING("Simulación correcta. Añade --confirmar para copiar los datos.")
            )
            return

        with TemporaryDirectory() as directory:
            # XML y no JSON: DjangoJSONEncoder recorta las fechas a milisegundos y se
            # perderían los microsegundos de todas las marcas de tiempo.
            fixture = Path(directory) / "traslado.xml"
            with transaction.atomic(using=ORIGEN):
                call_command(
                    "dumpdata",
                    exclude=list(EXCLUIDOS),
                    natural_foreign=True,
                    database=ORIGEN,
                    format="xml",
                    output=str(fixture),
                    verbosity=0,
                )
            with transaction.atomic(using=DEFAULT_DB_ALIAS):
                for label in SEMBRADOS:
                    apps.get_model(label)._default_manager.using(DEFAULT_DB_ALIAS).all().delete()
                call_command("loaddata", str(fixture), database=DEFAULT_DB_ALIAS, verbosity=0)
        self.stdout.write(self.style.SUCCESS("Datos copiados. Validando..."))
        self.validar()

    def comprobar_migraciones(self):
        executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError(
                "El destino tiene migraciones pendientes. Ejecuta primero: python manage.py migrate"
            )
        aplicadas_origen = set(MigrationRecorder(connections[ORIGEN]).applied_migrations())
        aplicadas_destino = set(
            MigrationRecorder(connections[DEFAULT_DB_ALIAS]).applied_migrations()
        )
        faltantes = sorted(aplicadas_origen - aplicadas_destino)
        if faltantes:
            raise CommandError(
                f"El origen tiene migraciones que este código no conoce: {faltantes}"
            )
        if ("tutorias", "0005_correo_unico") not in aplicadas_origen:
            raise CommandError(
                "Actualiza primero la base de origen: aplica sus migraciones pendientes."
            )

    def comprobar_colisiones(self):
        """MySQL compara texto sin distinguir mayúsculas ni tildes: detecta valores únicos que chocarían."""
        problemas = []
        for model in modelos_trasladables():
            for campos, condicion in conjuntos_unicos(model):
                queryset = model._default_manager.using(ORIGEN).all()
                if condicion is not None:
                    queryset = queryset.filter(condicion)
                vistos = defaultdict(list)
                for fila in queryset.values_list("pk", *campos):
                    valores = fila[1:]
                    if any(v is None for v in valores):
                        continue
                    vistos[tuple(clave_mysql(v) for v in valores)].append(fila[0])
                for clave, pks in vistos.items():
                    if len(pks) > 1:
                        problemas.append(
                            f"{model._meta.label}{list(campos)} = {clave!r}: filas {pks}"
                        )
        from django.contrib.auth.models import User

        correos = defaultdict(list)
        for pk, email in User.objects.using(ORIGEN).values_list("pk", "email"):
            if email.strip():
                correos[clave_mysql(email.strip())].append(pk)
        problemas += [
            f"auth.User[email] = {c!r}: filas {p}" for c, p in correos.items() if len(p) > 1
        ]
        if problemas:
            detalle = "\n".join("  - " + p for p in problemas)
            raise CommandError(
                "Valores que en MySQL (sin distinguir mayúsculas/tildes) serían duplicados. "
                f"Corrígelos en el origen antes de trasladar; no se modificó nada:\n{detalle}"
            )
        self.stdout.write("Sin colisiones de valores únicos por mayúsculas, tildes o espacios.")

    def validar(self):
        errores = 0
        for model in modelos_trasladables():
            n_origen, h_origen = huella(model, ORIGEN)
            n_destino, h_destino = huella(model, DEFAULT_DB_ALIAS)
            ok = n_origen == n_destino and h_origen == h_destino
            errores += not ok
            estado = self.style.SUCCESS("OK") if ok else self.style.ERROR("DIFERENTE")
            self.stdout.write(
                f"  {model._meta.label:<35} origen={n_origen:>7} destino={n_destino:>7}  {estado}"
            )
        if errores:
            raise CommandError(f"{errores} tabla(s) no coinciden. No publiques hasta revisar.")
        self.stdout.write(
            self.style.SUCCESS(
                "Validación completa: filas y contenido idénticos en todas las tablas."
            )
        )
