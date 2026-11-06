from django.db import migrations

# La restricción reserva_activa_unica de models.py es un índice único PARCIAL
# (WHERE activa). PostgreSQL y SQLite ya lo tienen desde la migración 0002;
# MySQL/MariaDB no admiten índices parciales y Django lo omite en silencio.
# Equivalente: columna generada = 1 si la reserva está activa y NULL si no;
# como los NULL no chocan en un índice único, solo se limita la reserva activa.
COLUMNA = (
    "ALTER TABLE tutorias_reservalaboratorio ADD COLUMN activa_unica TINYINT UNSIGNED "
    "GENERATED ALWAYS AS (IF(activa, 1, NULL)) STORED"
)
INDICE = (
    "CREATE UNIQUE INDEX reserva_activa_unica ON tutorias_reservalaboratorio "
    "(franja_id, fecha, estudiante_id, activa_unica)"
)
# InnoDB reutiliza este índice (empieza por franja_id) para la clave foránea de franja y
# descarta el índice propio de la FK; al revertir hay que recrearlo antes de borrar este.
BORRAR = (
    "CREATE INDEX tutorias_reservalaboratorio_franja_id_fk ON tutorias_reservalaboratorio (franja_id)",
    "DROP INDEX reserva_activa_unica ON tutorias_reservalaboratorio",
    "ALTER TABLE tutorias_reservalaboratorio DROP COLUMN activa_unica",
)


def crear(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute(COLUMNA)
        schema_editor.execute(INDICE)


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        for sql in BORRAR:
            schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("tutorias", "0005_correo_unico")]
    operations = [migrations.RunPython(crear, borrar, atomic=False)]
