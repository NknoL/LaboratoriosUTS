from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tutorias.laboratorista_views import consultar_agenda
from tutorias.models import (
    EstadoReserva,
    EventoSeguridad,
    FranjaLaboratorio,
    Laboratorio,
    Materia,
    PeriodoAcademico,
    RegistroSeguridad,
    ReservaLaboratorio,
    RolUsuario,
)
from tutorias.services import decidir_solicitud, reservar


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LaboratoristaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fecha = timezone.localdate() + timedelta(days=14)
        if cls.fecha.isoweekday() == 7:
            cls.fecha += timedelta(days=1)
        cls.coord = User.objects.create_superuser("coord", "coord@example.test", "Prueba-12345")
        cls.encargado = User.objects.create_user("encargado", "lab@example.test", "Prueba-12345")
        cls.encargado.perfil.rol = RolUsuario.LABORATORISTA
        cls.encargado.perfil.save()
        cls.alumnos = []
        for n in range(2):
            usuario = User.objects.create_user(
                f"99000{n}",
                f"alumno{n}@correo.uts.edu.co",
                "Prueba-12345",
                first_name=f"Estudiante {n}",
                last_name="Prueba",
            )
            perfil = usuario.perfil
            perfil.cedula = usuario.username
            perfil.programa = "TEC"
            perfil.semestre = 1
            perfil.save()
            cls.alumnos.append(usuario)
        cls.periodo = PeriodoAcademico.objects.create(
            nombre="Semestre QA", fecha_inicio=cls.fecha, fecha_fin=cls.fecha + timedelta(days=60)
        )
        cls.materia = Materia.objects.create(codigo="QA1", nombre="Redes", nivel="TEC", semestre=1)
        cls.lab = Laboratorio.objects.create(nombre="Telecomunicaciones", ubicacion="Aula 1")
        cls.otro_lab = Laboratorio.objects.create(nombre="IoT")
        cls.lab.materias.add(cls.materia)
        cls.otro_lab.materias.add(cls.materia)
        cls.franja = FranjaLaboratorio.objects.create(
            laboratorio=cls.lab,
            periodo=cls.periodo,
            dia_semana=cls.fecha.isoweekday(),
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )
        cls.otra_franja = FranjaLaboratorio.objects.create(
            laboratorio=cls.otro_lab,
            periodo=cls.periodo,
            dia_semana=cls.fecha.isoweekday(),
            hora_inicio=time(9),
            hora_fin=time(9, 45),
        )

    def solicitar(self, n=0, franja=None):
        return reservar(self.alumnos[n], (franja or self.franja).pk, self.materia.pk, self.fecha)

    def aprobar(self, n=0, franja=None):
        reserva = self.solicitar(n, franja)
        decidir_solicitud(self.coord, reserva.pk, "aprobar", "Ingreso autorizado")
        return reserva

    def agenda(self, **filtros):
        return self.client.get(reverse("agenda_laboratorista"), {"fecha": self.fecha, **filtros})

    def datos_cuenta(self, **cambios):
        return {
            "username": "nuevo.encargado",
            "first_name": "Nuevo",
            "last_name": "Encargado",
            "email": "nuevo@example.test",
            "password1": "Acceso-Seguro-734!",
            "password2": "Acceso-Seguro-734!",
            **cambios,
        }

    def test_approval_appears_from_existing_flow_and_cancellation_removes_it(self):
        reserva = self.solicitar()
        self.client.force_login(self.encargado)
        self.assertEqual(self.agenda().context["total_estudiantes"], 0)
        self.client.force_login(self.coord)
        response = self.client.post(
            reverse("resolver_solicitud", args=[reserva.pk]),
            {"decision": "aprobar", "motivo": "Ingreso autorizado"},
        )
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.encargado)
        response = self.client.get(reverse("agenda_laboratorista_datos"), {"fecha": self.fecha})
        self.assertEqual(response.status_code, 200)
        for dato in (
            "Aceptada por el coordinador",
            "Estudiante 0 Prueba",
            "990000",
            "alumno0@correo.uts.edu.co",
            "Redes",
            "Aula 1",
            "Semestre QA",
            "coord",
        ):
            self.assertIn(dato, response.json()["html"])
        self.client.force_login(self.coord)
        self.client.post(reverse("cancelar_reserva", args=[reserva.pk]))
        self.client.force_login(self.encargado)
        self.assertEqual(self.agenda().context["total_estudiantes"], 0)

    def test_pending_and_rejected_are_excluded(self):
        self.solicitar()
        segunda = self.solicitar(1)
        decidir_solicitud(self.coord, segunda.pk, "rechazar", "Sin autorización")
        self.client.force_login(self.encargado)
        self.assertContains(self.agenda(), "No hay préstamos aprobados")

    def test_same_time_and_lab_group_students_without_merging_labs(self):
        self.aprobar(0)
        self.aprobar(1)
        tercera = ReservaLaboratorio.objects.create(
            estudiante=self.alumnos[0],
            franja=self.otra_franja,
            laboratorio=self.otro_lab,
            materia=self.materia,
            fecha=self.fecha,
            hora_inicio=time(9),
            hora_fin=time(9, 45),
            estado=EstadoReserva.CONFIRMADA,
        )
        self.client.force_login(self.encargado)
        response = self.agenda()
        self.assertEqual(response.context["total_estudiantes"], 3)
        self.assertEqual(sorted(len(g["reservas"]) for g in response.context["grupos"]), [1, 2])
        self.assertContains(response, f"#{tercera.pk}")
        filtrada = self.agenda(laboratorio=self.lab.pk)
        self.assertEqual(filtrada.context["total_estudiantes"], 2)
        self.assertEqual(len(filtrada.context["grupos"]), 1)

    def test_different_dates_and_invalid_filters(self):
        self.aprobar()
        self.client.force_login(self.encargado)
        response = self.client.get(
            reverse("agenda_laboratorista"), {"fecha": self.fecha + timedelta(days=1)}
        )
        self.assertEqual(response.context["total_estudiantes"], 0)
        for filtros in ({"fecha": "no"}, {"fecha": self.fecha, "laboratorio": "9" * 5000}):
            for url in ("agenda_laboratorista", "agenda_laboratorista_datos"):
                with self.subTest(url=url, tipo=next(iter(filtros))):
                    self.assertEqual(self.client.get(reverse(url), filtros).status_code, 400)

    def test_status_at_start_and_end_uses_bogota_time(self):
        self.aprobar()
        for hora, esperado in (
            (time(8, 59), "proxima"),
            (time(9), "en_curso"),
            (time(9, 44), "en_curso"),
            (time(9, 45), "finalizada"),
        ):
            instante = timezone.make_aware(datetime.combine(self.fecha, hora))
            with (
                self.subTest(hora=hora),
                patch("tutorias.laboratorista_views.timezone.now", return_value=instante),
            ):
                contexto = consultar_agenda({"fecha": self.fecha.isoformat()})
                self.assertEqual(contexto["grupos"][0]["estado"], esperado)

    def test_agenda_requires_staff_role_and_no_cache(self):
        for url in ("agenda_laboratorista", "agenda_laboratorista_datos"):
            self.assertEqual(self.client.get(reverse(url)).status_code, 302)
        self.client.force_login(self.alumnos[0])
        for url in ("agenda_laboratorista", "agenda_laboratorista_datos"):
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)
        for usuario in (self.encargado, self.coord):
            self.client.force_login(usuario)
            for url in ("agenda_laboratorista", "agenda_laboratorista_datos"):
                response = self.client.get(reverse(url))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])

    def test_laboratorista_cannot_modify_reservations_or_manage_accounts(self):
        reserva = self.solicitar()
        self.client.force_login(self.encargado)
        for url, args in (
            ("resolver_solicitud", [reserva.pk]),
            ("cancelar_reserva", [reserva.pk]),
            ("confirmar_reserva", []),
            ("crear_laboratorista", []),
            ("editar_laboratorista", [self.encargado.pk]),
            ("clave_laboratorista", [self.encargado.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(reverse(url, args=args), {"decision": "aprobar"}).status_code,
                    403,
                )
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, EstadoReserva.PENDIENTE)
        for url in ("solicitudes", "laboratoristas", "estudiantes", "laboratorios", "mis_reservas"):
            self.assertEqual(self.client.get(reverse(url)).status_code, 403)

    def test_dashboard_and_navigation_follow_role(self):
        self.client.force_login(self.encargado)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("agenda_laboratorista"))
        response = self.agenda()
        self.assertNotContains(response, reverse("solicitudes"))
        self.assertNotContains(response, reverse("mis_reservas"))
        self.client.force_login(self.alumnos[0])
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("laboratorios"))
        self.client.force_login(self.coord)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("reportes"))

    def test_names_and_notes_are_escaped_in_html_and_refresh(self):
        reserva = self.aprobar()
        ReservaLaboratorio.objects.filter(pk=reserva.pk).update(
            motivo_decision="<script>alert(1)</script>"
        )
        self.client.force_login(self.encargado)
        self.assertContains(self.agenda(), "&lt;script&gt;")
        html = self.client.get(reverse("agenda_laboratorista_datos"), {"fecha": self.fecha}).json()[
            "html"
        ]
        self.assertNotIn("<script>", html)

    def test_coordinator_creates_account_without_admin_privileges_and_requires_password_change(
        self,
    ):
        self.client.force_login(self.coord)
        response = self.client.post(
            reverse("crear_laboratorista"),
            self.datos_cuenta(is_superuser="1", is_staff="1", rol="COORDINADOR"),
        )
        self.assertRedirects(response, reverse("laboratoristas"))
        usuario = User.objects.get(username="nuevo.encargado")
        self.assertEqual(usuario.perfil.rol, RolUsuario.LABORATORISTA)
        self.assertFalse(usuario.is_superuser)
        self.assertFalse(usuario.is_staff)
        self.assertTrue(usuario.perfil.debe_cambiar_clave)
        self.assertGreater(usuario.perfil.clave_temporal_expira, timezone.now())
        self.assertTrue(
            RegistroSeguridad.objects.filter(
                usuario=usuario, actor=self.coord, evento=EventoSeguridad.CLAVE_TEMPORAL
            ).exists()
        )
        self.client.logout()
        self.assertEqual(
            self.client.post(
                reverse("login"),
                {
                    "username": usuario.username,
                    "password": "Acceso-Seguro-734!",
                },
            ).status_code,
            302,
        )
        self.assertRedirects(
            self.client.get(reverse("agenda_laboratorista")), reverse("cambiar_clave")
        )
        response = self.client.post(
            reverse("cambiar_clave"),
            {
                "old_password": "Acceso-Seguro-734!",
                "new_password1": "Personal-Nueva-384!",
                "new_password2": "Personal-Nueva-384!",
            },
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("agenda_laboratorista"))
        usuario.perfil.refresh_from_db()
        self.assertFalse(usuario.perfil.debe_cambiar_clave)

    def test_account_validation_duplicate_email_username_password_and_required_fields(self):
        self.client.force_login(self.coord)
        for cambios, campo in (
            ({"email": " LAB@EXAMPLE.TEST "}, "email"),
            ({"username": "ENCARGADO"}, "username"),
            ({"first_name": ""}, "first_name"),
            ({"password2": "diferente"}, "password2"),
            ({"password1": "123", "password2": "123"}, "password2"),
        ):
            with self.subTest(campo=campo):
                response = self.client.post(
                    reverse("crear_laboratorista"), self.datos_cuenta(**cambios)
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(campo, response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="nuevo.encargado").exists())

    def test_existing_student_cedula_cannot_become_lab_username(self):
        self.alumnos[0].perfil.cedula = "889900"
        self.alumnos[0].perfil.save()
        self.client.force_login(self.coord)
        response = self.client.post(
            reverse("crear_laboratorista"), self.datos_cuenta(username="889900")
        )
        self.assertIn("username", response.context["form"].errors)

    def test_account_edit_and_deactivation_block_existing_session(self):
        otro_cliente = Client()
        otro_cliente.force_login(self.encargado)
        self.client.force_login(self.coord)
        response = self.client.post(
            reverse("editar_laboratorista", args=[self.encargado.pk]),
            {
                "first_name": "Persona",
                "last_name": "Encargada",
                "email": "lab@example.test",
                "is_staff": "1",
                "rol": "COORDINADOR",
            },
        )
        self.assertRedirects(response, reverse("laboratoristas"))
        self.encargado.refresh_from_db()
        self.assertFalse(self.encargado.is_active)
        self.assertFalse(self.encargado.is_staff)
        self.assertEqual(self.encargado.perfil.rol, RolUsuario.LABORATORISTA)
        self.assertEqual(otro_cliente.get(reverse("agenda_laboratorista_datos")).status_code, 302)

    def test_cannot_edit_student_or_coordinator_from_lab_account_routes(self):
        self.client.force_login(self.coord)
        for usuario in (self.coord, self.alumnos[0]):
            for url in ("editar_laboratorista", "clave_laboratorista"):
                self.assertEqual(
                    self.client.post(reverse(url, args=[usuario.pk]), {}).status_code, 404
                )
        self.client.force_login(self.alumnos[0])
        self.assertEqual(
            self.client.post(reverse("crear_laboratorista"), self.datos_cuenta()).status_code, 403
        )

    def test_password_reset_invalidates_session_and_expired_password_is_rejected(self):
        otro_cliente = Client()
        otro_cliente.force_login(self.encargado)
        self.client.force_login(self.coord)
        self.assertRedirects(
            self.client.post(
                reverse("clave_laboratorista", args=[self.encargado.pk]),
                {
                    "new_password1": "Otra-Clave-348!",
                    "new_password2": "Otra-Clave-348!",
                },
            ),
            reverse("laboratoristas"),
        )
        self.assertEqual(otro_cliente.get(reverse("agenda_laboratorista")).status_code, 302)
        perfil = self.encargado.perfil
        perfil.refresh_from_db()
        self.assertTrue(perfil.debe_cambiar_clave)
        perfil.clave_temporal_expira = timezone.now() - timedelta(minutes=1)
        perfil.save()
        response = otro_cliente.post(
            reverse("login"),
            {
                "username": self.encargado.username,
                "password": "Otra-Clave-348!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", otro_cliente.session)

    def test_csrf_required_on_account_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.coord)
        for url, args in (
            ("crear_laboratorista", []),
            ("editar_laboratorista", [self.encargado.pk]),
            ("clave_laboratorista", [self.encargado.pk]),
        ):
            self.assertEqual(client.post(reverse(url, args=args), {}).status_code, 403)

    def test_public_registration_ignores_requested_privileges(self):
        response = self.client.post(
            reverse("registro_estudiante"),
            {
                "cedula": "789123",
                "first_name": "Alumno",
                "last_name": "Prueba",
                "email": "seguro@correo.uts.edu.co",
                "programa": "TEC",
                "semestre": 1,
                "password1": "Personal-Nueva-384!",
                "password2": "Personal-Nueva-384!",
                "rol": "LABORATORISTA",
                "is_staff": "1",
                "is_superuser": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="789123")
        self.assertEqual(user.perfil.rol, RolUsuario.ESTUDIANTE)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
