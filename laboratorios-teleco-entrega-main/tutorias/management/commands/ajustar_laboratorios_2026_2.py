"""Ajuste conservador del catalogo y las franjas; no modifica clases ni reservas."""

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tutorias.catalogo import MATERIAS as CATALOGO_INICIAL
from tutorias.db_lock import escritura_atomica
from tutorias.horarios import franjas_45
from tutorias.management.commands.cargar_programacion_2026_2 import firma_clase
from tutorias.models import (
    FranjaLaboratorio,
    HorarioClase,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)
from tutorias.programacion_2026_2 import CLASES, MATERIAS


class Command(BaseCommand):
    help = "Revisa el catalogo del Excel 2026-2 y las reservas de 09:00 a 18:00. Requiere --aplicar para guardar."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        try:
            with escritura_atomica():
                self.ajustar(options["aplicar"])
        except ValidationError as exc:
            raise CommandError("No se guardo nada: " + " ".join(exc.messages)) from exc

    def ajustar(self, aplicar):
        periodo = PeriodoAcademico.objects.filter(nombre="2026-2").first()
        labs = list(Laboratorio.objects.order_by("pk"))
        if (
            not periodo
            or [lab.pk for lab in labs] != list(range(1, 6))
            or any(not lab.nombre.startswith(f"Lab {lab.pk}:") for lab in labs)
        ):
            raise CommandError("No coincide el semestre o los cinco laboratorios esperados.")
        clases = HorarioClase.objects.filter(periodo=periodo).select_related("materia")
        if {firma_clase(clase) for clase in clases} != set(CLASES) or clases.count() != len(CLASES):
            raise CommandError(
                "Las clases no coinciden con el Excel 2026-2. Revisalas antes del ajuste."
            )
        materias = {m.codigo: m for m in Materia.objects.filter(codigo__in=MATERIAS)}
        if set(materias) != set(MATERIAS):
            raise CommandError("Primero importa las 25 materias de la programacion 2026-2.")
        por_lab = defaultdict(set)
        for lab_id, dia, inicio, fin, codigo, grupo in CLASES:
            por_lab[lab_id].add(materias[codigo].pk)
        antiguos = Materia.objects.filter(
            codigo__in=[fila[0] for fila in CATALOGO_INICIAL]
        ).exclude(codigo__in=MATERIAS)
        futuras = ReservaLaboratorio.objects.filter(activa=True, fecha__gte=timezone.localdate())
        if futuras.filter(materia__in=antiguos).exists() or any(
            futuras.filter(laboratorio=lab).exclude(materia_id__in=por_lab[lab.pk]).exists()
            for lab in labs
        ):
            raise CommandError(
                "Hay reservas futuras en materias que se retirarian. Revisa esas solicitudes primero."
            )

        bloqueos = defaultdict(list)
        for clase in HorarioClase.objects.filter(
            periodo__fecha_inicio__lte=periodo.fecha_fin,
            periodo__fecha_fin__gte=periodo.fecha_inicio,
        ):
            bloqueos[(clase.laboratorio_id, clase.dia_semana)].append(
                (clase.hora_inicio, clase.hora_fin)
            )
        esperadas = {
            (lab.pk, dia, inicio, fin)
            for lab in labs
            for dia in range(1, 7)
            for inicio, fin in franjas_45()
            if not any(a < fin and b > inicio for a, b in bloqueos[(lab.pk, dia)])
        }
        actuales = list(FranjaLaboratorio.objects.filter(periodo=periodo))

        def clave(franja):
            return (franja.laboratorio_id, franja.dia_semana, franja.hora_inicio, franja.hora_fin)

        retirar = [f.pk for f in actuales if f.activa and clave(f) not in esperadas]
        if futuras.filter(franja_id__in=retirar).exists():
            raise CommandError(
                "Hay reservas futuras fuera de las nuevas franjas. Revisalas antes del ajuste."
            )
        existentes = {clave(f) for f in actuales}
        nuevas = sorted(esperadas - existentes)
        self.stdout.write(
            f"Materias del Excel: {len(materias)}. Asociaciones: {sum(map(len, por_lab.values()))}."
        )
        self.stdout.write(
            f"Materias anteriores a desactivar: {antiguos.filter(activa=True).count()}."
        )
        self.stdout.write(
            f"Franjas a retirar: {len(retirar)}. Franjas nuevas: {len(nuevas)}. Jornada: 09:00-18:00."
        )
        if not aplicar:
            self.stdout.write(
                "Vista previa. No se modifico nada. Usa --aplicar despues de respaldar la base."
            )
            return

        antiguos.update(activa=False)
        Materia.objects.filter(pk__in=[m.pk for m in materias.values()]).update(
            activa=True, tecnica=True
        )
        for lab in labs:
            lab.materias.set(por_lab[lab.pk])
        FranjaLaboratorio.objects.filter(pk__in=retirar).update(activa=False)
        for lab_id, dia, inicio, fin in nuevas:
            franja = FranjaLaboratorio(
                periodo=periodo,
                laboratorio_id=lab_id,
                dia_semana=dia,
                hora_inicio=inicio,
                hora_fin=fin,
            )
            franja.full_clean()
            franja.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Ajuste completado. Clases, usuarios, capacidades existentes e historial conservados."
            )
        )
