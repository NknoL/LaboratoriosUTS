"""Clave temporal entregada por coordinación, cambio obligatorio y bitácora de contraseñas."""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .acceso import direccion_cliente
from .db_lock import escritura_atomica
from .forms import EstiloForm
from .models import EventoSeguridad, PerfilUsuario, RegistroSeguridad, RolUsuario, es_coordinador

logger = logging.getLogger("tutorias.seguridad")

# Sin letras ni números que se confundan al dictarlos (0/O, 1/l/I).
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def generar_clave_temporal(longitud=10):
    while True:
        clave = "".join(secrets.choice(ALFABETO) for _ in range(longitud))
        if (
            any(c.isdigit() for c in clave)
            and any(c.isupper() for c in clave)
            and any(c.islower() for c in clave)
        ):
            return clave


def ip_cliente(request):
    return direccion_cliente(request) if request else None


def registrar(usuario, evento, request=None, actor=None):
    RegistroSeguridad.objects.create(
        usuario=usuario,
        usuario_nombre=usuario.username,
        actor=actor,
        evento=evento,
        ip=ip_cliente(request),
    )
    logger.info(
        "Seguridad: %s · usuario_id=%s · actor_id=%s",
        evento,
        usuario.pk,
        getattr(actor, "pk", "-"),
    )


def limpiar_clave_temporal(usuario):
    PerfilUsuario.objects.filter(usuario=usuario).update(
        debe_cambiar_clave=False, clave_temporal_expira=None
    )


def clave_temporal_vencida(usuario):
    perfil = getattr(usuario, "perfil", None)
    return bool(
        perfil
        and perfil.debe_cambiar_clave
        and perfil.clave_temporal_expira
        and perfil.clave_temporal_expira <= timezone.now()
    )


@escritura_atomica()
def asignar_clave_temporal(coordinador, perfil_id, request=None):
    if not es_coordinador(coordinador):
        raise PermissionDenied
    perfil = PerfilUsuario.objects.select_related("usuario").get(pk=perfil_id)
    usuario = perfil.usuario
    if perfil.rol != RolUsuario.ESTUDIANTE or usuario.is_superuser or not usuario.is_active:
        raise PermissionDenied
    clave = generar_clave_temporal()
    usuario.set_password(clave)  # Cierra también las sesiones abiertas del estudiante.
    usuario.save(update_fields=["password"])
    perfil.debe_cambiar_clave = True
    perfil.clave_temporal_expira = timezone.now() + timedelta(hours=settings.CLAVE_TEMPORAL_HORAS)
    perfil.save(update_fields=["debe_cambiar_clave", "clave_temporal_expira"])
    registrar(usuario, EventoSeguridad.CLAVE_TEMPORAL, request, actor=coordinador)
    return perfil, clave


class ClaveTemporalMiddleware:
    """Quien entra con una clave temporal solo puede cambiarla o cerrar sesión."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            perfil = getattr(user, "perfil", None)
            if perfil is not None and perfil.debe_cambiar_clave:
                permitidas = (reverse("cambiar_clave"), reverse("logout"))
                if request.path not in permitidas and not request.path.startswith(
                    "/" + settings.STATIC_URL.lstrip("/")
                ):
                    return redirect("cambiar_clave")
        return self.get_response(request)


class CambiarClaveForm(EstiloForm, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual (o clave temporal)"
        self.estilo()


@login_required
@never_cache
def cambiar_clave(request):
    obligatorio = bool(getattr(getattr(request.user, "perfil", None), "debe_cambiar_clave", False))
    form = CambiarClaveForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with escritura_atomica():
            user = form.save()
            limpiar_clave_temporal(user)
            registrar(user, EventoSeguridad.CAMBIO_CLAVE, request, actor=user)
        update_session_auth_hash(request, user)
        messages.success(request, "Tu contraseña fue actualizada.")
        return redirect("dashboard")
    return render(
        request, "tutorias/cambiar_clave.html", {"form": form, "obligatorio": obligatorio}
    )


@require_POST
@never_cache
def clave_temporal(request, pk):
    if not request.user.is_authenticated or not es_coordinador(request.user):
        raise PermissionDenied
    get_object_or_404(PerfilUsuario, pk=pk, rol=RolUsuario.ESTUDIANTE)
    perfil, clave = asignar_clave_temporal(request.user, pk, request)
    # Se muestra una sola vez en esta respuesta: no se guarda en mensajes, cookies ni registros.
    response = render(
        request,
        "tutorias/clave_temporal.html",
        {"estudiante": perfil, "clave": clave, "horas": settings.CLAVE_TEMPORAL_HORAS},
    )
    response["Cache-Control"] = "no-store"
    return response
