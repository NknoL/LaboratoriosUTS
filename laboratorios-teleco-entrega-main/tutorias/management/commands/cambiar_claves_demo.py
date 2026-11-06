from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Guia privada para cambiar unicamente las claves conocidas de demostracion."

    def handle(self, *args, **options):
        if not self.stdout.isatty():
            raise CommandError(
                "Ejecuta este comando directamente en tu terminal privada, sin redirigir la salida."
            )
        claves = ("Admin12345*", "Coord12345*", "Estudiante12345*")
        encontrados = 0
        for usuario in User.objects.filter(is_active=True):
            if any(usuario.check_password(clave) for clave in claves):
                encontrados += 1
                self.stdout.write(f"Cuenta con clave de ejemplo: {usuario.username}")
                self.stdout.write(
                    "La nueva clave se escribe dos veces y no se muestra. Cancela con Ctrl+C para detenerte."
                )
                call_command("changepassword", usuario.username)
        if not encontrados:
            self.stdout.write("No se encontraron claves conocidas de demostracion.")
        call_command("verificar_publicacion")
