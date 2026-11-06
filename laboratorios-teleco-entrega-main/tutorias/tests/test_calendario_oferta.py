from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tutorias.models import FranjaLaboratorio, Laboratorio, PeriodoAcademico


class CalendarioOfertaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser(
            "calendario_coord", "calendario@example.test", "Testing-12345"
        )
        cls.fecha = timezone.localdate() + timedelta(days=7)
        cls.periodo = PeriodoAcademico.objects.create(
            nombre="Calendario prueba",
            fecha_inicio=cls.fecha,
            fecha_fin=cls.fecha + timedelta(days=90),
        )
        cls.lab = Laboratorio.objects.create(nombre="Calendario laboratorio")
        cls.franja = FranjaLaboratorio.objects.create(
            periodo=cls.periodo,
            laboratorio=cls.lab,
            dia_semana=cls.fecha.isoweekday(),
            hora_inicio=time(9),
            hora_fin=time(9, 45),
            activa=False,
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.params = {"laboratorio": self.lab.pk, "periodo": self.periodo.pk}

    def test_inactive_slots_explained_without_reactivating(self):
        response = self.client.get(reverse("calendario"), self.params)
        self.assertContains(response, "Todas las franjas de préstamo")
        self.franja.refresh_from_db()
        self.assertFalse(self.franja.activa)

    def test_active_slots_appear_in_events_and_remove_warning(self):
        self.franja.activa = True
        self.franja.save()
        response = self.client.get(reverse("calendario"), self.params)
        self.assertEqual(response.context["aviso_oferta"], "")
        events = self.client.get(
            reverse("eventos_calendario"),
            {
                **self.params,
                "start": self.fecha.isoformat(),
                "end": (self.fecha + timedelta(days=1)).isoformat(),
            },
        ).json()
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["id"].startswith(f"franja-{self.franja.pk}-"))

    def test_missing_slots_message(self):
        self.franja.delete()
        response = self.client.get(reverse("calendario"), self.params)
        self.assertContains(response, "no tiene franjas de préstamo publicadas")

    def test_inactive_semester_message(self):
        self.periodo.activo = False
        self.periodo.save()
        response = self.client.get(reverse("calendario"), self.params)
        self.assertContains(response, "Este semestre está inactivo")
