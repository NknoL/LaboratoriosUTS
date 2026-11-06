import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.views import defaults

from tutorias.views import id_consulta
from tutorias_uts.logging import FormatoPrivado


class ConfiguracionProduccionTests(SimpleTestCase):
    def comprobar(self, **cambios):
        entorno = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("DJANGO_", "UTS_", "DATABASE_URL", "DB_"))
        }
        entorno.update(
            DJANGO_ENV="production",
            DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
            DJANGO_ALLOWED_HOSTS="laboratorios.example.test",
            DATABASE_URL="mysql://app:solo_prueba@127.0.0.1:3306/no_conectar",
            UTS_ENV_FILE=os.devnull,
            PYTHONDONTWRITEBYTECODE="1",
        )
        entorno.update(cambios)
        return subprocess.run(
            [sys.executable, "-c", "import tutorias_uts.settings"],
            cwd=settings.BASE_DIR,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_valid_configuration_loads_without_database_connection(self):
        result = self.comprobar()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsafe_configuration_fails_closed(self):
        casos = [
            {"DJANGO_ENV": "produccion"},
            {"DJANGO_SECRET_KEY": ""},
            {"DJANGO_SECRET_KEY": "corta"},
            {"DJANGO_SECRET_KEY": "a" * 80},
            {"DJANGO_ALLOWED_HOSTS": ""},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DATABASE_URL": ""},
            {"DATABASE_URL": "sqlite:///local.sqlite3"},
            {"DATABASE_URL": "mysql://root:clave@127.0.0.1/db"},
            {"DATABASE_URL": "mysql://app@127.0.0.1/db"},
            {"UTS_EMAIL_TLS": "1", "UTS_EMAIL_SSL": "1"},
            {"UTS_ENV_FILE": str(Path(__file__).with_name("no-existe-configuracion.env"))},
        ]
        for cambio in casos:
            with self.subTest(configuracion=list(cambio)):
                result = self.comprobar(**cambio)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_local_development_still_allows_local_root(self):
        result = self.comprobar(
            DJANGO_ENV="development", DATABASE_URL="mysql://root:local@127.0.0.1/db"
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class ErroresProduccionTests(SimpleTestCase):
    def test_query_ids_are_bounded(self):
        for value in ("", "-1", "0", "9" * 5000, "１", "nan"):
            self.assertIsNone(id_consulta(value))
        self.assertEqual(id_consulta("123"), 123)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_error_pages_render_without_user_or_database(self):
        request = RequestFactory().get("/inexistente/")
        for view, status in (
            (defaults.bad_request, 400),
            (defaults.permission_denied, 403),
            (defaults.page_not_found, 404),
        ):
            with self.subTest(status=status):
                response = view(request, ValueError("dato-confidencial"))
                self.assertEqual(response.status_code, status)
                self.assertIn(b"Laboratorios UTS", response.content)
                self.assertNotIn(b"dato-confidencial", response.content)
        self.assertEqual(defaults.server_error(request).status_code, 500)

    def test_http_log_does_not_include_url_or_exception_value(self):
        try:
            raise ValueError("clave-confidencial")
        except ValueError:
            record = logging.LogRecord(
                "django.request",
                logging.ERROR,
                __file__,
                1,
                "Error: %s",
                ("/cuentas/restablecer/token-secreto/",),
                sys.exc_info(),
            )
        record.status_code = 500
        salida = FormatoPrivado("%(message)s").format(record)
        self.assertIn("500", salida)
        self.assertIn("ValueError", salida)
        self.assertNotIn("clave-confidencial", salida)
        self.assertNotIn("token-secreto", salida)
        self.assertEqual(record.msg, "Error: %s")
