"""Carga la programacion oficial de laboratorios para 2026-2.

Sin --aplicar solo comprueba. La carga es atomica y puede repetirse sin duplicar datos.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tutorias.horarios import franjas_45
from tutorias.models import (
    FranjaLaboratorio,
    HorarioClase,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)
from tutorias.programacion_2026_2 import CLASES, MATERIAS

PERIODO = "2026-2"
CLASES_DEMO = {
    (1, 5, "16:00", "18:00", "INGTEL1005", "N"),
    (2, 1, "10:00", "12:00", "TGST103", "A"),
    (3, 2, "08:00", "10:00", "TGST205", "B"),
    (4, 3, "14:00", "16:00", "TGST402", "A"),
    (5, 4, "18:00", "20:00", "INGTEL804", "N"),
}
HORAS_DEMO = {(time(8), time(10)), (time(10), time(12)), (time(14), time(16)), (time(16), time(18))}


def firma_clase(clase):
    return (
        clase.laboratorio_id,
        clase.dia_semana,
        clase.hora_inicio.strftime("%H:%M"),
        clase.hora_fin.strftime("%H:%M"),
        clase.materia.codigo,
        clase.grupo,
    )


class Command(BaseCommand):
    help = "Comprueba o carga las materias, clases y franjas de 45 minutos de los cinco labs para 2026-2."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar", action="store_true", help="Guarda los cambios tras la comprobacion."
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            self._cargar(aplicar=options["aplicar"])

    def _cargar(self, aplicar):
        periodo = PeriodoAcademico.objects.filter(nombre=PERIODO).first()
        if not periodo:
            raise CommandError(f"No existe el semestre {PERIODO}; no se modifico nada.")
        labs = dict(Laboratorio.objects.order_by("pk").values_list("pk", "nombre"))
        if set(labs) != set(range(1, 6)) or any(
            not labs[i].startswith(f"Lab {i}:") for i in range(1, 6)
        ):
            raise CommandError(
                "No coinciden los cinco laboratorios esperados; no se modifico nada."
            )
        if len(CLASES) != 38 or len(set(CLASES)) != len(CLASES):
            raise CommandError(
                "La programacion de origen no contiene las 38 ocupaciones esperadas."
            )
        if {fila[4] for fila in CLASES} != set(MATERIAS):
            raise CommandError("Las materias y clases de origen no coinciden.")

        clases = list(HorarioClase.objects.filter(periodo=periodo).select_related("materia"))
        actuales = {firma_clase(clase) for clase in clases}
        esperadas = set(CLASES)
        demo = actuales == CLASES_DEMO
        if actuales != esperadas and clases and not demo:
            raise CommandError(
                "Hay clases de 2026-2 distintas a las de ejemplo o al Excel. Revísalas antes de reemplazar."
            )

        franjas = list(FranjaLaboratorio.objects.filter(periodo=periodo))
        activas = [f for f in franjas if f.activa]
        ya_45 = bool(activas) and all(
            datetime.combine(date.min, f.hora_fin) - datetime.combine(date.min, f.hora_inicio)
            == timedelta(minutes=45)
            for f in activas
        )
        demo_franjas = all(
            f.dia_semana <= 5 and (f.hora_inicio, f.hora_fin) in HORAS_DEMO and f.capacidad is None
            for f in activas
        )
        if activas and not ya_45 and not demo_franjas:
            raise CommandError("Hay franjas personalizadas. No se reemplazan automáticamente.")
        if ya_45 and actuales != esperadas:
            raise CommandError(
                "Hay franjas de 45 minutos pero las clases no coinciden con el Excel."
            )

        reservas = ReservaLaboratorio.objects.filter(franja__periodo=periodo, activa=True)
        conflictos = []
        for lab_id, dia, inicio, fin, codigo, grupo in CLASES:
            for reserva in reservas.filter(
                laboratorio_id=lab_id,
                hora_inicio__lt=time.fromisoformat(fin),
                hora_fin__gt=time.fromisoformat(inicio),
            ):
                if reserva.fecha.isoweekday() == dia and reserva.fecha >= timezone.localdate():
                    conflictos.append(f"{labs[lab_id]} {reserva.fecha} {inicio}-{fin}")
        if conflictos:
            raise CommandError(
                "Clases nuevas cruzan reservas vigentes: " + ", ".join(sorted(set(conflictos)))
            )

        if not aplicar:
            self.stdout.write(
                f"Vista previa: {len(MATERIAS)} materias, 38 ocupaciones de clase; "
                f"{len(activas)} franjas actuales. No se modificó nada."
            )
            return

        materias = {}
        for codigo, (nombre, nivel, semestre, provisional) in MATERIAS.items():
            materia, creada = Materia.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "nivel": nivel,
                    "semestre": semestre,
                    "tecnica": True,
                    "linea": "Semestre provisional: confirmar con coordinación"
                    if provisional
                    else "",
                },
            )
            if not creada and (materia.nombre != nombre or materia.nivel != nivel):
                raise CommandError(f"La materia {codigo} ya existe con otro nombre o programa.")
            materias[codigo] = materia

        if actuales != esperadas:
            HorarioClase.objects.filter(periodo=periodo).delete()

        codigos_por_lab = defaultdict(set)
        for lab_id, dia, inicio, fin, codigo, grupo in CLASES:
            codigos_por_lab[lab_id].add(codigo)

        for lab_id in range(1, 6):
            lab = Laboratorio.objects.get(pk=lab_id)
            conservar = set(
                ReservaLaboratorio.objects.filter(
                    laboratorio=lab, activa=True, fecha__gte=timezone.localdate()
                ).values_list("materia_id", flat=True)
            )
            lab.materias.set(
                conservar | {materias[codigo].pk for codigo in codigos_por_lab[lab_id]}
            )

        if actuales != esperadas:
            for lab_id, dia, inicio, fin, codigo, grupo in CLASES:
                clase = HorarioClase(
                    periodo=periodo,
                    laboratorio_id=lab_id,
                    dia_semana=dia,
                    hora_inicio=time.fromisoformat(inicio),
                    hora_fin=time.fromisoformat(fin),
                    materia=materias[codigo],
                    grupo=grupo,
                )
                clase.full_clean()
                clase.save()

        nuevas = 0
        if not ya_45:
            for franja in franjas:
                if franja.reservas.exists():
                    if franja.activa:
                        franja.activa = False
                        franja.save(update_fields=["activa"])
                else:
                    franja.delete()

            bloqueos = defaultdict(list)
            for lab_id, dia, inicio, fin in HorarioClase.objects.filter(
                periodo__fecha_inicio__lte=periodo.fecha_fin,
                periodo__fecha_fin__gte=periodo.fecha_inicio,
            ).values_list("laboratorio_id", "dia_semana", "hora_inicio", "hora_fin"):
                bloqueos[(lab_id, dia)].append((inicio, fin))

            for lab_id in range(1, 6):
                for dia in range(1, 7):
                    for inicio, fin in franjas_45():
                        if any(
                            b_inicio < fin and b_fin > inicio
                            for b_inicio, b_fin in bloqueos[(lab_id, dia)]
                        ):
                            continue
                        franja = FranjaLaboratorio(
                            periodo=periodo,
                            laboratorio_id=lab_id,
                            dia_semana=dia,
                            hora_inicio=inicio,
                            hora_fin=fin,
                        )
                        franja.full_clean()
                        franja.save()
                        nuevas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"2026-2 cargado: {len(MATERIAS)} materias, {len(CLASES)} clases, "
                f"{nuevas} franjas nuevas de 45 min. Usuarios y reservas conservados."
            )
        )
