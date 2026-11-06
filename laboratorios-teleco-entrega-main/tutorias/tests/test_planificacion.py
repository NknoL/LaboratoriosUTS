from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tutorias.forms import FranjaForm, LaboratorioForm
from tutorias.models import (
    FranjaLaboratorio,
    GeneracionFranjas,
    HorarioClase,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)
from tutorias.planificacion import calcular, publicar


class PlanificacionTests(TestCase):
    def test_night_classes_do_not_remove_daytime_slots(self):
        self.clase(hora_inicio=time(18, 30), hora_fin=time(21, 30))
        self.assertEqual(len(self.plan()["nuevas"]), 12)

    def test_missing_subject_blocks_generation(self):
        self.lab.materias.clear()
        self.assertTrue(self.plan()["conflictos"])
        with self.assertRaises(ValidationError):
            self.publicar()

    def test_overlapping_period_blocks_double_offer(self):
        otro = PeriodoAcademico.objects.create(
            nombre="Superpuesto", fecha_inicio=self.fecha, fecha_fin=self.fecha + timedelta(days=60)
        )
        self.franja(periodo=otro)
        plan = self.plan()
        self.assertEqual(len(plan["nuevas"]), 11)
        self.assertEqual(plan["otros_periodos"], [otro])

    def test_retirement_blocked_during_practice(self):
        f = self.franja()
        self.reserva(f)
        momento = timezone.make_aware(datetime.combine(self.fecha, time(9, 20)))
        with patch("tutorias.models.timezone.localtime", return_value=momento):
            self.assertTrue(self.lab.reservas_vigentes().exists())

    def test_publish_token_is_bound_to_coordinator(self):
        url = reverse("generar_franjas")
        response = self.client.post(
            url,
            {
                "accion": "calcular",
                "periodo": self.periodo.pk,
                "laboratorios": [self.lab.pk],
                "dias": [1],
            },
        )
        otro = User.objects.create_superuser(
            "otro_coordinador", "other@example.test", "Testing-12345"
        )
        self.client.force_login(otro)
        self.client.post(url, {"accion": "publicar", "token": response.context["token"]})
        self.assertFalse(FranjaLaboratorio.objects.filter(periodo=self.periodo).exists())

    def setUp(self):
        self.usuario = User.objects.create_superuser(
            "coordinador_test", "coord@example.test", "Testing-12345"
        )
        self.estudiante = User.objects.create_user(
            "estudiante_test", "student@example.test", "Testing-12345"
        )
        inicio = timezone.localdate() + timedelta(days=28)
        self.fecha = inicio - timedelta(days=inicio.weekday())
        self.periodo = PeriodoAcademico.objects.create(
            nombre="Prueba", fecha_inicio=self.fecha, fecha_fin=self.fecha + timedelta(days=120)
        )
        self.materia = Materia.objects.create(
            codigo="TEST-01", nombre="Redes de prueba", nivel="TEC", semestre=1
        )
        self.lab = Laboratorio.objects.create(nombre="Laboratorio de prueba", capacidad=20)
        self.lab.materias.add(self.materia)
        self.client.force_login(self.usuario)

    def plan(self):
        return calcular(self.periodo, [self.lab.pk], [1])

    def publicar(self, plan=None):
        return publicar(
            self.periodo.pk, [self.lab.pk], [1], (plan or self.plan())["huella"], self.usuario
        )

    def franja(self, **kwargs):
        datos = dict(
            periodo=self.periodo,
            laboratorio=self.lab,
            dia_semana=1,
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )
        datos.update(kwargs)
        return FranjaLaboratorio.objects.create(**datos)

    def clase(self, **kwargs):
        datos = dict(
            periodo=self.periodo,
            laboratorio=self.lab,
            materia=self.materia,
            dia_semana=1,
            hora_inicio=time(10),
            hora_fin=time(11, 30),
        )
        datos.update(kwargs)
        return HorarioClase.objects.create(**datos)

    def reserva(self, franja, **kwargs):
        datos = dict(
            franja=franja,
            laboratorio=self.lab,
            estudiante=self.estudiante,
            materia=self.materia,
            fecha=self.fecha,
            hora_inicio=franja.hora_inicio,
            hora_fin=franja.hora_fin,
        )
        datos.update(kwargs)
        return ReservaLaboratorio.objects.create(**datos)

    def test_preview_read_only_and_bounds(self):
        plan = self.plan()
        self.assertEqual(len(plan["nuevas"]), 12)
        self.assertFalse(FranjaLaboratorio.objects.filter(periodo=self.periodo).exists())
        self.assertEqual(plan["nuevas"][0].hora_inicio, time(9))
        self.assertEqual(plan["nuevas"][-1].hora_fin, time(18))

    def test_idempotent_without_student_requests(self):
        self.publicar()
        self.publicar()
        self.assertEqual(FranjaLaboratorio.objects.filter(periodo=self.periodo).count(), 12)
        self.assertEqual(GeneracionFranjas.objects.count(), 1)
        self.assertEqual(ReservaLaboratorio.objects.count(), 0)

    def test_class_filters_only_its_lab(self):
        otra = Laboratorio.objects.create(nombre="Otro laboratorio")
        otra.materias.add(self.materia)
        self.clase()
        plan = calcular(self.periodo, [self.lab.pk, otra.pk], [1])
        self.assertEqual(len([f for f in plan["nuevas"] if f.laboratorio_id == otra.pk]), 12)
        propias = [f for f in plan["nuevas"] if f.laboratorio_id == self.lab.pk]
        self.assertTrue(
            all(f.hora_fin <= time(10) or f.hora_inicio >= time(11, 30) for f in propias)
        )
        self.assertTrue(any(f.hora_inicio == time(11, 30) for f in propias))

    def test_inactive_manual_preserved(self):
        f = self.franja(activa=False)
        self.publicar()
        f.refresh_from_db()
        self.assertFalse(f.activa)
        self.assertFalse(
            FranjaLaboratorio.objects.filter(
                periodo=self.periodo, activa=True, hora_inicio=time(9)
            ).exists()
        )

    def test_stale_preview(self):
        plan = self.plan()
        self.clase()
        with self.assertRaisesMessage(ValidationError, "cambiaron"):
            self.publicar(plan)
        self.assertFalse(FranjaLaboratorio.objects.filter(periodo=self.periodo).exists())

    def test_new_booking_invalidates_preview(self):
        f = self.franja()
        plan = self.plan()
        self.reserva(f)
        with self.assertRaisesMessage(ValidationError, "cambiaron"):
            self.publicar(plan)

    def test_history_and_future_protection(self):
        self.publicar()
        f = FranjaLaboratorio.objects.get(periodo=self.periodo, hora_inicio=time(9))
        r = self.reserva(f)
        self.clase(hora_inicio=time(9), hora_fin=time(10))
        with self.assertRaises(ValidationError):
            self.publicar()
        r.activa, r.estado = False, "CANCELADA"
        r.save()
        self.publicar()
        f.refresh_from_db()
        self.assertFalse(f.activa)
        self.assertTrue(ReservaLaboratorio.objects.filter(pk=r.pk).exists())

    def test_rollback(self):
        self.publicar()
        self.clase(hora_inicio=time(9), hora_fin=time(10))
        with patch.object(
            FranjaLaboratorio, "full_clean", side_effect=ValidationError("fallo controlado")
        ):
            with self.assertRaises(ValidationError):
                self.publicar()
        self.assertEqual(
            FranjaLaboratorio.objects.filter(periodo=self.periodo, activa=True).count(), 12
        )

    def test_manual_edit_protects_automatic(self):
        f = self.franja(automatica=True)
        form = FranjaForm(
            {
                "periodo": self.periodo.pk,
                "laboratorio": self.lab.pk,
                "dia_semana": 1,
                "hora_inicio": "09:00",
                "hora_fin": "09:45",
                "activa": "on",
                "capacidad": 10,
            },
            instance=f,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        f.refresh_from_db()
        self.assertFalse(f.automatica)

    def test_create_and_delete_empty_lab(self):
        response = self.client.post(
            reverse("crear_configuracion", args=["laboratorios"]),
            {
                "nombre": "Nuevo laboratorio",
                "capacidad": 15,
                "activo": "on",
                "materias": [self.materia.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        lab = Laboratorio.objects.get(nombre="Nuevo laboratorio")
        self.assertTrue(lab.materias.filter(pk=self.materia.pk).exists())
        self.client.post(reverse("retirar_laboratorio", args=[lab.pk]))
        self.assertFalse(Laboratorio.objects.filter(pk=lab.pk).exists())

    def test_retire_preserves_history(self):
        f = self.franja(automatica=True)
        r = self.reserva(f, activa=False, estado="CANCELADA")
        self.client.post(reverse("retirar_laboratorio", args=[self.lab.pk]))
        self.lab.refresh_from_db()
        f.refresh_from_db()
        self.assertFalse(self.lab.activo)
        self.assertFalse(f.activa)
        self.assertTrue(ReservaLaboratorio.objects.filter(pk=r.pk).exists())

    def test_retire_blocked_even_in_edit_form(self):
        self.reserva(self.franja())
        self.client.post(reverse("retirar_laboratorio", args=[self.lab.pk]))
        self.lab.refresh_from_db()
        self.assertTrue(self.lab.activo)
        form = LaboratorioForm(
            {"nombre": self.lab.nombre, "capacidad": 20, "materias": [self.materia.pk]},
            instance=self.lab,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("activo", form.errors)

    def test_student_forbidden(self):
        self.client.force_login(self.estudiante)
        for url in [
            reverse("generar_franjas"),
            reverse("retirar_laboratorio", args=[self.lab.pk]),
            reverse("crear_configuracion", args=["laboratorios"]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_preview_and_publish_token(self):
        url = reverse("generar_franjas")
        response = self.client.post(
            url,
            {
                "accion": "calcular",
                "periodo": self.periodo.pk,
                "laboratorios": [self.lab.pk],
                "dias": [1],
            },
        )
        self.assertEqual(response.status_code, 200)
        token = response.context["token"]
        self.client.post(url, {"accion": "publicar", "token": token + "bad"})
        self.assertFalse(FranjaLaboratorio.objects.filter(periodo=self.periodo).exists())
        self.client.post(url, {"accion": "publicar", "token": token})
        self.assertEqual(FranjaLaboratorio.objects.filter(periodo=self.periodo).count(), 12)

    def test_get_is_read_only(self):
        self.assertEqual(
            self.client.get(reverse("retirar_laboratorio", args=[self.lab.pk])).status_code, 200
        )
        self.assertTrue(Laboratorio.objects.filter(pk=self.lab.pk).exists())

    def test_copy_classes_only_default(self):
        self.clase()
        self.franja()
        destino = PeriodoAcademico.objects.create(
            nombre="Destino",
            fecha_inicio=self.periodo.fecha_fin + timedelta(days=1),
            fecha_fin=self.periodo.fecha_fin + timedelta(days=100),
        )
        response = self.client.post(
            reverse("copiar_horarios"), {"origen": self.periodo.pk, "destino": destino.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(HorarioClase.objects.filter(periodo=destino).count(), 1)
        self.assertFalse(FranjaLaboratorio.objects.filter(periodo=destino).exists())
