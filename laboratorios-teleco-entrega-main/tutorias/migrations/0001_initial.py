import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Laboratorio",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=80, unique=True)),
                ("ubicacion", models.CharField(blank=True, max_length=120)),
                ("capacidad", models.PositiveSmallIntegerField(default=20)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "laboratorio",
                "verbose_name_plural": "laboratorios",
                "ordering": ["nombre"],
            },
        ),
        migrations.CreateModel(
            name="Materia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("codigo", models.CharField(max_length=20, unique=True)),
                ("nombre", models.CharField(max_length=120)),
                (
                    "nivel",
                    models.CharField(
                        choices=[("TEC", "Tecnologia"), ("ING", "Ingenieria")], max_length=3
                    ),
                ),
                ("semestre", models.PositiveSmallIntegerField()),
                ("linea", models.CharField(blank=True, max_length=80)),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "materia",
                "verbose_name_plural": "materias",
                "ordering": ["semestre", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="PeriodoAcademico",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=80, unique=True)),
                ("fecha_inicio", models.DateField()),
                ("fecha_fin", models.DateField()),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "periodo academico",
                "verbose_name_plural": "periodos academicos",
                "ordering": ["-fecha_inicio"],
            },
        ),
        migrations.CreateModel(
            name="PerfilUsuario",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "rol",
                    models.CharField(
                        choices=[
                            ("ADMIN", "Administrador"),
                            ("DOCENTE", "Docente"),
                            ("ESTUDIANTE", "Estudiante"),
                        ],
                        default="ESTUDIANTE",
                        max_length=20,
                    ),
                ),
                (
                    "usuario",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="perfil",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "perfil de usuario",
                "verbose_name_plural": "perfiles de usuario",
            },
        ),
        migrations.CreateModel(
            name="HorarioClase",
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
                            (3, "Miercoles"),
                            (4, "Jueves"),
                            (5, "Viernes"),
                            (6, "Sabado"),
                        ]
                    ),
                ),
                ("hora_inicio", models.TimeField()),
                ("hora_fin", models.TimeField()),
                ("grupo", models.CharField(blank=True, max_length=30)),
                (
                    "laboratorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="horarios_clase",
                        to="tutorias.laboratorio",
                    ),
                ),
                (
                    "materia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="horarios_clase",
                        to="tutorias.materia",
                    ),
                ),
                (
                    "periodo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="horarios_clase",
                        to="tutorias.periodoacademico",
                    ),
                ),
            ],
            options={
                "verbose_name": "horario fijo de clase",
                "verbose_name_plural": "horarios fijos de clase",
                "ordering": ["dia_semana", "hora_inicio", "laboratorio__nombre"],
            },
        ),
        migrations.CreateModel(
            name="Tutoria",
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
                            (3, "Miercoles"),
                            (4, "Jueves"),
                            (5, "Viernes"),
                            (6, "Sabado"),
                        ]
                    ),
                ),
                ("hora_inicio", models.TimeField()),
                ("hora_fin", models.TimeField()),
                ("cupos", models.PositiveSmallIntegerField(default=20)),
                ("activo", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                (
                    "docente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tutorias_publicadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "laboratorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tutorias",
                        to="tutorias.laboratorio",
                    ),
                ),
                (
                    "materia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tutorias",
                        to="tutorias.materia",
                    ),
                ),
                (
                    "periodo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tutorias",
                        to="tutorias.periodoacademico",
                    ),
                ),
            ],
            options={
                "verbose_name": "tutoria",
                "verbose_name_plural": "tutorias",
                "ordering": ["dia_semana", "hora_inicio", "materia__nombre"],
            },
        ),
        migrations.CreateModel(
            name="DocenteMateria",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "docente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="materias_asignadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "materia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="docentes_asignados",
                        to="tutorias.materia",
                    ),
                ),
            ],
            options={
                "verbose_name": "materia asignada a docente",
                "verbose_name_plural": "materias asignadas a docentes",
                "ordering": ["docente__last_name", "docente__first_name", "materia__nombre"],
                "unique_together": {("docente", "materia")},
            },
        ),
        migrations.CreateModel(
            name="ReservaTutoria",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("creada", models.DateTimeField(auto_now_add=True)),
                ("activa", models.BooleanField(default=True)),
                (
                    "estudiante",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservas_tutoria",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tutoria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reservas",
                        to="tutorias.tutoria",
                    ),
                ),
            ],
            options={
                "verbose_name": "reserva de tutoria",
                "verbose_name_plural": "reservas de tutorias",
                "ordering": ["-creada"],
                "unique_together": {("tutoria", "estudiante")},
            },
        ),
    ]
