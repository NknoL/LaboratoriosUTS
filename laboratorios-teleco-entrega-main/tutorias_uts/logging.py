"""Registros operativos sin URL, tokens ni valores de excepciones HTTP."""

import copy
import logging
import traceback


class FormatoPrivado(logging.Formatter):
    def format(self, record):
        record = copy.copy(record)
        record.exc_text = None
        if record.name.startswith(("django.request", "django.security")):
            record.msg = "Respuesta HTTP %s"
            record.args = (getattr(record, "status_code", "-"),)
        elif record.name.startswith("axes"):
            record.msg = "Control de acceso: evento de seguridad"
            record.args = ()
        return super().format(record)

    def formatException(self, exc_info):
        # Conserva archivo y línea para diagnosticar, sin mensajes SQL ni datos del usuario.
        frames = traceback.extract_tb(exc_info[2])
        locations = "\n".join(
            f"  {frame.filename}:{frame.lineno} ({frame.name})" for frame in frames
        )
        return f"{locations}\n{exc_info[0].__name__}"
