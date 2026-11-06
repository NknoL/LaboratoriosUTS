from django.urls import path

from . import calendar_views, laboratorista_views, recovery, seguridad, views

urlpatterns = [
    path("laboratorista/", laboratorista_views.agenda_laboratorista, name="agenda_laboratorista"),
    path(
        "laboratorista/agenda/",
        laboratorista_views.agenda_laboratorista_datos,
        name="agenda_laboratorista_datos",
    ),
    path("coordinacion/laboratoristas/", laboratorista_views.laboratoristas, name="laboratoristas"),
    path(
        "coordinacion/laboratoristas/nuevo/",
        laboratorista_views.crear_laboratorista,
        name="crear_laboratorista",
    ),
    path(
        "coordinacion/laboratoristas/<int:pk>/",
        laboratorista_views.editar_laboratorista,
        name="editar_laboratorista",
    ),
    path(
        "coordinacion/laboratoristas/<int:pk>/clave/",
        laboratorista_views.clave_laboratorista,
        name="clave_laboratorista",
    ),
    path(
        "coordinacion/semestres/<int:pk>/eliminar/",
        views.eliminar_semestre,
        name="eliminar_semestre",
    ),
    path("coordinacion/generar-franjas/", views.generar_franjas, name="generar_franjas"),
    path(
        "coordinacion/laboratorios/<int:pk>/retirar/",
        views.retirar_laboratorio,
        name="retirar_laboratorio",
    ),
    path("cuentas/recuperar/", recovery.SolicitarRecuperacion.as_view(), name="password_reset"),
    path(
        "cuentas/recuperar/enviado/",
        recovery.RecuperacionEnviada.as_view(),
        name="password_reset_done",
    ),
    path(
        "cuentas/restablecer/<uidb64>/<token>/",
        recovery.ConfirmarRecuperacion.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "cuentas/restablecida/",
        recovery.RecuperacionCompleta.as_view(),
        name="password_reset_complete",
    ),
    path("cuentas/cambiar-clave/", seguridad.cambiar_clave, name="cambiar_clave"),
    path(
        "coordinacion/estudiantes/<int:pk>/clave-temporal/",
        seguridad.clave_temporal,
        name="clave_temporal",
    ),
    path("coordinacion/solicitudes/", views.solicitudes, name="solicitudes"),
    path("coordinacion/solicitudes/<int:pk>/", views.resolver_solicitud, name="resolver_solicitud"),
    path("coordinacion/calendario/", calendar_views.calendario, name="calendario"),
    path(
        "coordinacion/calendario/eventos/",
        calendar_views.eventos_calendario,
        name="eventos_calendario",
    ),
    path("mis-reservas/estados/", views.estados_reservas, name="estados_reservas"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("registro/", views.registro_estudiante, name="registro_estudiante"),
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("laboratorios/", views.laboratorios, name="laboratorios"),
    path("laboratorios/<int:pk>/", views.reservar_laboratorio, name="reservar_laboratorio"),
    path("api/laboratorios/<int:pk>/disponibilidad/", views.disponibilidad, name="disponibilidad"),
    path("reservas/confirmar/", views.confirmar_reserva, name="confirmar_reserva"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path("reservas/<int:pk>/cancelar/", views.cancelar_reserva, name="cancelar_reserva"),
    path("coordinacion/", views.reportes, name="reportes"),
    path("coordinacion/estudiantes/", views.estudiantes, name="estudiantes"),
    path("coordinacion/estudiantes/<int:pk>/", views.revisar_estudiante, name="revisar_estudiante"),
    path("coordinacion/reservas/", views.reservas_coordinador, name="reservas_coordinador"),
    path("coordinacion/copiar-horarios/", views.copiar_horarios, name="copiar_horarios"),
    path(
        "coordinacion/materias/<int:pk>/eliminar/", views.eliminar_materia, name="eliminar_materia"
    ),
    path("coordinacion/configurar/<str:tipo>/", views.configurar, name="configurar"),
    path(
        "coordinacion/configurar/<str:tipo>/nuevo/",
        views.editar_configuracion,
        name="crear_configuracion",
    ),
    path(
        "coordinacion/configurar/<str:tipo>/<int:pk>/",
        views.editar_configuracion,
        name="editar_configuracion",
    ),
    path(
        "coordinacion/configurar/<str:tipo>/<int:pk>/eliminar/",
        views.eliminar_horario,
        name="eliminar_horario",
    ),
]
