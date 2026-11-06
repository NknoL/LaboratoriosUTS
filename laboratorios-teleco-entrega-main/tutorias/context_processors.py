from django.conf import settings

from .models import RolUsuario, obtener_rol
from .recovery import recuperacion_habilitada


def rol_usuario(request):
    return {
        "rol_usuario": obtener_rol(getattr(request, "user", None)),
        "ROL_COORDINADOR": RolUsuario.COORDINADOR,
        "ROL_ESTUDIANTE": RolUsuario.ESTUDIANTE,
        "ROL_LABORATORISTA": RolUsuario.LABORATORISTA,
        "recuperacion_habilitada": recuperacion_habilitada(),
        "recuperacion_demo": not settings.PASSWORD_RESET_ENABLED,
    }
