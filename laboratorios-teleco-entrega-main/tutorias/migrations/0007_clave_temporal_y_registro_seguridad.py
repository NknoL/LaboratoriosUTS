import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tutorias", "0006_reserva_activa_unica_mysql"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilusuario",
            name="clave_temporal_expira",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="debe_cambiar_clave",
            field=models.BooleanField(default=False, verbose_name="debe cambiar la contraseña"),
        ),
        migrations.CreateModel(
            name="RegistroSeguridad",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("usuario_nombre", models.CharField(max_length=150)),
                (
                    "evento",
                    models.CharField(
                        choices=[
                            (
                                "RECUPERACION_CORREO",
                                "Contraseña restablecida por correo",
                            ),
                            (
                                "CLAVE_TEMPORAL",
                                "Clave temporal generada por coordinación",
                            ),
                            ("CAMBIO_CLAVE", "Contraseña cambiada por el usuario"),
                        ],
                        max_length=24,
                    ),
                ),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "registro de seguridad",
                "verbose_name_plural": "registros de seguridad",
                "ordering": ["-creado"],
            },
        ),
    ]
