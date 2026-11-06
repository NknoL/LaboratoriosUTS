#!/usr/bin/env python
"""Punto de entrada para la administracion del aplicativo."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tutorias_uts.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Activa el entorno virtual e instala requirements.txt."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
