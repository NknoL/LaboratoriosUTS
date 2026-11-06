from datetime import date

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tutorias.catalogo import MATERIAS
from tutorias.horarios import franjas_45
from tutorias.models import (
    FranjaLaboratorio,
    Laboratorio,
    Materia,
    PeriodoAcademico,
)


class Command(BaseCommand):
    help = "Prepara el catálogo y las franjas iniciales sin crear cuentas."

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        segunda = today.month > 6
        periodo, _ = PeriodoAcademico.objects.get_or_create(
            nombre=f"{today.year}-{2 if segunda else 1}",
            defaults={
                "fecha_inicio": date(today.year, 7 if segunda else 1, 1),
                "fecha_fin": date(today.year, 12 if segunda else 6, 31),
            },
        )
        existentes = list(Laboratorio.objects.order_by("pk"))
        if len(existentes) != 5:
            raise CommandError(
                "Se esperan cinco laboratorios. Ejecuta las migraciones y revisa la configuración."
            )
        labs = dict(enumerate(existentes, 1))
        for codigo, nombre, nivel, semestre, numeros in MATERIAS:
            materia, created = Materia.objects.get_or_create(
                codigo=codigo,
                defaults={"nombre": nombre, "nivel": nivel, "semestre": semestre, "tecnica": True},
            )
            if created:
                for numero in numeros:
                    labs[numero].materias.add(materia)
        for lab in labs.values():
            if lab.franjas.filter(periodo=periodo).exists():
                continue
            for dia in range(1, 7):
                for inicio, fin in franjas_45():
                    franja = FranjaLaboratorio(
                        periodo=periodo,
                        laboratorio=lab,
                        dia_semana=dia,
                        hora_inicio=inicio,
                        hora_fin=fin,
                    )
                    try:
                        franja.full_clean()
                    except ValidationError:
                        continue
                    franja.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Catálogo preparado. Revisa materias por laboratorio y franjas de ejemplo en Configuración."
            )
        )
