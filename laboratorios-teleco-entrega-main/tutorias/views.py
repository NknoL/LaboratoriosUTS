from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .db_lock import escritura_atomica
from .forms import (
    ClaseForm,
    ConfirmacionForm,
    CopiarHorarioForm,
    DatosEstudianteForm,
    FechaForm,
    FranjaForm,
    GenerarFranjasForm,
    LaboratorioForm,
    MateriaForm,
    PeriodoForm,
    RegistroEstudianteForm,
    RevisionForm,
)
from .models import (
    EstadoReserva,
    FranjaLaboratorio,
    GeneracionFranjas,
    HorarioClase,
    Laboratorio,
    Materia,
    PerfilUsuario,
    PeriodoAcademico,
    ReservaLaboratorio,
    VisitaReservas,
    es_coordinador,
    es_estudiante,
    es_laboratorista,
)
from .planificacion import calcular, publicar
from .services import decidir_solicitud, estado_franja, reservar, resumen_uso


def solo_coordinador(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not es_coordinador(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def fecha_consulta(request):
    form = FechaForm(request.GET if request.GET else {"fecha": timezone.localdate().isoformat()})
    return form, form.cleaned_data["fecha"] if form.is_valid() else None


def id_consulta(valor):
    if valor.isascii() and valor.isdecimal() and len(valor) <= 18:
        numero = int(valor)
        return numero if numero > 0 else None
    return None


def registro_estudiante(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistroEstudianteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError as exc:
            if "uts_user_email_unique" in str(exc):
                form.add_error("email", "Este correo ya está en uso")
            else:
                form.add_error("cedula", "Esta cédula ya tiene una cuenta.")
        else:
            login(request, user, backend="tutorias.backends.AccesoLaboratoriosBackend")
            messages.success(request, "Cuenta creada. Ya puedes reservar laboratorios.")
            return redirect("laboratorios")
    return render(request, "tutorias/registro_estudiante.html", {"form": form})


@login_required
def mi_perfil(request):
    if not es_estudiante(request.user):
        raise PermissionDenied
    with escritura_atomica():
        form = DatosEstudianteForm(request.POST or None, instance=request.user.perfil)
        if request.method == "POST" and form.is_valid():
            profile = form.save(commit=False)
            profile.revision = "PENDIENTE"
            profile.revisado_el = None
            profile.revisado_por = None
            try:
                with escritura_atomica():
                    profile.usuario.save()
                    profile.save()
            except IntegrityError:
                form.add_error("email", "Este correo ya está en uso")
                return render(request, "tutorias/perfil.html", {"form": form})
            messages.success(
                request,
                "Tus datos se actualizaron. Puedes reservar mientras coordinación los revisa.",
            )
            return redirect("laboratorios")
    return render(request, "tutorias/perfil.html", {"form": form})


@login_required
def dashboard(request):
    if es_coordinador(request.user):
        return redirect("reportes")
    if es_laboratorista(request.user):
        return redirect("agenda_laboratorista")
    return redirect("laboratorios")


@login_required
def laboratorios(request):
    if not es_estudiante(request.user) and not es_coordinador(request.user):
        raise PermissionDenied
    if es_estudiante(request.user):
        VisitaReservas.objects.get_or_create(estudiante=request.user, fecha=timezone.localdate())
    labs = Laboratorio.objects.filter(activo=True).prefetch_related("materias")
    form, fecha = fecha_consulta(request)
    return render(
        request, "tutorias/laboratorios.html", {"laboratorios": labs, "form": form, "fecha": fecha}
    )


@login_required
def reservar_laboratorio(request, pk):
    lab = get_object_or_404(Laboratorio, pk=pk, activo=True)
    if not es_estudiante(request.user) and not es_coordinador(request.user):
        raise PermissionDenied
    if es_estudiante(request.user):
        VisitaReservas.objects.get_or_create(estudiante=request.user, fecha=timezone.localdate())
    form, fecha = fecha_consulta(request)
    materias = lab.materias.filter(activa=True, tecnica=True)
    selected = id_consulta(request.GET.get("materia", ""))
    materia = materias.filter(pk=selected).first() if selected else None
    context = {"lab": lab, "materias": materias, "materia": materia, "form": form, "fecha": fecha}
    return render(request, "tutorias/reservar_laboratorio.html", context)


@login_required
@never_cache
def disponibilidad(request, pk):
    lab = get_object_or_404(Laboratorio, pk=pk, activo=True)
    if not es_estudiante(request.user) and not es_coordinador(request.user):
        raise PermissionDenied
    form, fecha = fecha_consulta(request)
    materia_id = id_consulta(request.GET.get("materia", ""))
    if fecha is None or materia_id is None:
        return JsonResponse({"error": "Selecciona una fecha y una materia válidas."}, status=400)
    if not lab.materias.filter(pk=materia_id, tecnica=True, activa=True).exists():
        return JsonResponse(
            {"error": "La materia no está asociada a este laboratorio."}, status=400
        )
    franjas = (
        lab.franjas.filter(
            activa=True,
            periodo__activo=True,
            periodo__fecha_inicio__lte=fecha,
            periodo__fecha_fin__gte=fecha,
            dia_semana=fecha.isoweekday(),
        )
        .select_related("periodo", "laboratorio")
        .order_by("hora_inicio")
    )
    reserved = dict(
        ReservaLaboratorio.objects.filter(
            estudiante=request.user, fecha=fecha, activa=True
        ).values_list("franja_id", "estado")
    )
    items = []
    for franja in franjas:
        estado = estado_franja(franja, fecha)
        estado["reservada"] = franja.pk in reserved
        estado["estado_solicitud"] = reserved.get(franja.pk, "")
        estado["permitida"] = es_estudiante(request.user) and request.user.perfil.completo
        items.append(estado)
    return JsonResponse(
        {"franjas": items, "actualizado": timezone.localtime().strftime("%H:%M:%S")}
    )


@login_required
@require_POST
def confirmar_reserva(request):
    form = ConfirmacionForm(request.POST)
    if not es_estudiante(request.user):
        raise PermissionDenied
    if not form.is_valid():
        return JsonResponse({"error": "Revisa la materia, la fecha y la franja."}, status=400)
    try:
        reserva = reservar(
            request.user,
            form.cleaned_data["franja"],
            form.cleaned_data["materia"],
            form.cleaned_data["fecha"],
        )
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=409)
    except (IntegrityError, OperationalError):
        return JsonResponse(
            {"error": "La disponibilidad cambió. Actualiza e intenta de nuevo."}, status=409
        )
    return JsonResponse(
        {
            "mensaje": "Solicitud enviada. Pendiente de aprobación del coordinador.",
            "estado": reserva.estado,
            "reserva": reserva.pk,
            "url": reverse("mis_reservas"),
        },
        status=201,
    )


@login_required
def mis_reservas(request):
    if not es_estudiante(request.user):
        raise PermissionDenied
    reservas = (
        ReservaLaboratorio.objects.filter(estudiante=request.user)
        .select_related("materia", "laboratorio")
        .order_by("-fecha", "hora_inicio")
    )
    now = timezone.localtime()
    for reserva in reservas:
        reserva.cancelable = reserva.activa and datetime.combine(
            reserva.fecha, reserva.hora_inicio
        ) > now.replace(tzinfo=None)
    return render(request, "tutorias/mis_reservas.html", {"reservas": reservas})


@login_required
@require_POST
def cancelar_reserva(request, pk):
    with escritura_atomica():
        reserva = get_object_or_404(ReservaLaboratorio, pk=pk)
        if reserva.estudiante_id != request.user.pk and not es_coordinador(request.user):
            raise PermissionDenied
        if not reserva.activa:
            messages.error(request, "La solicitud ya fue resuelta o cancelada.")
        elif (
            timezone.make_aware(datetime.combine(reserva.fecha, reserva.hora_inicio))
            <= timezone.now()
        ):
            messages.error(request, "No es posible cancelar una franja que ya comenzó.")
        else:
            reserva.activa = False
            reserva.estado = EstadoReserva.CANCELADA
            reserva.cancelada_el = timezone.now()
            reserva.save(update_fields=["activa", "estado", "cancelada_el"])
            messages.success(request, "Reserva cancelada. El cupo vuelve a estar disponible.")
    return redirect("reservas_coordinador" if es_coordinador(request.user) else "mis_reservas")


@solo_coordinador
def reportes(request):
    form, fecha = fecha_consulta(request)
    context = {"form": form, "fecha": fecha}
    if fecha:
        lunes = fecha - timedelta(days=fecha.weekday())
        viernes = lunes + timedelta(days=4)
        diario = resumen_uso(fecha, fecha)
        semanal = resumen_uso(lunes, viernes)
        filas = []
        for i in range(5):
            day = lunes + timedelta(days=i)
            uso = resumen_uso(day, day)
            filas.append(
                {
                    "fecha": day,
                    "reservas": uso["reservas"],
                    "estudiantes": uso["estudiantes"],
                    "visitas": VisitaReservas.objects.filter(fecha=day).count(),
                }
            )
        context.update(
            diario=diario,
            semanal=semanal,
            lunes=lunes,
            viernes=viernes,
            filas=filas,
            visitas=VisitaReservas.objects.filter(fecha=fecha).count(),
            visitas_semana=VisitaReservas.objects.filter(fecha__range=(lunes, viernes))
            .values("estudiante")
            .distinct()
            .count(),
            pendientes=PerfilUsuario.objects.filter(
                rol="ESTUDIANTE", usuario__is_active=True, revision="PENDIENTE"
            ).count(),
        )
    return render(request, "tutorias/reportes.html", context)


@solo_coordinador
def estudiantes(request):
    query = request.GET.get("q", "").strip()
    profiles = PerfilUsuario.objects.filter(
        rol="ESTUDIANTE", usuario__is_active=True
    ).select_related("usuario")
    if query:
        profiles = profiles.filter(
            Q(cedula__icontains=query)
            | Q(usuario__first_name__icontains=query)
            | Q(usuario__last_name__icontains=query)
            | Q(usuario__email__icontains=query)
        )
    return render(
        request,
        "tutorias/estudiantes.html",
        {"estudiantes": profiles.order_by("usuario__last_name"), "q": query},
    )


@solo_coordinador
def revisar_estudiante(request, pk):
    profile = get_object_or_404(
        PerfilUsuario.objects.select_related("usuario"), pk=pk, rol="ESTUDIANTE"
    )
    form = RevisionForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        profile = form.save(commit=False)
        profile.revisado_por = request.user
        profile.revisado_el = timezone.now()
        profile.save()
        messages.success(request, "Revisión guardada. El estudiante puede seguir reservando.")
        return redirect("estudiantes")
    return render(
        request, "tutorias/revisar_estudiante.html", {"estudiante": profile, "form": form}
    )


@solo_coordinador
def reservas_coordinador(request):
    form, fecha = fecha_consulta(request)
    reservas = (
        ReservaLaboratorio.objects.none()
        if not fecha
        else ReservaLaboratorio.objects.filter(fecha=fecha)
    )
    franja_id = id_consulta(request.GET.get("franja", ""))
    if franja_id:
        reservas = reservas.filter(franja_id=franja_id)
    reservas = reservas.select_related("estudiante__perfil", "laboratorio", "materia").order_by(
        "hora_inicio", "laboratorio__nombre"
    )
    return render(
        request,
        "tutorias/reservas_coordinador.html",
        {"reservas": reservas, "form": form, "fecha": fecha},
    )


CONFIG = {
    "laboratorios": (
        Laboratorio,
        LaboratorioForm,
        "Laboratorios",
        ["nombre", "ubicacion", "capacidad", "activo"],
    ),
    "materias": (
        Materia,
        MateriaForm,
        "Materias técnicas",
        ["codigo", "nombre", "nivel", "semestre", "activa"],
    ),
    "semestres": (
        PeriodoAcademico,
        PeriodoForm,
        "Semestres",
        ["nombre", "fecha_inicio", "fecha_fin", "activo"],
    ),
    "franjas": (
        FranjaLaboratorio,
        FranjaForm,
        "Franjas de reserva",
        ["laboratorio", "periodo", "dia_semana", "hora_inicio", "hora_fin", "capacidad", "activa"],
    ),
    "clases": (
        HorarioClase,
        ClaseForm,
        "Clases fijas",
        ["laboratorio", "materia", "periodo", "dia_semana", "hora_inicio", "hora_fin"],
    ),
}


def pagina_configuracion(request):
    valor = request.GET.get("pagina", "1")
    return (
        int(valor)
        if valor.isascii() and valor.isdecimal() and len(valor) <= 9 and int(valor) > 0
        else 1
    )


def volver_configuracion(tipo, periodo=None, pagina=1):
    url = reverse("configurar", kwargs={"tipo": tipo})
    if tipo in ("clases", "franjas") and periodo:
        url += "?" + urlencode({"periodo": periodo, "pagina": pagina})
    return url


@solo_coordinador
@never_cache
def configurar(request, tipo):
    if tipo not in CONFIG:
        raise PermissionDenied
    model, _, titulo, fields = CONFIG[tipo]
    objects = model.objects.all()
    estado = request.GET.get("estado", "activas")
    if tipo == "materias":
        objects = objects.filter(tecnica=True)
        if estado != "todas":
            objects = objects.filter(activa=estado != "inactivas")
    if tipo == "laboratorios" and estado != "todas":
        objects = objects.filter(activo=estado != "inactivas")
    por_semestre = tipo in ("clases", "franjas")
    periodos = PeriodoAcademico.objects.all() if por_semestre else []
    periodo = pagina = None
    error_periodo = ""
    if por_semestre:
        valor = request.GET.get("periodo", "")
        if valor.isascii() and valor.isdecimal() and len(valor) <= 18:
            periodo = periodos.filter(pk=int(valor)).first()
        if valor and periodo is None:
            error_periodo = "Selecciona un semestre válido."
        fields = [field for field in fields if field != "periodo"]
        if periodo:
            objects = objects.filter(periodo=periodo).select_related("laboratorio", "periodo")
            if tipo == "clases":
                objects = objects.select_related("materia")
            objects = objects.order_by("laboratorio__nombre", "dia_semana", "hora_inicio", "pk")
            pagina = Paginator(objects, 10).get_page(pagina_configuracion(request))
            objects = pagina.object_list
        else:
            objects = objects.none()
    rows = []
    for obj in objects:
        values = []
        for field in fields:
            display = getattr(obj, f"get_{field}_display", None)
            value = display() if display else getattr(obj, field)
            if isinstance(value, bool):
                value = "Sí" if value else "No"
            elif value is None:
                value = "Del laboratorio"
            values.append(value)
        rows.append({"pk": obj.pk, "values": values})
    return render(
        request,
        "tutorias/configurar.html",
        {
            "tipo": tipo,
            "titulo": titulo,
            "tabs": [(k, v[2]) for k, v in CONFIG.items()],
            "headers": [model._meta.get_field(f).verbose_name for f in fields],
            "rows": rows,
            "crear": True,
            "estado": estado,
            "por_semestre": por_semestre,
            "periodos": periodos,
            "periodo_seleccionado": periodo,
            "pagina": pagina,
            "error_periodo": error_periodo,
        },
    )


@solo_coordinador
@never_cache
def editar_configuracion(request, tipo, pk=None):
    if tipo not in CONFIG:
        raise PermissionDenied
    model, form_type, titulo, _ = CONFIG[tipo]
    with escritura_atomica():
        obj = get_object_or_404(model, pk=pk) if pk else None
        initial = {}
        if not obj:
            for key in ("laboratorio", "periodo"):
                value = id_consulta(request.GET.get(key, ""))
                if value:
                    initial[key] = value
        form = form_type(request.POST or None, instance=obj, initial=initial)
        periodo_anterior = (
            obj.periodo_id if obj and tipo in ("clases", "franjas") else initial.get("periodo")
        )
        url_volver = volver_configuracion(tipo, periodo_anterior, pagina_configuracion(request))
        if request.method == "POST" and form.is_valid():
            form.save()
            if tipo == "laboratorios" and not form.instance.activo:
                form.instance.franjas.filter(activa=True).update(activa=False, automatica=False)
            messages.success(request, "Configuración guardada.")
            if tipo == "clases":
                messages.info(
                    request,
                    "La clase quedó guardada. Recalcula la disponibilidad desde Generar franjas antes de publicar nuevos horarios.",
                )
            periodo_guardado = form.instance.periodo_id if tipo in ("clases", "franjas") else None
            pagina_destino = (
                pagina_configuracion(request) if periodo_guardado == periodo_anterior else 1
            )
            return redirect(volver_configuracion(tipo, periodo_guardado, pagina_destino))
    return render(
        request,
        "tutorias/editar_configuracion.html",
        {"form": form, "titulo": titulo, "tipo": tipo, "obj": obj, "url_volver": url_volver},
    )


@solo_coordinador
@never_cache
@require_http_methods(["GET", "POST"])
def eliminar_semestre(request, pk):
    try:
        with escritura_atomica():
            periodo = get_object_or_404(PeriodoAcademico, pk=pk)
            reservas = ReservaLaboratorio.objects.filter(franja__periodo=periodo)
            ahora = timezone.localtime()
            vigentes = (
                reservas.filter(activa=True)
                .filter(
                    Q(fecha__gt=ahora.date()) | Q(fecha=ahora.date(), hora_fin__gt=ahora.time())
                )
                .exists()
            )
            resumen = {
                "clases": HorarioClase.objects.filter(periodo=periodo).count(),
                "franjas": FranjaLaboratorio.objects.filter(periodo=periodo).count(),
                "generaciones": GeneracionFranjas.objects.filter(periodo=periodo).count(),
                "reservas": reservas.count(),
            }
            if request.method == "POST":
                accion = request.POST.get("accion")
                if vigentes:
                    messages.error(
                        request,
                        "Hay préstamos futuros o en curso. Resuélvelos antes de cerrar o eliminar el semestre.",
                    )
                elif accion == "cerrar" and resumen["reservas"]:
                    periodo.activo = False
                    periodo.save(update_fields=["activo"])
                    messages.success(
                        request,
                        "Semestre cerrado. Se conservaron sus clases, franjas y reservas históricas.",
                    )
                elif accion == "eliminar" and not resumen["reservas"]:
                    HorarioClase.objects.filter(periodo=periodo).delete()
                    FranjaLaboratorio.objects.filter(periodo=periodo).delete()
                    GeneracionFranjas.objects.filter(periodo=periodo).delete()
                    periodo.delete()
                    messages.success(
                        request,
                        "Semestre eliminado junto con sus clases y franjas. Los laboratorios, materias y otros semestres no cambiaron.",
                    )
                else:
                    messages.error(
                        request,
                        "No se realizaron cambios. Revisa nuevamente la confirmación del semestre.",
                    )
                return redirect("configurar", tipo="semestres")
    except ProtectedError:
        messages.error(
            request, "Este semestre tiene registros protegidos. No se eliminó ningún dato."
        )
        return redirect("configurar", tipo="semestres")
    return render(
        request,
        "tutorias/eliminar_semestre.html",
        {
            "periodo": periodo,
            "resumen": resumen,
            "vigentes": vigentes,
        },
    )


@solo_coordinador
def eliminar_materia(request, pk):
    with escritura_atomica():
        materia = get_object_or_404(Materia, pk=pk, tecnica=True)
        protegida = (
            materia.horarios_clase.exists()
            or ReservaLaboratorio.objects.filter(materia=materia).exists()
        )
        futuras = ReservaLaboratorio.objects.filter(
            materia=materia, activa=True, fecha__gte=timezone.localdate()
        ).exists()
        if request.method == "POST":
            if futuras:
                messages.error(
                    request, "Revisa las reservas futuras antes de retirar esta materia."
                )
            elif protegida:
                materia.activa = False
                materia.save(update_fields=["activa"])
                materia.laboratorios.clear()
                messages.success(
                    request, "Materia retirada del catálogo activo. Su historial se conserva."
                )
            else:
                materia.delete()
                messages.success(request, "Materia eliminada.")
            return redirect("configurar", tipo="materias")
    return render(
        request,
        "tutorias/eliminar_materia.html",
        {
            "materia": materia,
            "protegida": protegida,
            "futuras": futuras,
        },
    )


@solo_coordinador
def retirar_laboratorio(request, pk):
    with escritura_atomica():
        lab = get_object_or_404(Laboratorio, pk=pk)
        protegido = (
            lab.franjas.exists()
            or HorarioClase.objects.filter(laboratorio=lab).exists()
            or ReservaLaboratorio.objects.filter(laboratorio=lab).exists()
        )
        vigentes = lab.reservas_vigentes().exists()
        if request.method == "POST":
            if vigentes:
                messages.error(
                    request,
                    "Resuelve los préstamos futuros o en curso antes de retirar el laboratorio.",
                )
            elif protegido:
                lab.activo = False
                lab.full_clean()
                lab.save(update_fields=["activo"])
                lab.franjas.filter(activa=True).update(activa=False, automatica=False)
                messages.success(request, "Laboratorio retirado. Su historial se conserva.")
            else:
                lab.delete()
                messages.success(request, "Laboratorio eliminado.")
            return redirect("configurar", tipo="laboratorios")
    return render(
        request,
        "tutorias/retirar_laboratorio.html",
        {
            "laboratorio": lab,
            "protegido": protegido,
            "vigentes": vigentes,
        },
    )


@solo_coordinador
def generar_franjas(request):
    form = GenerarFranjasForm(
        request.POST
        if request.method == "POST" and request.POST.get("accion") != "publicar"
        else None
    )
    plan = token = periodo = None
    if request.method == "POST" and request.POST.get("accion") == "publicar":
        try:
            datos = signing.loads(
                request.POST.get("token", ""), salt="oferta-semestral", max_age=1800
            )
            if datos["usuario"] != request.user.pk:
                raise signing.BadSignature
            resultado = publicar(
                datos["periodo"], datos["labs"], datos["dias"], datos["huella"], request.user
            )
        except signing.BadSignature:
            messages.error(request, "La vista previa venció o no es válida. Calcula de nuevo.")
        except (ValidationError, PeriodoAcademico.DoesNotExist) as exc:
            messages.error(
                request,
                " ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "El semestre ya no existe.",
            )
        except (OperationalError, IntegrityError):
            messages.error(
                request,
                "No se publicaron los cambios. Recalcula la disponibilidad e intenta de nuevo.",
            )
        else:
            messages.success(
                request,
                f"Publicación completada: {len(resultado['nuevas'])} franjas nuevas y {len(resultado['retirar'])} retiradas. No se crearon solicitudes de estudiantes.",
            )
        return redirect("generar_franjas")
    if request.method == "POST" and form.is_valid():
        periodo = form.cleaned_data["periodo"]
        labs = list(form.cleaned_data["laboratorios"].values_list("pk", flat=True))
        dias = form.cleaned_data["dias"]
        plan = calcular(periodo, labs, dias)
        if plan["nuevas"] or plan["retirar"]:
            token = signing.dumps(
                {
                    "periodo": periodo.pk,
                    "labs": labs,
                    "dias": dias,
                    "huella": plan["huella"],
                    "usuario": request.user.pk,
                },
                salt="oferta-semestral",
            )
    return render(
        request,
        "tutorias/generar_franjas.html",
        {
            "form": form,
            "plan": plan,
            "token": token,
            "periodo": periodo,
        },
    )


@solo_coordinador
@require_POST
def eliminar_horario(request, tipo, pk):
    if tipo not in ("clases", "franjas"):
        raise PermissionDenied
    with escritura_atomica():
        obj = get_object_or_404(CONFIG[tipo][0], pk=pk)
        periodo_id = obj.periodo_id
        try:
            obj.delete()
            messages.success(request, "Horario eliminado.")
        except ProtectedError:
            messages.error(request, "Esta franja tiene reservas. Puedes desactivarla desde Editar.")
    return redirect(volver_configuracion(tipo, periodo_id, pagina_configuracion(request)))


@solo_coordinador
def copiar_horarios(request):
    form = CopiarHorarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with escritura_atomica():
                origen, destino = form.cleaned_data["origen"], form.cleaned_data["destino"]
                if (
                    destino.fecha_inicio <= origen.fecha_fin
                    and destino.fecha_fin >= origen.fecha_inicio
                ):
                    raise ValidationError(
                        "Los semestres se superponen. Ajusta sus fechas antes de copiar."
                    )
                total = 0
                modelos = (
                    (HorarioClase, FranjaLaboratorio)
                    if form.cleaned_data["incluir_franjas"]
                    else (HorarioClase,)
                )
                for model in modelos:
                    for obj in model.objects.filter(periodo=origen):
                        obj.pk = None
                        obj.periodo = destino
                        if model is FranjaLaboratorio:
                            obj.automatica = False
                        obj.full_clean()
                        obj.save()
                        total += 1
                if not total:
                    raise ValidationError("El semestre de origen no tiene horarios.")
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(request, f"Se copiaron {total} horarios al semestre {destino}.")
            return redirect("configurar", tipo="clases")
    return render(
        request,
        "tutorias/editar_configuracion.html",
        {
            "form": form,
            "titulo": "Copiar horarios entre semestres",
            "tipo": "clases",
            "copiar": True,
        },
    )


@solo_coordinador
def solicitudes(request):
    estado = request.GET.get("estado", EstadoReserva.PENDIENTE)
    if estado not in EstadoReserva.values:
        estado = EstadoReserva.PENDIENTE
    reservas = (
        ReservaLaboratorio.objects.filter(estado=estado)
        .select_related("estudiante__perfil", "laboratorio", "materia")
        .order_by("fecha", "hora_inicio", "creada")
    )
    return render(
        request,
        "tutorias/solicitudes.html",
        {
            "reservas": reservas,
            "estado": estado,
            "estados": EstadoReserva.choices,
            "pendientes": ReservaLaboratorio.objects.filter(estado=EstadoReserva.PENDIENTE).count(),
        },
    )


@solo_coordinador
def resolver_solicitud(request, pk):
    reserva = get_object_or_404(
        ReservaLaboratorio.objects.select_related(
            "estudiante__perfil", "laboratorio", "materia", "decidida_por"
        ),
        pk=pk,
    )
    error = None
    if request.method == "POST":
        try:
            decidir_solicitud(
                request.user, pk, request.POST.get("decision"), request.POST.get("motivo", "")
            )
        except ValidationError as exc:
            error = " ".join(exc.messages)
            reserva.refresh_from_db()
        except (IntegrityError, OperationalError):
            error = "La solicitud está siendo actualizada. Recarga la página e intenta de nuevo."
            reserva.refresh_from_db()
        else:
            messages.success(
                request, "La decisión fue registrada y ya es visible para el estudiante."
            )
            return redirect("solicitudes")
    return render(request, "tutorias/resolver_solicitud.html", {"reserva": reserva, "error": error})


@login_required
@never_cache
def estados_reservas(request):
    if not es_estudiante(request.user):
        raise PermissionDenied
    return JsonResponse(
        {
            "reservas": [
                {
                    "id": reserva.pk,
                    "estado": reserva.estado,
                    "etiqueta": reserva.get_estado_display(),
                    "motivo": reserva.motivo_decision,
                    "activa": reserva.activa,
                }
                for reserva in ReservaLaboratorio.objects.filter(estudiante=request.user)
            ]
        }
    )
