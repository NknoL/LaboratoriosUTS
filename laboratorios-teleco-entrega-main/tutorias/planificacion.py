"""Cálculo sin escrituras y publicación protegida de la oferta semanal."""

import hashlib
import json
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from .db_lock import escritura_atomica
from .models import (
    FranjaLaboratorio,
    GeneracionFranjas,
    HorarioClase,
    Laboratorio,
    PeriodoAcademico,
    ReservaLaboratorio,
)


def cruza(a, b, c, d):
    return a < d and b > c


def calcular(periodo, laboratorios, dias):
    dias = sorted(set(dias))
    labs = list(Laboratorio.objects.filter(pk__in=laboratorios).order_by("pk"))
    periodos = list(
        PeriodoAcademico.objects.filter(
            fecha_inicio__lte=periodo.fecha_fin, fecha_fin__gte=periodo.fecha_inicio
        ).order_by("pk")
    )
    ids = [p.pk for p in periodos]
    clases = list(
        HorarioClase.objects.filter(periodo_id__in=ids, laboratorio__in=labs).order_by("pk")
    )
    franjas = list(
        FranjaLaboratorio.objects.filter(periodo_id__in=ids, laboratorio__in=labs).order_by("pk")
    )
    reservas = list(
        ReservaLaboratorio.objects.filter(
            laboratorio__in=labs, activa=True, fecha__gte=timezone.localdate()
        )
        .order_by("pk")
        .values("id", "franja_id", "fecha", "hora_inicio", "hora_fin", "estado")
    )
    materias = {
        lab.pk: list(
            lab.materias.filter(activa=True, tecnica=True)
            .values_list("pk", flat=True)
            .order_by("pk")
        )
        for lab in labs
    }
    # La huella incluye dependencias, no solo el resultado: publicar requiere una vista vigente.
    snapshot = {
        "periodo": periodo.pk,
        "dias": sorted(dias),
        "materias": materias,
        "labs": [(lab.pk, lab.nombre, lab.activo, lab.capacidad) for lab in labs],
        "periodos": [(p.pk, p.fecha_inicio, p.fecha_fin, p.activo) for p in periodos],
        "clases": [
            (c.pk, c.periodo_id, c.laboratorio_id, c.dia_semana, c.hora_inicio, c.hora_fin)
            for c in clases
        ],
        "franjas": [
            (
                f.pk,
                f.periodo_id,
                f.laboratorio_id,
                f.dia_semana,
                f.hora_inicio,
                f.hora_fin,
                f.activa,
                f.automatica,
                f.capacidad,
            )
            for f in franjas
        ],
        "reservas": reservas,
    }
    huella = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
    nuevas, retirar, conservar, conflictos = [], [], [], []
    if periodo.fecha_fin < timezone.localdate():
        conflictos.append("No se puede generar oferta para un semestre finalizado.")
    for lab in labs:
        if not lab.activo or not materias[lab.pk]:
            conflictos.append(f"{lab}: debe estar activo y tener materias técnicas activas.")
            continue
        for dia in sorted(dias):
            bloqueos = [
                (c.hora_inicio, c.hora_fin)
                for c in clases
                if c.laboratorio_id == lab.pk and c.dia_semana == dia
            ]
            actuales = [f for f in franjas if f.laboratorio_id == lab.pk and f.dia_semana == dia]
            automaticas = [f for f in actuales if f.periodo_id == periodo.pk and f.automatica]
            manuales = [f for f in actuales if f.periodo_id == periodo.pk and not f.automatica]
            externas = [f for f in actuales if f.periodo_id != periodo.pk and f.activa]
            for f in manuales:
                if f.activa and any(cruza(f.hora_inicio, f.hora_fin, a, b) for a, b in bloqueos):
                    conflictos.append(
                        f"{lab}, {f.get_dia_semana_display()} {f.hora_inicio:%H:%M}: ajusta la franja manual que cruza una clase."
                    )
            # También se respeta una franja desactivada manualmente: no se vuelve a ofrecer.
            bloqueos += [(f.hora_inicio, f.hora_fin) for f in manuales + externas]
            libres = [(time(9), time(18))]
            for a, b in sorted(bloqueos):
                recortados = []
                for inicio, fin in libres:
                    if not cruza(inicio, fin, a, b):
                        recortados.append((inicio, fin))
                    else:
                        if inicio < a:
                            recortados.append((inicio, a))
                        if b < fin:
                            recortados.append((b, fin))
                libres = recortados
            deseadas = set()
            for inicio, fin in libres:
                cursor = datetime.combine(date.min, inicio)
                limite = datetime.combine(date.min, fin)
                while cursor + timedelta(minutes=45) <= limite:
                    siguiente = cursor + timedelta(minutes=45)
                    deseadas.add((cursor.time(), siguiente.time()))
                    cursor = siguiente
            for f in automaticas:
                if f.activa and (f.hora_inicio, f.hora_fin) not in deseadas:
                    retirar.append(f)
                    if any(r["franja_id"] == f.pk for r in reservas):
                        conflictos.append(
                            f"{lab}, {f.get_dia_semana_display()} {f.hora_inicio:%H:%M}: hay solicitudes futuras que impiden retirar esta franja."
                        )
            for inicio, fin in sorted(deseadas):
                existente = next(
                    (
                        f
                        for f in automaticas
                        if f.hora_inicio == inicio and f.hora_fin == fin and f.activa
                    ),
                    None,
                )
                if existente:
                    conservar.append(existente)
                else:
                    nuevas.append(
                        FranjaLaboratorio(
                            periodo=periodo,
                            laboratorio=lab,
                            dia_semana=dia,
                            hora_inicio=inicio,
                            hora_fin=fin,
                            automatica=True,
                        )
                    )
    return {
        "huella": huella,
        "nuevas": nuevas,
        "retirar": retirar,
        "conservar": conservar,
        "conflictos": conflictos,
        "otros_periodos": [p for p in periodos if p.pk != periodo.pk],
        "manuales": [
            f
            for f in franjas
            if f.periodo_id == periodo.pk and not f.automatica and f.dia_semana in dias
        ],
    }


def publicar(periodo_id, laboratorios, dias, huella, usuario):
    with escritura_atomica():
        periodo = PeriodoAcademico.objects.get(pk=periodo_id)
        plan = calcular(periodo, laboratorios, dias)
        if plan["huella"] != huella:
            raise ValidationError(
                "La programación o las reservas cambiaron. Calcula una nueva vista previa."
            )
        if plan["conflictos"]:
            raise ValidationError(plan["conflictos"])
        FranjaLaboratorio.objects.filter(pk__in=[f.pk for f in plan["retirar"]]).update(
            activa=False
        )
        for franja in plan["nuevas"]:
            franja.full_clean()
            franja.save()
        if plan["nuevas"] or plan["retirar"]:
            GeneracionFranjas.objects.create(
                periodo=periodo,
                usuario=usuario,
                nuevas=len(plan["nuevas"]),
                retiradas=len(plan["retirar"]),
                detalle={"laboratorios": sorted(laboratorios), "dias": sorted(dias)},
            )
        return plan
