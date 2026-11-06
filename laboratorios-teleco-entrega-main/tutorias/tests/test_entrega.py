import io
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from tutorias.management.commands import exportar_entrega


class ExportacionEntregaTests(SimpleTestCase):
    def test_requires_explicit_acknowledgment(self):
        with self.assertRaisesMessage(CommandError, "--confirmar-copia-admin"):
            exportar_entrega.Command().handle(confirmar_copia_admin=False)

    def test_rejects_sqlite(self):
        with patch.object(exportar_entrega, "connection", SimpleNamespace(vendor="sqlite")):
            with self.assertRaisesMessage(CommandError, "MySQL/MariaDB"):
                exportar_entrega.Command().handle(confirmar_copia_admin=True)

    def test_rejects_demo_password_before_writing(self):
        user = SimpleNamespace(has_usable_password=lambda: True, check_password=lambda _: True)
        with (
            patch.object(exportar_entrega, "connection", SimpleNamespace(vendor="mysql")),
            patch.object(exportar_entrega.User.objects, "get", return_value=user),
            self.assertRaisesMessage(CommandError, "Cambia primero la clave"),
        ):
            exportar_entrega.Command().handle(confirmar_copia_admin=True)

    def test_admin_export_omits_contacts_and_requires_password_change(self):
        user = SimpleNamespace(
            pk=1,
            username="admin",
            password="hash_de_prueba",
            date_joined=datetime(2026, 1, 1, tzinfo=timezone.utc),
            email="privado@example.invalid",
            first_name="Nombre privado",
        )
        db = MagicMock()
        cursor = db.connection.cursor.return_value.__enter__.return_value
        cursor.mogrify.side_effect = lambda sql, params: sql
        with patch.object(exportar_entrega, "connection", db):
            exportar_entrega.Command().escribir_admin(io.BytesIO(), user)
        llamadas = cursor.mogrify.call_args_list
        self.assertEqual(len(llamadas), 2)
        self.assertNotIn(user.email, repr(llamadas))
        self.assertNotIn(user.first_name, repr(llamadas))
        self.assertIn("debe_cambiar_clave", llamadas[1].args[0])
        self.assertIn("NULL,NULL,1,NULL", llamadas[1].args[0])

    def test_data_whitelist_excludes_private_tables(self):
        self.assertFalse(
            {"auth_user", "django_session", "tutorias_reservalaboratorio", "tutorias_perfilusuario"}
            & set(exportar_entrega.TABLAS_DATOS)
        )
