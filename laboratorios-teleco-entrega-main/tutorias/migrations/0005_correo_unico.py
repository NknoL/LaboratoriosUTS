from django.db import migrations

# PostgreSQL y SQLite: índice único parcial sobre una expresión.
INDICE_PARCIAL = "CREATE UNIQUE INDEX uts_user_email_unique ON auth_user (LOWER(TRIM(email))) WHERE TRIM(email) <> ''"
BORRAR_INDICE_PARCIAL = "DROP INDEX uts_user_email_unique"

# MySQL/MariaDB no admiten índices parciales (WHERE). Equivalente portable: una columna
# generada que vale NULL para correos vacíos (los NULL no chocan en un índice único)
# y el correo normalizado en los demás casos. Django no conoce la columna y no la escribe.
MYSQL_COLUMNA = (
    "ALTER TABLE auth_user ADD COLUMN email_normalizado VARCHAR(254) "
    "GENERATED ALWAYS AS (NULLIF(LOWER(TRIM(email)), '')) STORED"
)
MYSQL_INDICE = "CREATE UNIQUE INDEX uts_user_email_unique ON auth_user (email_normalizado)"
MYSQL_BORRAR = (
    "DROP INDEX uts_user_email_unique ON auth_user",
    "ALTER TABLE auth_user DROP COLUMN email_normalizado",
)


def comprobar_duplicados(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT LOWER(TRIM(email)) AS correo, COUNT(*) AS total FROM auth_user "
            "WHERE TRIM(email) <> '' GROUP BY LOWER(TRIM(email)) HAVING COUNT(*) > 1) AS duplicados"
        )
        if cursor.fetchone()[0]:
            raise RuntimeError(
                "Hay correos duplicados. Resuelve las cuentas duplicadas antes de aplicar esta migración; no se han borrado datos."
            )


def crear_indice(apps, schema_editor):
    comprobar_duplicados(schema_editor)
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute(MYSQL_COLUMNA)
        schema_editor.execute(MYSQL_INDICE)
    else:
        schema_editor.execute(INDICE_PARCIAL)


def borrar_indice(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        for sql in MYSQL_BORRAR:
            schema_editor.execute(sql)
    else:
        schema_editor.execute(BORRAR_INDICE_PARCIAL)


class Migration(migrations.Migration):
    dependencies = [("tutorias", "0004_limiterecuperacion_reservalaboratorio_decidida_el_and_more")]
    operations = [
        # User es el modelo estándar de Django. El índice protege también escrituras fuera del formulario.
        migrations.RunPython(crear_indice, borrar_indice, atomic=False),
    ]
