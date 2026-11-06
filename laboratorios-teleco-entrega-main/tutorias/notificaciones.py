"""Avisos a coordinación cuando un estudiante crea una solicitud de laboratorio.

Canales:
- Correo (SMTP institucional, Gmail, Brevo...) a UTS_NOTIFICAR_CORREOS o a los coordinadores activos.
- Telegram (opcional, gratuito, llega al celular al instante) con UTS_TELEGRAM_BOT_TOKEN y UTS_TELEGRAM_CHAT_ID.

El envío ocurre después de guardar la solicitud (transaction.on_commit) y en un hilo aparte:
el estudiante recibe su respuesta de inmediato y un fallo del correo nunca anula la reserva.
"""

import json
import logging
import threading
from datetime import timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import AvisoReserva, ReservaLaboratorio, RolUsuario

logger = logging.getLogger("tutorias.notificaciones")

CORREO_LOCAL = (
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
)


def destinatarios():
    if settings.NOTIFICAR_CORREOS:
        return list(settings.NOTIFICAR_CORREOS)
    correos = (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(perfil__rol=RolUsuario.COORDINADOR))
        .exclude(email="")
        .values_list("email", flat=True)
    )
    return sorted({c.strip().lower() for c in correos if c.strip()})


def correo_configurado():
    if not settings.DEFAULT_FROM_EMAIL:
        return False
    if settings.EMAIL_BACKEND == "tutorias.email_backend.BrevoBackend":
        return bool(settings.BREVO_API_KEY)
    if settings.EMAIL_BACKEND in CORREO_LOCAL:
        return True
    return bool(settings.EMAIL_HOST)


def telegram_configurado():
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def enviar_telegram(texto):
    request = Request(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        data=json.dumps(
            {"chat_id": settings.TELEGRAM_CHAT_ID, "text": texto, "disable_web_page_preview": True}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise OSError("Telegram no aceptó el mensaje.")


def enviar_aviso_solicitud(reserva_id, canales=None):
    """Envía el aviso por todos los canales configurados. Devuelve {canal: resultado}."""
    ReservaLaboratorio.objects.only("pk").get(pk=reserva_id)
    resultados = {}
    para = destinatarios()
    if (canales is None or "correo" in canales) and correo_configurado() and para:
        asunto = "Nueva reserva de laboratorio"
        mensaje = EmailMultiAlternatives(
            asunto,
            render_to_string("tutorias/correo/nueva_solicitud.txt"),
            settings.DEFAULT_FROM_EMAIL,
            para,
        )
        mensaje.attach_alternative(
            render_to_string("tutorias/correo/nueva_solicitud.html"), "text/html"
        )
        try:
            if mensaje.send() != 1:
                raise OSError("Mensaje no aceptado")
            resultados["correo"] = f"enviado a {', '.join(para)}"
        except Exception:
            logger.error("No fue posible enviar el correo de la solicitud %s.", reserva_id)
            resultados["correo"] = "error"
    else:
        resultados["correo"] = "sin configurar"
    if (canales is None or "telegram" in canales) and telegram_configurado():
        try:
            enviar_telegram(
                render_to_string("tutorias/correo/nueva_solicitud_telegram.txt").strip()
            )
            resultados["telegram"] = "enviado"
        except (URLError, OSError):
            logger.error(
                "No fue posible enviar el aviso de Telegram de la solicitud %s.", reserva_id
            )
            resultados["telegram"] = "error"
    else:
        resultados["telegram"] = "sin configurar"
    logger.info("Aviso de solicitud %s procesado.", reserva_id)
    return resultados


def procesar_aviso(reserva_id):
    now = timezone.now()
    lease = now + timedelta(minutes=2)
    disponibles = AvisoReserva.objects.filter(
        reserva_id=reserva_id,
        completado__isnull=True,
        proximo_intento__lte=now,
    ).filter(Q(bloqueo_hasta__isnull=True) | Q(bloqueo_hasta__lte=now))
    # La actualizacion condicional permite varios procesos sin enviar el mismo aviso a la vez.
    if not disponibles.update(bloqueo_hasta=lease, intentos=F("intentos") + 1):
        return False
    aviso = AvisoReserva.objects.get(reserva_id=reserva_id)
    canales = []
    if not aviso.correo_enviado:
        canales.append("correo")
    if telegram_configurado() and not aviso.telegram_enviado:
        canales.append("telegram")
    try:
        resultados = enviar_aviso_solicitud(reserva_id, canales)
    except Exception:
        logger.error("Fallo al procesar aviso %s; se reintentara.", reserva_id)
        resultados = {}
    correo = aviso.correo_enviado or resultados.get("correo", "").startswith("enviado")
    telegram = aviso.telegram_enviado or resultados.get("telegram") == "enviado"
    completo = correo and (not telegram_configurado() or telegram)
    AvisoReserva.objects.filter(pk=aviso.pk, bloqueo_hasta=lease).update(
        correo_enviado=correo,
        telegram_enviado=telegram,
        completado=timezone.now() if completo else None,
        bloqueo_hasta=None,
        proximo_intento=timezone.now()
        + timedelta(seconds=min(300, 15 * 2 ** min(aviso.intentos - 1, 5))),
        ultimo_error="" if completo else "Canal pendiente: revisar configuracion o proveedor",
    )
    return True


def procesar_pendientes(limite=100):
    now = timezone.now()
    ids = list(
        AvisoReserva.objects.filter(completado__isnull=True, proximo_intento__lte=now)
        .filter(Q(bloqueo_hasta__isnull=True) | Q(bloqueo_hasta__lte=now))
        .order_by("proximo_intento")
        .values_list("reserva_id", flat=True)[:limite]
    )
    return sum(procesar_aviso(pk) for pk in ids)


def _enviar_seguro(reserva_id):
    try:
        procesar_aviso(reserva_id)
    except Exception:
        logger.error("Aviso %s pendiente; el trabajador volvera a intentarlo.", reserva_id)


def _en_segundo_plano(reserva_id):
    try:
        _enviar_seguro(reserva_id)
    finally:
        connection.close()  # El hilo tiene su propia conexión a la base.


def avisar_nueva_solicitud(reserva):
    """Llamar dentro de la transacción que crea la reserva; el aviso sale solo si se confirma."""
    _, nuevo = AvisoReserva.objects.get_or_create(reserva=reserva)
    if not nuevo:
        return

    def despachar():
        if settings.NOTIFICACIONES_EN_SEGUNDO_PLANO:
            try:
                threading.Thread(
                    target=_en_segundo_plano,
                    args=(reserva.pk,),
                    daemon=True,
                    name=f"aviso-solicitud-{reserva.pk}",
                ).start()
            except RuntimeError:
                logger.error(
                    "Aviso %s guardado; no se pudo iniciar el envio inmediato.", reserva.pk
                )
        else:
            _enviar_seguro(reserva.pk)

    transaction.on_commit(despachar, robust=True)
