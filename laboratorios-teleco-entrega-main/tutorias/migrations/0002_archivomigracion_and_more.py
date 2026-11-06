import json

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import migrations, models


def archivar_sistema_anterior(apps, schema_editor):
    alias = schema_editor.connection.alias
    archivo = apps.get_model("tutorias", "ArchivoMigracion")
    for nombre in ("Tutoria", "ReservaTutoria", "DocenteMateria"):
        filas = list(apps.get_model("tutorias", nombre).objects.using(alias).values())
        archivo.objects.using(alias).create(
            origen=nombre, datos=json.loads(json.dumps(filas, cls=DjangoJSONEncoder))
        )
    perfil = apps.get_model("tutorias", "PerfilUsuario")
    user = apps.get_model("auth", "User")
    antiguos = perfil.objects.using(alias).filter(rol="DOCENTE")
    user.objects.using(alias).filter(pk__in=antiguos.values("usuario_id")).update(
        is_active=False, is_staff=False, is_superuser=False
    )
    antiguos.update(rol="ESTUDIANTE")
    perfil.objects.using(alias).filter(rol="ADMIN").update(rol="COORDINADOR")


class Migration(migrations.Migration):
    dependencies = [
        ("tutorias", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArchivoMigracion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("origen", models.CharField(max_length=80)),
                ("datos", models.JSONField()),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.RunPython(archivar_sistema_anterior),
        migrations.AlterUniqueTogether(
            name="reservatutoria",
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name="reservatutoria",
            name="estudiante",
        ),
        migrations.RemoveField(
            model_name="reservatutoria",
            name="tutoria",
        ),
        migrations.RemoveField(
            model_name="tutoria",
            name="docente",
        ),
        migrations.RemoveField(
            model_name="tutoria",
            name="laboratorio",
        ),
        migrations.RemoveField(
            model_name="tutoria",
            name="materia",
        ),
        migrations.RemoveField(
            model_name="tutoria",
            name="periodo",
        ),
        migrations.AlterModelOptions(
            name="horarioclase",
            options={
                "ordering": ["dia_semana", "hora_inicio", "laboratorio__nombre"],
                "verbose_name": "clase fija",
                "verbose_name_plural": "clases fijas",
            },
        ),
        migrations.AlterModelOptions(
            name="laboratorio",
            options={"ordering": ["nombre"]},
        ),
        migrations.AlterModelOptions(
            name="materia",
            options={"ordering": ["semestre", "nombre"]},
        ),
        migrations.AlterModelOptions(
            name="perfilusuario",
            options={"verbose_name": "perfil", "verbose_name_plural": "perfiles"},
        ),
        migrations.AlterModelOptions(
            name="periodoacademico",
            options={
                "ordering": ["-fecha_inicio"],
                "verbose_name": "semestre académico",
                "verbose_name_plural": "semestres académicos",
            },
        ),
        migrations.AddField(
            model_name="laboratorio",
            name="materias",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"activa": True, "tecnica": True},
                related_name="laboratorios",
                to="tutorias.materia",
            ),
        ),
        migrations.AddField(
            model_name="materia",
            name="tecnica",
            field=models.BooleanField(default=True, verbose_name="materia técnica"),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="cedula",
            field=models.CharField(
                blank=True,
                max_length=15,
                null=True,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[0-9]{6,15}$", "Ingresa de 6 a 15 dígitos."
                    )
                ],
                verbose_name="cédula",
            ),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="notas_revision",
            field=models.TextField(blank=True, verbose_name="observaciones internas"),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="programa",
            field=models.CharField(
                blank=True, choices=[("TEC", "Tecnología"), ("ING", "Ingeniería")], max_length=3
            ),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="revisado_el",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="revisado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="revision",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("VALIDADA", "Validada"),
                    ("REVISAR", "Por revisar"),
                ],
                default="PENDIENTE",
                max_length=12,
                verbose_name="revisión de matrícula",
            ),
        ),
        migrations.AddField(
            model_name="perfilusuario",
            name="semestre",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(10),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="horarioclase",
            name="dia_semana",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "Lunes"),
                    (2, "Martes"),
                    (3, "Miércoles"),
                    (4, "Jueves"),
                    (5, "Viernes"),
                    (6, "Sábado"),
                ],
                verbose_name="día",
            ),
        ),
        migrations.AlterField(
            model_name="horarioclase",
            name="hora_fin",
            field=models.TimeField(verbose_name="hora de fin"),
        ),
        migrations.AlterField(
            model_name="horarioclase",
            name="hora_inicio",
            field=models.TimeField(verbose_name="hora de inicio"),
        ),
        migrations.AlterField(
            model_name="horarioclase",
            name="laboratorio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="tutorias.laboratorio"
            ),
        ),
        migrations.AlterField(
            model_name="horarioclase",
            name="periodo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="tutorias.periodoacademico"
            ),
        ),
        migrations.AlterField(
            model_name="laboratorio",
            name="capacidad",
            field=models.PositiveSmallIntegerField(
                default=20, validators=[django.core.validators.MinValueValidator(1)]
            ),
        ),
        migrations.AlterField(
            model_name="laboratorio",
            name="ubicacion",
            field=models.CharField(blank=True, max_length=120, verbose_name="ubicación"),
        ),
        migrations.AlterField(
            model_name="materia",
            name="nivel",
            field=models.CharField(
                choices=[("TEC", "Tecnología"), ("ING", "Ingeniería")], max_length=3
            ),
        ),
        migrations.AlterField(
            model_name="materia",
            name="semestre",
            field=models.PositiveSmallIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(10),
                ]
            ),
        ),
        migrations.AlterField(
            model_name="perfilusuario",
            name="rol",
            field=models.CharField(
                choices=[("COORDINADOR", "Coordinador"), ("ESTUDIANTE", "Estudiante")],
                default="ESTUDIANTE",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="FranjaLaboratorio",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "dia_semana",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "Lunes"),
                            (2, "Martes"),
                            (3, "Miércoles"),
                            (4, "Jueves"),
                            (5, "Viernes"),
                            (6, "Sábado"),
                        ],
                        verbose_name="día",
                    ),
                ),
                ("hora_inicio", models.TimeField(verbose_name="hora de inicio")),
                ("hora_fin", models.TimeField(verbose_name="hora de fin")),
                (
                    "capacidad",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Vacío: usa la capacidad del laboratorio.",
                        null=True,
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                ("activa", models.BooleanField(default=True)),
                (
                    "laboratorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="franjas",
                        to="tutorias.laboratorio",
                    ),
                ),
                (
                    "periodo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="tutorias.periodoacademico"
                    ),
                ),
            ],
            options={
                "verbose_name": "franja de reserva",
                "verbose_name_plural": "franjas de reserva",
                "ordering": ["dia_semana", "hora_inicio", "laboratorio__nombre"],
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ReservaLaboratorio",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("fecha", models.DateField(db_index=True)),
                ("hora_inicio", models.TimeField()),
                ("hora_fin", models.TimeField()),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("activa", models.BooleanField(default=True)),
                ("cancelada_el", models.DateTimeField(blank=True, null=True)),
                (
                    "estudiante",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reservas_laboratorio",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "franja",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reservas",
                        to="tutorias.franjalaboratorio",
                    ),
                ),
                (
                    "laboratorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="tutorias.laboratorio"
                    ),
                ),
                (
                    "materia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="tutorias.materia"
                    ),
                ),
            ],
            options={
                "ordering": ["fecha", "hora_inicio"],
            },
        ),
        migrations.CreateModel(
            name="VisitaReservas",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("fecha", models.DateField(default=django.utils.timezone.localdate)),
                (
                    "estudiante",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="DocenteMateria",
        ),
        migrations.DeleteModel(
            name="ReservaTutoria",
        ),
        migrations.DeleteModel(
            name="Tutoria",
        ),
        migrations.AddConstraint(
            model_name="franjalaboratorio",
            constraint=models.CheckConstraint(
                condition=models.Q(("hora_fin__gt", models.F("hora_inicio"))),
                name="franja_horas_validas",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservalaboratorio",
            constraint=models.UniqueConstraint(
                condition=models.Q(("activa", True)),
                fields=("franja", "fecha", "estudiante"),
                name="reserva_activa_unica",
            ),
        ),
        migrations.AddConstraint(
            model_name="reservalaboratorio",
            constraint=models.CheckConstraint(
                condition=models.Q(("hora_fin__gt", models.F("hora_inicio"))),
                name="reserva_horas_validas",
            ),
        ),
        migrations.AddConstraint(
            model_name="visitareservas",
            constraint=models.UniqueConstraint(
                fields=("estudiante", "fecha"), name="visita_diaria_unica"
            ),
        ),
    ]
