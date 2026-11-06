import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tutorias", "0007_clave_temporal_y_registro_seguridad")]
    operations = [
        migrations.CreateModel(
            name="AvisoReserva",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "proximo_intento",
                    models.DateTimeField(db_index=True, default=django.utils.timezone.now),
                ),
                ("bloqueo_hasta", models.DateTimeField(blank=True, null=True)),
                ("intentos", models.PositiveIntegerField(default=0)),
                ("correo_enviado", models.BooleanField(default=False)),
                ("telegram_enviado", models.BooleanField(default=False)),
                ("completado", models.DateTimeField(blank=True, null=True)),
                ("ultimo_error", models.CharField(blank=True, max_length=100)),
                (
                    "reserva",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="aviso",
                        to="tutorias.reservalaboratorio",
                    ),
                ),
            ],
        ),
    ]
