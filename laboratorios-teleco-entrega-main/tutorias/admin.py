from django.contrib import admin

from .models import es_coordinador

# Toda la gestión de negocio pasa por las vistas validadas de coordinación.
admin.site.site_header = "Coordinación de Telecomunicaciones UTS"
admin.site.site_title = "Laboratorios UTS"
admin.site.has_permission = lambda request: request.user.is_active and es_coordinador(request.user)
