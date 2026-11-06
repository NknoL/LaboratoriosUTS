"""Identidad y origen usados para limitar intentos de inicio de sesion."""

from ipaddress import ip_address

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q


def direccion_cliente(request):
    try:
        origen = ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None
    # Gunicorn solo escucha en loopback; Nginx sobrescribe esta cabecera.
    if settings.PRODUCTION and origen.is_loopback:
        try:
            return str(ip_address(request.META.get("HTTP_X_FORWARDED_FOR", "")))
        except ValueError:
            pass
    return str(origen)


def identidad_acceso(request, credentials=None):
    datos = credentials if credentials is not None else request.POST
    nombre = str(datos.get("username", "")).strip()[:150]
    usuario = (
        User.objects.filter(Q(username__iexact=nombre) | Q(perfil__cedula=nombre))
        .values_list("username", flat=True)
        .first()
    )
    return (usuario or nombre).casefold()
