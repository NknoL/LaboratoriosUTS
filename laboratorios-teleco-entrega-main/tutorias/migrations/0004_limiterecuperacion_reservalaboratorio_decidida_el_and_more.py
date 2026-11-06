import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def conservar_estados(apps, schema_editor):
    reserva = apps.get_model("tutorias", "ReservaLaboratorio")
    reserva.objects.using(schema_editor.connection.alias).filter(activa=True).update(
        estado="CONFIRMADA"
    )
    reserva.objects.using(schema_editor.connection.alias).filter(activa=False).update(
        estado="CANCELADA"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tutorias", "0003_catalogo_laboratorios"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LimiteRecuperacion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("clave", models.CharField(max_length=64)),
                ("ventana", models.BigIntegerField()),
                ("intentos", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.AddField(
            model_name="reservalaboratorio",
            name="decidida_el",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservalaboratorio",
            name="decidida_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="reservalaboratorio",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("CONFIRMADA", "Confirmada"),
                    ("RECHAZADA", "Rechazada"),
                    ("CANCELADA", "Cancelada"),
                ],
                db_index=True,
                default="PENDIENTE",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="reservalaboratorio",
            name="motivo_decision",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.RunPython(conservar_estados, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="reservalaboratorio",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("activa", True), ("estado__in", ["PENDIENTE", "CONFIRMADA"])),
                    models.Q(("activa", False), ("estado__in", ["RECHAZADA", "CANCELADA"])),
                    _connector="OR",
                ),
                name="reserva_estado_coherente",
            ),
        ),
        migrations.AddConstraint(
            model_name="limiterecuperacion",
            constraint=models.UniqueConstraint(
                fields=("clave", "ventana"), name="limite_recuperacion_unico"
            ),
        ),
    ]
