import logging
from datetime import datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from .db_lock import escritura_atomica
from .laboratorista_forms import (
    AgendaLaboratoristaForm,
    ClaveLaboratoristaForm,
    CrearLaboratoristaForm,
    EditarLaboratoristaForm,
)
from .models import (
    EstadoReserva,
    EventoSeguridad,
    ReservaLaboratorio,
    RolUsuario,
    es_coordinador,
    es_laboratorista,
)
from .seguridad import registrar
from .views import solo_coordinador

logger = logging.getLogger("tutorias.seguridad")


def acceso_agenda(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_laboratorista(request.user) and not es_coordinador(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def consultar_agenda(params):
    datos = params.copy()
    if "fecha" not in datos:
        datos["fecha"] = timezone.localdate().isoformat()
    form = AgendaLaboratoristaForm(datos)
    contexto = {"form": form, "grupos": [], "total_estudiantes": 0}
    if not form.is_valid():
        return contexto

    fecha = form.cleaned_data["fecha"]
    reservas = ReservaLaboratorio.objects.filter(
        fecha=fecha, activa=True, estado=EstadoReserva.CONFIRMADA
    ).select_related(
        "estudiante__perfil", "laboratorio", "materia", "franja__periodo", "decidida_por"
    )
    if form.cleaned_data["laboratorio"]:
        reservas = reservas.filter(laboratorio=form.cleaned_data["laboratorio"])

    ahora = timezone.localtime().replace(tzinfo=None)
    grupos = {}
    for reserva in reservas.order_by(
        "hora_inicio",
        "laboratorio__nombre",
        "laboratorio_id",
        "hora_fin",
        "estudiante__first_name",
        "estudiante__last_name",
        "pk",
    ):
        clave = (reserva.laboratorio_id, reserva.hora_inicio, reserva.hora_fin)
        if clave not in grupos:
            inicio = datetime.combine(fecha, reserva.hora_inicio)
            fin = datetime.combine(fecha, reserva.hora_fin)
            estado = "finalizada" if ahora >= fin else "en_curso" if ahora >= inicio else "proxima"
            grupos[clave] = {
                "id": f"turno-{reserva.laboratorio_id}-{fecha:%Y%m%d}"
                f"-{reserva.hora_inicio:%H%M%S}-{reserva.hora_fin:%H%M%S}",
                "laboratorio": reserva.laboratorio,
                "hora_inicio": reserva.hora_inicio,
                "hora_fin": reserva.hora_fin,
                "estado": estado,
                "estado_nombre": {
                    "finalizada": "Finalizada",
                    "en_curso": "En curso",
                    "proxima": "Próxima",
                }[estado],
                "reservas": [],
            }
        grupos[clave]["reservas"].append(reserva)
        contexto["total_estudiantes"] += 1

    contexto.update(fecha=fecha, grupos=list(grupos.values()))
    return contexto


@never_cache
@acceso_agenda
@require_GET
def agenda_laboratorista(request):
    contexto = consultar_agenda(request.GET)
    return render(
        request,
        "tutorias/laboratorista/agenda.html",
        contexto,
        status=200 if contexto["form"].is_valid() else 400,
    )


@never_cache
@acceso_agenda
@require_GET
def agenda_laboratorista_datos(request):
    contexto = consultar_agenda(request.GET)
    if not contexto["form"].is_valid():
        return JsonResponse({"error": "Selecciona una fecha y un laboratorio válidos."}, status=400)
    return JsonResponse(
        {
            "html": render_to_string(
                "tutorias/laboratorista/agenda_contenido.html", contexto, request
            ),
            "actualizado": timezone.localtime().strftime("%H:%M:%S"),
        }
    )


def cuentas_laboratoristas():
    return (
        User.objects.filter(
            perfil__rol=RolUsuario.LABORATORISTA, is_superuser=False, is_staff=False
        )
        .select_related("perfil")
        .order_by("first_name", "last_name", "username")
    )


@never_cache
@solo_coordinador
@require_GET
def laboratoristas(request):
    pagina = Paginator(cuentas_laboratoristas(), 25).get_page(request.GET.get("page"))
    return render(request, "tutorias/laboratorista/cuentas.html", {"pagina": pagina})


def marcar_clave_temporal(usuario, request):
    perfil = usuario.perfil
    perfil.debe_cambiar_clave = True
    perfil.clave_temporal_expira = timezone.now() + timedelta(hours=settings.CLAVE_TEMPORAL_HORAS)
    perfil.save(update_fields=["debe_cambiar_clave", "clave_temporal_expira"])
    registrar(usuario, EventoSeguridad.CLAVE_TEMPORAL, request, actor=request.user)


@sensitive_post_parameters("password1", "password2")
@never_cache
@solo_coordinador
@require_http_methods(["GET", "POST"])
def crear_laboratorista(request):
    form = CrearLaboratoristaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with escritura_atomica():
                usuario = form.save()
                perfil = usuario.perfil
                perfil.rol = RolUsuario.LABORATORISTA
                perfil.save(update_fields=["rol"])
                marcar_clave_temporal(usuario, request)
        except IntegrityError:
            form.add_error(None, "El usuario o el correo ya está en uso. Revisa los datos.")
        else:
            messages.success(
                request,
                "Cuenta de laboratorista creada. Entrega sus datos de acceso de forma privada.",
            )
            return redirect("laboratoristas")
    return render(
        request,
        "tutorias/laboratorista/cuenta_form.html",
        {
            "form": form,
            "titulo": "Crear laboratorista",
            "clave_temporal": True,
            "horas": settings.CLAVE_TEMPORAL_HORAS,
        },
    )


@never_cache
@solo_coordinador
@require_http_methods(["GET", "POST"])
def editar_laboratorista(request, pk):
    # Bloquea la cuenta durante el guardado para no sobrescribir cambios simultaneos.
    with escritura_atomica():
        usuario = get_object_or_404(cuentas_laboratoristas().select_for_update(), pk=pk)
        form = EditarLaboratoristaForm(
            request.POST if request.method == "POST" else None, instance=usuario
        )
        if request.method == "POST" and form.is_valid():
            try:
                with escritura_atomica():
                    form.save()
            except IntegrityError:
                form.add_error("email", "Este correo ya está en uso")
            else:
                logger.info(
                    "Cuenta de laboratorista actualizada: usuario_id=%s actor_id=%s activa=%s",
                    usuario.pk,
                    request.user.pk,
                    usuario.is_active,
                )
                messages.success(request, "Cuenta de laboratorista actualizada.")
                return redirect("laboratoristas")
    return render(
        request,
        "tutorias/laboratorista/cuenta_form.html",
        {
            "form": form,
            "titulo": "Editar laboratorista",
            "cuenta": usuario,
        },
    )


@sensitive_post_parameters("new_password1", "new_password2")
@never_cache
@solo_coordinador
@require_http_methods(["GET", "POST"])
def clave_laboratorista(request, pk):
    with escritura_atomica():
        usuario = get_object_or_404(cuentas_laboratoristas().select_for_update(), pk=pk)
        form = ClaveLaboratoristaForm(usuario, request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            form.save()
            marcar_clave_temporal(usuario, request)
            messages.success(
                request, "Contraseña temporal actualizada. Entrega la nueva clave de forma privada."
            )
            return redirect("laboratoristas")
    return render(
        request,
        "tutorias/laboratorista/cuenta_form.html",
        {
            "form": form,
            "titulo": "Restablecer acceso",
            "cuenta": usuario,
            "clave_temporal": True,
            "horas": settings.CLAVE_TEMPORAL_HORAS,
        },
    )
