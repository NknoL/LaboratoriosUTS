from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from axes.models import AccessAttempt
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tutorias.acceso import direccion_cliente


class ProteccionAccesoTests(TestCase):
    def setUp(self):
        self.clave = "ClavePrueba-NoReal-632#"
        self.user = User.objects.create_user("estudiante_qa", "qa@example.test", self.clave)
        perfil = self.user.perfil
        perfil.cedula = "90123456"
        perfil.save()

    def ingresar(self, username="estudiante_qa", password="incorrecta", ip="192.0.2.15"):
        return self.client.post(
            reverse("login"), {"username": username, "password": password}, REMOTE_ADDR=ip
        )

    def test_lockout_alias_and_cooloff(self):
        for _ in range(5):
            response = self.ingresar()
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "15 minutos", status_code=429)
        self.assertEqual(self.ingresar("90123456", self.clave).status_code, 429)
        self.assertEqual(self.ingresar("ESTUDIANTE_QA", self.clave).status_code, 429)
        AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.ingresar(password=self.clave).status_code, 302)
        self.assertFalse(AccessAttempt.objects.exists())

    def test_does_not_lock_other_students_sharing_ip(self):
        for _ in range(5):
            self.ingresar()
        User.objects.create_user("otro_qa", "otro@example.test", self.clave)
        self.assertEqual(self.ingresar("otro_qa", self.clave).status_code, 302)

    def test_password_not_saved_in_attempt(self):
        self.ingresar(password="nunca-guardar-este-valor")
        attempt = AccessAttempt.objects.get()
        self.assertNotIn("nunca-guardar-este-valor", attempt.post_data)
        self.assertNotIn(self.user.username, attempt.post_data)

    def test_registration_still_starts_session(self):
        response = self.client.post(
            reverse("registro_estudiante"),
            {
                "cedula": "90223344",
                "first_name": "Prueba",
                "last_name": "Registro",
                "email": "registroqa@correo.uts.edu.co",
                "programa": "TEC",
                "semestre": 2,
                "password1": self.clave,
                "password2": self.clave,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    @override_settings(PRODUCTION=True)
    def test_only_loopback_proxy_can_supply_client_ip(self):
        factory = RequestFactory()
        request = factory.get("/", REMOTE_ADDR="192.0.2.20", HTTP_X_FORWARDED_FOR="198.51.100.3")
        self.assertEqual(direccion_cliente(request), "192.0.2.20")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.assertEqual(direccion_cliente(request), "198.51.100.3")
        request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.3, 192.0.2.20"
        self.assertEqual(direccion_cliente(request), "127.0.0.1")

    def test_demo_wizard_does_not_change_password_noninteractively(self):
        before = self.user.password
        with self.assertRaises(CommandError):
            call_command("cambiar_claves_demo", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertEqual(before, self.user.password)

    def test_production_check_rejects_development(self):
        with self.assertRaisesMessage(CommandError, "desarrollo"):
            call_command("verificar_publicacion", produccion=True)

    def test_health_check_does_not_send_messages(self):
        output = StringIO()
        with patch("django.core.mail.send_mail") as enviar:
            call_command("comprobar_operacion", stdout=output)
        self.assertIn('"base": "ok"', output.getvalue())
        enviar.assert_not_called()
