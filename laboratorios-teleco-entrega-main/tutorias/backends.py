from django.contrib.auth.backends import ModelBackend

from .models import PerfilUsuario


class AccesoLaboratoriosBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is not None:
            profile = (
                PerfilUsuario.objects.select_related("usuario")
                .filter(cedula=username.strip())
                .first()
            )
            if profile:
                username = profile.usuario.username
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None:
            from .seguridad import clave_temporal_vencida

            if clave_temporal_vencida(user):
                # La clave temporal caducó sin usarse: coordinación debe generar otra.
                return None
        return user
