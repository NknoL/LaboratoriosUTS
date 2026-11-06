from datetime import datetime

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from .db_lock import escritura_atomica
from .horarios import dentro_jornada
from .models import (
    EstadoReserva,
    FranjaLaboratorio,
    HorarioClase,
    ReservaLaboratorio,
    es_coordinador,
    es_estudiante,
)
from .notificaciones import avisar_nueva_solicitud

SIN_CUPOS = "No hay más cupos en el salón a esa hora. Por favor, elige otra franja horaria"


def estado_franja(franja, fecha, excluir_reserva=None):
    inicio = timezone.make_aware(datetime.combine(fecha, franja.hora_inicio))
    motivo = ""
    if not franja.activa or not franja.laboratorio.activo or not franja.periodo.activo:
        motivo = "Esta franja no está habilitada."
    elif not dentro_jornada(franja.hora_inicio, franja.hora_fin):
        motivo = "Los préstamos están disponibles de 09:00 a 18:00."
    elif not franja.periodo.fecha_inicio <= fecha <= franja.periodo.fecha_fin:
        motivo = "La fecha está fuera del semestre."
    elif fecha.isoweekday() != franja.dia_semana:
        motivo = "La franja no corresponde al día seleccionado."
    elif inicio <= timezone.now():
        motivo = "La franja ya comenzó."
    elif HorarioClase.objects.filter(
        laboratorio=franja.laboratorio,
        periodo__activo=True,
        periodo__fecha_inicio__lte=fecha,
        periodo__fecha_fin__gte=fecha,
        dia_semana=fecha.isoweekday(),
        hora_inicio__lt=franja.hora_fin,
        hora_fin__gt=franja.hora_inicio,
    ).exists():
        motivo = "Laboratorio ocupado por una clase fija."
    # Cupos compartidos por laboratorio y fecha, independientemente de la materia.
    ocupados = (
        ReservaLaboratorio.objects.filter(
            laboratorio=franja.laboratorio,
            fecha=fecha,
            activa=True,
            hora_inicio__lt=franja.hora_fin,
            hora_fin__gt=franja.hora_inicio,
        )
        .exclude(pk=excluir_reserva)
        .count()
    )
    disponibles = max(0, franja.limite - ocupados)
    if not motivo and not disponibles:
        motivo = SIN_CUPOS
    return {
        "id": franja.pk,
        "inicio": franja.hora_inicio.strftime("%H:%M"),
        "fin": franja.hora_fin.strftime("%H:%M"),
        "ocupados": ocupados,
        "capacidad": franja.limite,
        "disponibles": disponibles,
        "reservable": not motivo,
        "motivo": motivo,
    }


@escritura_atomica()
def reservar(estudiante, franja_id, materia_id, fecha):
    # SQLite BEGIN IMMEDIATE serializa lectura del cupo e inserción entre conexiones.
    if not es_estudiante(estudiante):
        raise ValidationError("Solo los estudiantes pueden reservar.")
    if not estudiante.perfil.completo:
        raise ValidationError("Completa tus datos de registro antes de reservar.")
    try:
        franja = FranjaLaboratorio.objects.select_related("laboratorio", "periodo").get(
            pk=franja_id
        )
    except FranjaLaboratorio.DoesNotExist:
        raise ValidationError("La franja ya no existe.")
    materia = franja.laboratorio.materias.filter(pk=materia_id, activa=True, tecnica=True).first()
    if materia is None:
        raise ValidationError("La materia no pertenece a este laboratorio.")
    if ReservaLaboratorio.objects.filter(
        estudiante=estudiante, franja=franja, fecha=fecha, activa=True
    ).exists():
        raise ValidationError("Ya tienes una reserva para esta franja.")
    estado = estado_franja(franja, fecha)
    if not estado["reservable"]:
        raise ValidationError(estado["motivo"])
    if ReservaLaboratorio.objects.filter(
        estudiante=estudiante,
        fecha=fecha,
        activa=True,
        hora_inicio__lt=franja.hora_fin,
        hora_fin__gt=franja.hora_inicio,
    ).exists():
        raise ValidationError("Ya tienes una reserva en otro laboratorio a esa hora.")
    reserva = ReservaLaboratorio.objects.create(
        estudiante=estudiante,
        franja=franja,
        laboratorio=franja.laboratorio,
        materia=materia,
        fecha=fecha,
        hora_inicio=franja.hora_inicio,
        hora_fin=franja.hora_fin,
    )
    avisar_nueva_solicitud(
        reserva
    )  # Se envía al confirmar la transacción, sin demorar la respuesta.
    return reserva


def resumen_uso(inicio, fin):
    reservas = ReservaLaboratorio.objects.filter(
        activa=True, estado=EstadoReserva.CONFIRMADA, fecha__range=(inicio, fin)
    )
    return {
        "reservas": reservas.count(),
        "estudiantes": reservas.values("estudiante").distinct().count(),
        "laboratorios": list(
            reservas.values("laboratorio__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "laboratorio__nombre")
        ),
        "materias": list(
            reservas.values("materia__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "materia__nombre")
        ),
    }


@escritura_atomica()
def decidir_solicitud(coordinador, reserva_id, decision, motivo=""):
    if not es_coordinador(coordinador):
        raise ValidationError("Solo coordinación puede decidir solicitudes.")
    if decision not in ("aprobar", "rechazar"):
        raise ValidationError("Decisión no válida.")
    reserva = ReservaLaboratorio.objects.select_related(
        "franja__laboratorio", "franja__periodo", "estudiante", "materia"
    ).get(pk=reserva_id)
    if reserva.estado != EstadoReserva.PENDIENTE or not reserva.activa:
        raise ValidationError("Esta solicitud ya fue resuelta o cancelada.")
    if decision == "aprobar":
        estado = estado_franja(reserva.franja, reserva.fecha, excluir_reserva=reserva.pk)
        if not estado["reservable"]:
            raise ValidationError(estado["motivo"])
        if (
            not reserva.estudiante.is_active
            or not reserva.franja.laboratorio.materias.filter(
                pk=reserva.materia_id, activa=True, tecnica=True
            ).exists()
        ):
            raise ValidationError("El estudiante o la materia ya no están habilitados.")
        reserva.estado = EstadoReserva.CONFIRMADA
    else:
        if not motivo.strip():
            raise ValidationError("Indica el motivo del rechazo.")
        reserva.estado = EstadoReserva.RECHAZADA
        reserva.activa = False
    reserva.motivo_decision = motivo.strip()[:300]
    reserva.decidida_por = coordinador
    reserva.decidida_el = timezone.now()
    reserva.save(
        update_fields=["estado", "activa", "motivo_decision", "decidida_por", "decidida_el"]
    )
    return reserva
