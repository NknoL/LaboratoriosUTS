from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Count, F, Q
from django.utils import timezone


class RolUsuario(models.TextChoices):
    COORDINADOR = "COORDINADOR", "Coordinador"
    ESTUDIANTE = "ESTUDIANTE", "Estudiante"
    LABORATORISTA = "LABORATORISTA", "Laboratorista"


class NivelMateria(models.TextChoices):
    TECNOLOGIA = "TEC", "Tecnología"
    INGENIERIA = "ING", "Ingeniería"


class RevisionMatricula(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    VALIDADA = "VALIDADA", "Validada"
    REVISAR = "REVISAR", "Por revisar"


class EstadoReserva(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    CANCELADA = "CANCELADA", "Cancelada"


DIA_CHOICES = [
    (1, "Lunes"),
    (2, "Martes"),
    (3, "Miércoles"),
    (4, "Jueves"),
    (5, "Viernes"),
    (6, "Sábado"),
]


def obtener_rol(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return RolUsuario.COORDINADOR
    return getattr(getattr(user, "perfil", None), "rol", None)


def es_coordinador(user):
    return obtener_rol(user) == RolUsuario.COORDINADOR


def es_estudiante(user):
    return obtener_rol(user) == RolUsuario.ESTUDIANTE


def es_laboratorista(user):
    return obtener_rol(user) == RolUsuario.LABORATORISTA


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    rol = models.CharField(max_length=20, choices=RolUsuario.choices, default=RolUsuario.ESTUDIANTE)
    cedula = models.CharField(
        "cédula",
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^[0-9]{6,15}$", "Ingresa de 6 a 15 dígitos.")],
    )
    programa = models.CharField(max_length=3, choices=NivelMateria.choices, blank=True)
    semestre = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    revision = models.CharField(
        "revisión de matrícula",
        max_length=12,
        choices=RevisionMatricula.choices,
        default=RevisionMatricula.PENDIENTE,
    )
    notas_revision = models.TextField("observaciones internas", blank=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revisado_el = models.DateTimeField(null=True, blank=True)
    debe_cambiar_clave = models.BooleanField("debe cambiar la contraseña", default=False)
    clave_temporal_expira = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "perfil"
        verbose_name_plural = "perfiles"

    def clean(self):
        if self.programa and self.semestre:
            if self.programa == NivelMateria.TECNOLOGIA and self.semestre > 6:
                raise ValidationError({"semestre": "Tecnología: semestres 1 a 6."})
            if self.programa == NivelMateria.INGENIERIA and self.semestre < 7:
                raise ValidationError({"semestre": "Ingeniería: semestres 7 a 10."})

    @property
    def completo(self):
        return bool(
            self.cedula
            and self.programa
            and self.semestre
            and self.usuario.email
            and self.usuario.first_name
            and self.usuario.last_name
        )

    def __str__(self):
        return f"{self.usuario.get_full_name() or self.usuario.username} · {self.get_rol_display()}"


class PeriodoAcademico(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "semestre académico"
        verbose_name_plural = "semestres académicos"
        ordering = ["-fecha_inicio"]

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError("La fecha final debe ser posterior a la inicial.")
        if self.pk and self.fecha_inicio and self.fecha_fin:
            fuera = ReservaLaboratorio.objects.filter(
                franja__periodo=self, activa=True, fecha__gte=timezone.localdate()
            ).filter(Q(fecha__lt=self.fecha_inicio) | Q(fecha__gt=self.fecha_fin))
            if fuera.exists():
                raise ValidationError("Hay reservas futuras fuera de las nuevas fechas.")

    def __str__(self):
        return self.nombre


class Materia(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=120)
    nivel = models.CharField(max_length=3, choices=NivelMateria.choices)
    semestre = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    linea = models.CharField(max_length=80, blank=True)
    activa = models.BooleanField(default=True)
    tecnica = models.BooleanField("materia técnica", default=True)

    class Meta:
        ordering = ["semestre", "nombre"]

    def clean(self):
        if self.semestre and self.nivel:
            if self.nivel == NivelMateria.TECNOLOGIA and self.semestre > 6:
                raise ValidationError({"semestre": "Tecnología: semestres 1 a 6."})
            if self.nivel == NivelMateria.INGENIERIA and self.semestre < 7:
                raise ValidationError({"semestre": "Ingeniería: semestres 7 a 10."})

    def __str__(self):
        return f"{self.nombre} · {self.get_nivel_display()} / {self.semestre}"


class Laboratorio(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    ubicacion = models.CharField("ubicación", max_length=120, blank=True)
    capacidad = models.PositiveSmallIntegerField(default=20, validators=[MinValueValidator(1)])
    activo = models.BooleanField(default=True)
    materias = models.ManyToManyField(
        Materia,
        blank=True,
        related_name="laboratorios",
        limit_choices_to={"tecnica": True, "activa": True},
    )

    class Meta:
        ordering = ["nombre"]

    def clean(self):
        if self.pk and self.capacidad:
            if not self.activo and self.reservas_vigentes().exists():
                raise ValidationError(
                    {
                        "activo": "Resuelve los préstamos futuros o en curso antes de retirar el laboratorio."
                    }
                )
            if self.franjas.filter(capacidad__gt=self.capacidad).exists():
                raise ValidationError(
                    {"capacidad": "Una franja tiene una capacidad mayor. Ajústala primero."}
                )
            counts = (
                ReservaLaboratorio.objects.filter(
                    laboratorio=self, activa=True, fecha__gte=timezone.localdate()
                )
                .values("fecha", "hora_inicio", "hora_fin")
                .annotate(total=Count("id"))
            )
            if any(row["total"] > self.capacidad for row in counts):
                raise ValidationError(
                    {"capacidad": "La capacidad no puede ser menor que las reservas existentes."}
                )

    def __str__(self):
        return self.nombre

    def reservas_vigentes(self):
        ahora = timezone.localtime()
        return ReservaLaboratorio.objects.filter(laboratorio=self, activa=True).filter(
            Q(fecha__gt=ahora.date()) | Q(fecha=ahora.date(), hora_fin__gt=ahora.time())
        )


class HorarioBase(models.Model):
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT)
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT)
    dia_semana = models.PositiveSmallIntegerField("día", choices=DIA_CHOICES)
    hora_inicio = models.TimeField("hora de inicio")
    hora_fin = models.TimeField("hora de fin")

    class Meta:
        abstract = True
        ordering = ["dia_semana", "hora_inicio", "laboratorio__nombre"]

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            raise ValidationError("La hora final debe ser posterior a la inicial.")

    def cruces(self, model):
        return model.objects.filter(
            laboratorio_id=self.laboratorio_id,
            dia_semana=self.dia_semana,
            periodo__fecha_inicio__lte=self.periodo.fecha_fin,
            periodo__fecha_fin__gte=self.periodo.fecha_inicio,
            hora_inicio__lt=self.hora_fin,
            hora_fin__gt=self.hora_inicio,
        )

    @property
    def horario_completo(self):
        return all(
            [self.periodo_id, self.laboratorio_id, self.dia_semana, self.hora_inicio, self.hora_fin]
        )

    def __str__(self):
        return f"{self.laboratorio} · {self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}"


class HorarioClase(HorarioBase):
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT, related_name="horarios_clase")
    grupo = models.CharField(max_length=30, blank=True)

    class Meta(HorarioBase.Meta):
        verbose_name = "clase fija"
        verbose_name_plural = "clases fijas"

    def clean(self):
        super().clean()
        if self.horario_completo:
            if self.cruces(HorarioClase).exclude(pk=self.pk).exists():
                raise ValidationError("Ya hay una clase en ese laboratorio y horario.")
            reservations = ReservaLaboratorio.objects.filter(
                laboratorio_id=self.laboratorio_id,
                activa=True,
                fecha__gte=max(timezone.localdate(), self.periodo.fecha_inicio),
                fecha__lte=self.periodo.fecha_fin,
                hora_inicio__lt=self.hora_fin,
                hora_fin__gt=self.hora_inicio,
            )
            if any(r.fecha.isoweekday() == self.dia_semana for r in reservations):
                raise ValidationError(
                    "Esta clase se cruza con solicitudes pendientes o confirmadas. Revisa las reservas primero."
                )
        if (
            self.materia_id
            and self.laboratorio_id
            and not self.laboratorio.materias.filter(pk=self.materia_id, tecnica=True).exists()
        ):
            raise ValidationError({"materia": "La materia debe estar asociada al laboratorio."})


class FranjaLaboratorio(HorarioBase):
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT, related_name="franjas")
    capacidad = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Vacío: usa la capacidad del laboratorio.",
    )
    activa = models.BooleanField(default=True)
    automatica = models.BooleanField(default=False, editable=False)

    class Meta(HorarioBase.Meta):
        verbose_name = "franja de reserva"
        verbose_name_plural = "franjas de reserva"
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_fin__gt=F("hora_inicio")), name="franja_horas_validas"
            )
        ]

    @property
    def limite(self):
        return self.capacidad if self.capacidad is not None else self.laboratorio.capacidad

    def clean(self):
        super().clean()
        if self.laboratorio_id and self.capacidad and self.capacidad > self.laboratorio.capacidad:
            raise ValidationError({"capacidad": "No puede superar la capacidad del laboratorio."})
        if self.horario_completo and self.activa:
            if self.cruces(FranjaLaboratorio).filter(activa=True).exclude(pk=self.pk).exists():
                raise ValidationError("Ya existe una franja de reserva en ese horario.")
            if self.cruces(HorarioClase).exists():
                raise ValidationError("El laboratorio está ocupado por una clase fija.")
        if self.pk:
            future = self.reservas.filter(activa=True, fecha__gte=timezone.localdate())
            old = FranjaLaboratorio.objects.get(pk=self.pk)
            protected = ("periodo_id", "laboratorio_id", "dia_semana", "hora_inicio", "hora_fin")
            if future.exists() and any(getattr(old, f) != getattr(self, f) for f in protected):
                raise ValidationError(
                    "Una franja con reservas futuras no puede cambiar de fecha, horario o laboratorio."
                )
            if (
                self.laboratorio_id
                and future.values("fecha")
                .annotate(total=Count("id"))
                .filter(total__gt=self.limite)
                .exists()
            ):
                raise ValidationError(
                    {"capacidad": "Ya hay más solicitudes activas que la capacidad indicada."}
                )


class GeneracionFranjas(models.Model):
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    creada = models.DateTimeField(auto_now_add=True)
    nuevas = models.PositiveIntegerField()
    retiradas = models.PositiveIntegerField()
    detalle = models.JSONField(default=dict)


class ReservaLaboratorio(models.Model):
    franja = models.ForeignKey(FranjaLaboratorio, on_delete=models.PROTECT, related_name="reservas")
    estudiante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservas_laboratorio"
    )
    laboratorio = models.ForeignKey(Laboratorio, on_delete=models.PROTECT)
    materia = models.ForeignKey(Materia, on_delete=models.PROTECT)
    fecha = models.DateField(db_index=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    creada = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)
    cancelada_el = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=12, choices=EstadoReserva.choices, default=EstadoReserva.PENDIENTE, db_index=True
    )
    decidida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decidida_el = models.DateTimeField(null=True, blank=True)
    motivo_decision = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["fecha", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["franja", "fecha", "estudiante"],
                condition=Q(activa=True),
                name="reserva_activa_unica",
            ),
            models.CheckConstraint(
                condition=Q(hora_fin__gt=F("hora_inicio")), name="reserva_horas_validas"
            ),
            models.CheckConstraint(
                condition=(
                    Q(activa=True, estado__in=["PENDIENTE", "CONFIRMADA"])
                    | Q(activa=False, estado__in=["RECHAZADA", "CANCELADA"])
                ),
                name="reserva_estado_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.laboratorio} · {self.fecha:%d/%m/%Y} · {self.estudiante}"


class AvisoReserva(models.Model):
    """Cola persistente; no almacena claves ni contenido de recuperacion."""

    reserva = models.OneToOneField(
        ReservaLaboratorio, on_delete=models.CASCADE, related_name="aviso"
    )
    creado = models.DateTimeField(auto_now_add=True)
    proximo_intento = models.DateTimeField(default=timezone.now, db_index=True)
    bloqueo_hasta = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveIntegerField(default=0)
    correo_enviado = models.BooleanField(default=False)
    telegram_enviado = models.BooleanField(default=False)
    completado = models.DateTimeField(null=True, blank=True)
    ultimo_error = models.CharField(max_length=100, blank=True)


class VisitaReservas(models.Model):
    estudiante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    fecha = models.DateField(default=timezone.localdate)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["estudiante", "fecha"], name="visita_diaria_unica")
        ]


class ArchivoMigracion(models.Model):
    origen = models.CharField(max_length=80)
    datos = models.JSONField()
    creada = models.DateTimeField(auto_now_add=True)


class LimiteRecuperacion(models.Model):
    clave = models.CharField(max_length=64)
    ventana = models.BigIntegerField()
    intentos = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["clave", "ventana"], name="limite_recuperacion_unico")
        ]


class EventoSeguridad(models.TextChoices):
    RECUPERACION_CORREO = "RECUPERACION_CORREO", "Contraseña restablecida por correo"
    CLAVE_TEMPORAL = "CLAVE_TEMPORAL", "Clave temporal generada por coordinación"
    CAMBIO_CLAVE = "CAMBIO_CLAVE", "Contraseña cambiada por el usuario"


class RegistroSeguridad(models.Model):
    """Bitácora de cambios de contraseña. Nunca guarda contraseñas ni tokens."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    usuario_nombre = models.CharField(max_length=150)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    evento = models.CharField(max_length=24, choices=EventoSeguridad.choices)
    ip = models.GenericIPAddressField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado"]
        verbose_name = "registro de seguridad"
        verbose_name_plural = "registros de seguridad"

    def __str__(self):
        return f"{self.creado:%Y-%m-%d %H:%M} · {self.usuario_nombre} · {self.get_evento_display()}"
