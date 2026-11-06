from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from tutorias.models import (
    FranjaLaboratorio,
    GeneracionFranjas,
    HorarioClase,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)


class EliminarSemestreTests(TestCase):
    def setUp(self):
        self.coord = User.objects.create_superuser(
            "borrar_coord", "borrar@example.test", "Testing-12345"
        )
        self.estudiante = User.objects.create_user(
            "borrar_estudiante", "estudiante@example.test", "Testing-12345"
        )
        self.inicio = timezone.localdate() + timedelta(days=30)
        self.periodo = PeriodoAcademico.objects.create(
            nombre="Ejemplo", fecha_inicio=self.inicio, fecha_fin=self.inicio + timedelta(days=90)
        )
        self.lab = Laboratorio.objects.create(nombre="Lab borrado")
        self.materia = Materia.objects.create(
            codigo="BORRAR", nombre="Materia", nivel="TEC", semestre=1
        )
        self.lab.materias.add(self.materia)
        self.franja = FranjaLaboratorio.objects.create(
            periodo=self.periodo,
            laboratorio=self.lab,
            dia_semana=1,
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )
        self.clase = HorarioClase.objects.create(
            periodo=self.periodo,
            laboratorio=self.lab,
            materia=self.materia,
            dia_semana=2,
            hora_inicio=time(18, 30),
            hora_fin=time(20),
        )
        GeneracionFranjas.objects.create(
            periodo=self.periodo, usuario=self.coord, nuevas=1, retiradas=0
        )
        self.url = reverse("eliminar_semestre", args=[self.periodo.pk])
        self.client.force_login(self.coord)

    def reserva(self, **kwargs):
        datos = dict(
            franja=self.franja,
            estudiante=self.estudiante,
            laboratorio=self.lab,
            materia=self.materia,
            fecha=self.inicio,
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )
        datos.update(kwargs)
        return ReservaLaboratorio.objects.create(**datos)

    def test_get_does_not_delete(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Eliminar semestre y horarios")
        self.assertEqual(response.context["resumen"]["clases"], 1)
        self.assertTrue(PeriodoAcademico.objects.filter(pk=self.periodo.pk).exists())

    def test_delete_example_with_schedules_preserves_catalog(self):
        otro = PeriodoAcademico.objects.create(
            nombre="Otro", fecha_inicio=self.inicio, fecha_fin=self.inicio + timedelta(days=60)
        )
        response = self.client.post(self.url, {"accion": "eliminar"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PeriodoAcademico.objects.filter(pk=self.periodo.pk).exists())
        self.assertFalse(FranjaLaboratorio.objects.filter(pk=self.franja.pk).exists())
        self.assertFalse(HorarioClase.objects.filter(pk=self.clase.pk).exists())
        self.assertFalse(GeneracionFranjas.objects.filter(periodo_id=self.periodo.pk).exists())
        self.assertTrue(PeriodoAcademico.objects.filter(pk=otro.pk).exists())
        self.assertTrue(self.lab.materias.filter(pk=self.materia.pk).exists())

    def test_empty_semester_can_be_deleted(self):
        p = PeriodoAcademico.objects.create(
            nombre="Vacio", fecha_inicio=self.inicio, fecha_fin=self.inicio
        )
        self.client.post(reverse("eliminar_semestre", args=[p.pk]), {"accion": "eliminar"})
        self.assertFalse(PeriodoAcademico.objects.filter(pk=p.pk).exists())

    def test_active_future_reservations_block_both_actions(self):
        self.reserva()
        for accion in ("cerrar", "eliminar"):
            self.client.post(self.url, {"accion": accion})
            self.periodo.refresh_from_db()
            self.assertTrue(self.periodo.activo)
            self.assertTrue(FranjaLaboratorio.objects.filter(pk=self.franja.pk).exists())

    def test_history_can_close_but_cannot_be_deleted(self):
        reserva = self.reserva(activa=False, estado="CANCELADA")
        self.client.post(self.url, {"accion": "eliminar"})
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.activo)
        self.client.post(self.url, {"accion": "cerrar"})
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.activo)
        self.assertTrue(ReservaLaboratorio.objects.filter(pk=reserva.pk).exists())
        self.assertTrue(HorarioClase.objects.filter(pk=self.clase.pk).exists())

    def test_historical_confirmed_reservation_is_preserved(self):
        self.reserva(fecha=timezone.localdate() - timedelta(days=1), estado="CONFIRMADA")
        self.client.post(self.url, {"accion": "cerrar"})
        self.periodo.refresh_from_db()
        self.assertFalse(self.periodo.activo)

    def test_changed_confirmation_does_not_close_silently(self):
        self.client.get(self.url)
        self.reserva(activa=False, estado="RECHAZADA")
        self.client.post(self.url, {"accion": "eliminar"})
        self.periodo.refresh_from_db()
        self.assertTrue(self.periodo.activo)

    def test_missing_action_does_nothing(self):
        self.client.post(self.url)
        self.assertTrue(PeriodoAcademico.objects.filter(pk=self.periodo.pk).exists())

    def test_other_protected_relation_rolls_back_schedule_deletion(self):
        with patch.object(PeriodoAcademico, "delete", side_effect=ProtectedError("protegido", [])):
            self.client.post(self.url, {"accion": "eliminar"})
        self.assertTrue(HorarioClase.objects.filter(pk=self.clase.pk).exists())
        self.assertTrue(FranjaLaboratorio.objects.filter(pk=self.franja.pk).exists())
        self.assertTrue(GeneracionFranjas.objects.filter(periodo=self.periodo).exists())

    def test_permissions_csrf_and_no_cache(self):
        response = self.client.get(reverse("configurar", args=["clases"]))
        self.assertIn("no-store", response.headers["Cache-Control"])
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.coord)
        self.assertEqual(secure.post(self.url, {"accion": "eliminar"}).status_code, 403)
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.post(self.url, {"accion": "eliminar"}).status_code, 403)
