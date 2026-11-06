from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from tutorias.forms import correo_institucional
from tutorias.models import (
    AvisoReserva,
    EstadoReserva,
    FranjaLaboratorio,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    ReservaLaboratorio,
)
from tutorias.services import decidir_solicitud, estado_franja, reservar


class ReservasSeguridadTests(TestCase):
    def setUp(self):
        self.fecha = timezone.localdate() + timedelta(days=14)
        if self.fecha.isoweekday() == 7:
            self.fecha += timedelta(days=1)
        self.coordinador = User.objects.create_superuser(
            "coord_qa", "qa@example.test", "Testing-12345"
        )
        self.estudiantes = []
        for numero in range(3):
            user = User.objects.create_user(
                f"90000{numero}",
                f"qa{numero}@correo.uts.edu.co",
                "Testing-12345",
                first_name="Prueba",
                last_name="Local",
            )
            perfil = user.perfil
            perfil.cedula = user.username
            perfil.programa = "TEC"
            perfil.semestre = 1
            perfil.save()
            self.estudiantes.append(user)
        periodo = PeriodoAcademico.objects.create(
            nombre="QA reservas",
            fecha_inicio=self.fecha,
            fecha_fin=self.fecha + timedelta(days=90),
        )
        self.materia = Materia.objects.create(
            codigo="QA-REDES", nombre="Redes QA", nivel="TEC", semestre=1
        )
        self.lab = Laboratorio.objects.create(nombre="Laboratorio QA reservas", capacidad=2)
        self.lab.materias.add(self.materia)
        self.franja = FranjaLaboratorio.objects.create(
            laboratorio=self.lab,
            periodo=periodo,
            dia_semana=self.fecha.isoweekday(),
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )

    def solicitar(self, numero=0):
        # TestCase no confirma la transaccion exterior: no se envian correos reales.
        return reservar(self.estudiantes[numero], self.franja.pk, self.materia.pk, self.fecha)

    def test_pending_reservations_share_capacity_and_queue_notice(self):
        reserva = self.solicitar()
        self.assertEqual(reserva.estado, EstadoReserva.PENDIENTE)
        self.assertTrue(AvisoReserva.objects.filter(reserva=reserva).exists())
        self.solicitar(1)
        with self.assertRaisesMessage(ValidationError, "No hay más cupos"):
            self.solicitar(2)
        self.assertEqual(estado_franja(self.franja, self.fecha)["disponibles"], 0)

    def test_approval_and_rejection_release_only_rejected_seat(self):
        primera, segunda = self.solicitar(), self.solicitar(1)
        decidir_solicitud(self.coordinador, primera.pk, "aprobar")
        decidir_solicitud(self.coordinador, segunda.pk, "rechazar", "Prueba de disponibilidad")
        primera.refresh_from_db()
        self.assertEqual(primera.estado, EstadoReserva.CONFIRMADA)
        self.assertEqual(estado_franja(self.franja, self.fecha)["disponibles"], 1)
        self.solicitar(2)

    def test_student_cannot_approve_or_access_coordination(self):
        reserva = self.solicitar()
        with self.assertRaises(ValidationError):
            decidir_solicitud(self.estudiantes[0], reserva.pk, "aprobar")
        self.client.force_login(self.estudiantes[0])
        self.assertEqual(self.client.get(reverse("solicitudes")).status_code, 403)

    def test_duplicate_student_and_email_are_rejected(self):
        self.solicitar()
        with self.assertRaises(ValidationError):
            self.solicitar()
        with self.assertRaisesMessage(ValidationError, "Este correo ya está en uso"):
            correo_institucional("  QA0@CORREO.UTS.EDU.CO ")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="otro_qa", email="QA0@CORREO.UTS.EDU.CO")

    def test_csrf_required_to_reserve(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.estudiantes[0])
        self.assertEqual(client.post(reverse("confirmar_reserva"), {}).status_code, 403)

    def test_invalid_subject_filter_returns_400_not_500(self):
        self.client.force_login(self.estudiantes[0])
        response = self.client.get(
            reverse("disponibilidad", args=[self.lab.pk]),
            {"fecha": self.fecha.isoformat(), "materia": "9" * 5000},
        )
        self.assertEqual(response.status_code, 400)


@skipUnless(connection.vendor == "mysql", "Comprueba el bloqueo de MySQL/MariaDB.")
class CupoConcurrenteTests(TransactionTestCase):
    setUp = ReservasSeguridadTests.setUp

    def test_only_one_student_gets_last_seat_across_connections(self):
        barrera = Barrier(2)

        def competir(usuario_id):
            close_old_connections()
            try:
                usuario = User.objects.get(pk=usuario_id)
                barrera.wait(timeout=10)
                try:
                    reservar(usuario, self.franja.pk, self.materia.pk, self.fecha)
                    return "reservado"
                except ValidationError:
                    return "sin_cupo"
            finally:
                connection.close()

        with patch("tutorias.services.avisar_nueva_solicitud"):
            reservar(self.estudiantes[0], self.franja.pk, self.materia.pk, self.fecha)
            with ThreadPoolExecutor(max_workers=2) as executor:
                resultados = list(executor.map(competir, [u.pk for u in self.estudiantes[1:]]))
        self.assertCountEqual(resultados, ["reservado", "sin_cupo"])
        self.assertEqual(ReservaLaboratorio.objects.filter(franja=self.franja).count(), 2)
