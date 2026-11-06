import json
import logging
from email.utils import parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoBackend(BaseEmailBackend):
    """HTTPS mail transport; credentials and message bodies never enter logs."""

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            try:
                if not settings.BREVO_API_KEY:
                    raise OSError("Falta configurar el servicio de correo.")
                name, address = parseaddr(message.from_email)
                payload = {
                    "sender": {"email": address, "name": name or "Laboratorios UTS"},
                    "to": [{"email": parseaddr(item)[1]} for item in message.to],
                    "subject": message.subject,
                    "textContent": message.body,
                }
                for content, mimetype in getattr(message, "alternatives", []) or []:
                    if mimetype == "text/html":
                        payload["htmlContent"] = content
                request = Request(
                    "https://api.brevo.com/v3/smtp/email",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "api-key": settings.BREVO_API_KEY,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    if response.status != 201:
                        raise OSError("El servicio no aceptó el correo.")
                sent += 1
            except (HTTPError, URLError, OSError):
                logging.getLogger(__name__).error(
                    "Fallo de envío HTTPS. Revisa el proveedor de correo."
                )
                if not self.fail_silently:
                    raise OSError("No fue posible enviar el correo.") from None
        return sent
