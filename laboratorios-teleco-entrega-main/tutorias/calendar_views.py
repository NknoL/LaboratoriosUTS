from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django import forms
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache

from .forms import EstiloForm
from .models import HorarioClase, Laboratorio, PeriodoAcademico, ReservaLaboratorio
from .services import estado_franja
from .views import solo_coordinador


class CalendarioForm(EstiloForm, forms.Form):
    laboratorio = forms.ModelChoiceField(queryset=Laboratorio.objects.all())
    periodo = forms.ModelChoiceField(queryset=PeriodoAcademico.objects.all(), label="Semestre")
    fecha = forms.DateField(
        label="Ir a fecha",
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


@solo_coordinador
@never_cache
def calendario(request):
    lab = Laboratorio.objects.first()
    hoy = timezone.localdate()
    activos = PeriodoAcademico.objects.filter(activo=True)
    periodo = (
        activos.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy).order_by("fecha_inicio").first()
        or activos.first()
        or PeriodoAcademico.objects.first()
    )
    data = (
        request.GET
        if request.GET
        else {
            "laboratorio": lab.pk if lab else "",
            "periodo": periodo.pk if periodo else "",
        }
    )
    form = CalendarioForm(data)
    config = None
    aviso_oferta = ""
    if form.is_valid():
        lab, periodo = form.cleaned_data["laboratorio"], form.cleaned_data["periodo"]
        fecha = form.cleaned_data["fecha"] or timezone.localdate()
        fecha = min(max(fecha, periodo.fecha_inicio), periodo.fecha_fin)
        params = urlencode({"laboratorio": lab.pk, "periodo": periodo.pk})
        config = {
            "inicio": periodo.fecha_inicio.isoformat(),
            "fin": (periodo.fecha_fin + timedelta(days=1)).isoformat(),
            "fecha": fecha.isoformat(),
            "url": reverse("eventos_calendario") + "?" + params,
        }
        franjas_periodo = lab.franjas.filter(periodo=periodo)
        if not lab.activo:
            aviso_oferta = "Este laboratorio está inactivo. Sus horarios se muestran para consulta, pero no admite nuevas solicitudes."
        elif not periodo.activo:
            aviso_oferta = "Este semestre está inactivo. Sus horarios se muestran para consulta, pero no admite nuevas solicitudes."
        elif not franjas_periodo.filter(activa=True).exists():
            if franjas_periodo.exists():
                aviso_oferta = "Todas las franjas de préstamo de este laboratorio están desactivadas para el semestre seleccionado. Solo se muestran las clases y el historial de reservas."
            else:
                aviso_oferta = "Este laboratorio aún no tiene franjas de préstamo publicadas para el semestre seleccionado."
    return render(
        request,
        "tutorias/calendario.html",
        {
            "form": form,
            "config": config,
            "lab": lab,
            "periodo": periodo,
            "aviso_oferta": aviso_oferta,
        },
    )


def dia_parametro(value):
    parsed = parse_datetime(value)
    return parsed.date() if parsed else date.fromisoformat(value)


@solo_coordinador
@never_cache
def eventos_calendario(request):
    form = CalendarioForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"error": "Selecciona un laboratorio y semestre válidos."}, status=400)
    try:
        inicio = dia_parametro(request.GET.get("start", ""))
        fin = dia_parametro(request.GET.get("end", ""))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Fechas no válidas."}, status=400)
    if not 0 < (fin - inicio).days <= 62:
        return JsonResponse({"error": "El rango debe ser de 1 a 62 días."}, status=400)
    lab, periodo = form.cleaned_data["laboratorio"], form.cleaned_data["periodo"]
    inicio = max(inicio, periodo.fecha_inicio)
    fin = min(fin, periodo.fecha_fin + timedelta(days=1))
    franjas = list(lab.franjas.filter(periodo=periodo).select_related("laboratorio", "periodo"))
    clases = list(
        HorarioClase.objects.filter(laboratorio=lab, periodo=periodo).select_related("materia")
    )
    counts = {}
    for row in (
        ReservaLaboratorio.objects.filter(laboratorio=lab, fecha__gte=inicio, fecha__lt=fin)
        .values("franja_id", "fecha", "estado")
        .annotate(total=Count("id"))
    ):
        counts.setdefault((row["franja_id"], row["fecha"]), {})[row["estado"]] = row["total"]
    eventos = []
    fecha = inicio
    while fecha < fin:
        for horario in [*clases, *franjas]:
            if horario.dia_semana != fecha.isoweekday():
                continue
            clase = isinstance(horario, HorarioClase)
            totals = counts.get((horario.pk, fecha), {}) if not clase else {}
            if not clase and not horario.activa and not totals:
                continue
            base = {
                "id": f"{'clase' if clase else 'franja'}-{horario.pk}-{fecha}",
                # Wall-clock schedule in Colombia, independent of the browser timezone.
                "start": datetime.combine(fecha, horario.hora_inicio).isoformat(),
                "end": datetime.combine(fecha, horario.hora_fin).isoformat(),
                "allDay": False,
                "extendedProps": {
                    "horario": f"{fecha:%d/%m/%Y} · {horario.hora_inicio:%H:%M} - {horario.hora_fin:%H:%M} (Colombia)"
                },
            }
            if clase:
                base.update(
                    title=f"Clase · {horario.materia.nombre}",
                    classNames=["evento-clase"],
                    url=reverse("editar_configuracion", args=["clases", horario.pk]),
                )
            else:
                estado = estado_franja(horario, fecha)
                pendientes, confirmadas = totals.get("PENDIENTE", 0), totals.get("CONFIRMADA", 0)
                tipo = (
                    "pendiente"
                    if pendientes
                    else "confirmada"
                    if confirmadas
                    else "libre"
                    if estado["reservable"]
                    else "cerrada"
                )
                detalle = f"{estado['disponibles']}/{estado['capacidad']} cupos · {pendientes} pendientes · {confirmadas} confirmadas"
                title = f"{estado['disponibles']}/{estado['capacidad']} cupos"
                if not horario.activa:
                    title = "Historial de reservas"
                base.update(
                    title=title,
                    classNames=[f"evento-{tipo}"],
                    url=reverse("reservas_coordinador")
                    + "?"
                    + urlencode({"fecha": fecha.isoformat(), "franja": horario.pk}),
                )
                base["extendedProps"].update(
                    detalle=detalle,
                    editar=reverse("editar_configuracion", args=["franjas", horario.pk]),
                    motivo=estado["motivo"],
                )
            eventos.append(base)
        fecha += timedelta(days=1)
    return JsonResponse(eventos, safe=False)
