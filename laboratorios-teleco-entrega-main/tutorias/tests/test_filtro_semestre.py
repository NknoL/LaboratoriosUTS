from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tutorias.models import FranjaLaboratorio, HorarioClase, Laboratorio, Materia, PeriodoAcademico


class FiltroSemestreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinador = User.objects.create_superuser(
            "filtro_coord", "filtro@example.test", "Testing-12345"
        )
        fecha = timezone.localdate() + timedelta(days=30)
        cls.periodo = PeriodoAcademico.objects.create(
            nombre="Semestre A", fecha_inicio=fecha, fecha_fin=fecha + timedelta(days=60)
        )
        cls.otro = PeriodoAcademico.objects.create(
            nombre="Semestre B",
            fecha_inicio=fecha + timedelta(days=70),
            fecha_fin=fecha + timedelta(days=130),
            activo=False,
        )
        cls.vacio = PeriodoAcademico.objects.create(
            nombre="Sin horarios",
            fecha_inicio=fecha + timedelta(days=140),
            fecha_fin=fecha + timedelta(days=200),
        )
        cls.lab = Laboratorio.objects.create(nombre="Lab filtro")
        cls.materia = Materia.objects.create(
            codigo="FILTRO", nombre="Materia filtro", nivel="TEC", semestre=1
        )
        cls.lab.materias.add(cls.materia)
        cls.ids = {}
        for periodo in (cls.periodo, cls.otro):
            franjas = []
            for i in range(12):
                inicio = datetime.combine(fecha, time(9)) + timedelta(minutes=45 * i)
                franjas.append(
                    FranjaLaboratorio.objects.create(
                        periodo=periodo,
                        laboratorio=cls.lab,
                        dia_semana=1,
                        hora_inicio=inicio.time(),
                        hora_fin=(inicio + timedelta(minutes=45)).time(),
                    )
                )
            cls.ids[periodo.pk] = [f.pk for f in franjas]
            HorarioClase.objects.create(
                periodo=periodo,
                laboratorio=cls.lab,
                materia=cls.materia,
                dia_semana=2,
                hora_inicio=time(18, 30),
                hora_fin=time(20),
            )

    def setUp(self):
        self.client.force_login(self.coordinador)

    def lista(self, tipo="franjas", **params):
        return self.client.get(reverse("configurar", args=[tipo]), params)

    def test_requires_selection_for_both_tabs(self):
        for tipo in ("franjas", "clases"):
            response = self.lista(tipo)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["rows"], [])
            self.assertContains(response, "Selecciona un semestre para consultar")
            self.assertNotContains(response, 'class="table"')

    def test_slots_filtered_and_paginated(self):
        response = self.lista(periodo=self.periodo.pk)
        self.assertEqual(len(response.context["rows"]), 10)
        self.assertEqual(response.context["pagina"].paginator.count, 12)
        self.assertTrue(all(r["pk"] in self.ids[self.periodo.pk] for r in response.context["rows"]))
        second = self.lista(periodo=self.periodo.pk, pagina=2)
        self.assertEqual(len(second.context["rows"]), 2)
        self.assertFalse(
            set(r["pk"] for r in response.context["rows"])
            & set(r["pk"] for r in second.context["rows"])
        )

    def test_inactive_semester_and_classes(self):
        response = self.lista("clases", periodo=self.otro.pk)
        self.assertEqual(response.context["pagina"].paginator.count, 1)
        self.assertEqual(
            response.context["rows"][0]["pk"], HorarioClase.objects.get(periodo=self.otro).pk
        )

    def test_invalid_ids_do_not_show_all(self):
        for value in ("abc", "999999999999999999999999999", "999999", "-1"):
            response = self.lista(periodo=value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["rows"], [])
            self.assertContains(response, "Selecciona un semestre válido")

    def test_empty_and_out_of_range_pages(self):
        empty = self.lista(periodo=self.vacio.pk)
        self.assertContains(empty, "No hay horarios registrados para este semestre")
        response = self.lista(periodo=self.periodo.pk, pagina=900)
        self.assertEqual(response.context["pagina"].number, 2)
        response = self.lista(periodo=self.periodo.pk, pagina="invalid")
        self.assertEqual(response.context["pagina"].number, 1)

    def test_navigation_and_create_keep_semester(self):
        response = self.lista(periodo=self.periodo.pk, pagina=2)
        self.assertContains(
            response, reverse("configurar", args=["clases"]) + f"?periodo={self.periodo.pk}"
        )
        response = self.client.get(
            reverse("crear_configuracion", args=["franjas"]), {"periodo": self.periodo.pk}
        )
        self.assertEqual(response.context["form"].initial["periodo"], self.periodo.pk)

    def test_edit_returns_to_selected_page(self):
        franja = FranjaLaboratorio.objects.get(pk=self.ids[self.periodo.pk][10])
        url = reverse("editar_configuracion", args=["franjas", franja.pk]) + "?pagina=2"
        response = self.client.post(
            url,
            {
                "periodo": self.periodo.pk,
                "laboratorio": self.lab.pk,
                "dia_semana": 1,
                "hora_inicio": franja.hora_inicio.strftime("%H:%M"),
                "hora_fin": franja.hora_fin.strftime("%H:%M"),
                "capacidad": 15,
                "activa": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("configurar", args=["franjas"]) + f"?periodo={self.periodo.pk}&pagina=2",
        )

    def test_delete_keeps_semester(self):
        url = (
            reverse("eliminar_horario", args=["franjas", self.ids[self.periodo.pk][-1]])
            + "?pagina=2"
        )
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("configurar", args=["franjas"]) + f"?periodo={self.periodo.pk}&pagina=2",
        )

    def test_other_configuration_unchanged(self):
        response = self.lista("laboratorios")
        self.assertFalse(response.context["por_semestre"])
        self.assertTrue(response.context["rows"])
