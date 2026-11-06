import logging
import time
from smtplib import SMTPException
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.models.functions import Lower, Trim
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.crypto import salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic.edit import FormView

from .db_lock import escritura_atomica
from .forms import EstiloForm
from .models import EventoSeguridad, LimiteRecuperacion

CORREO_LOCAL = (
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.console.EmailBackend",
)


def recuperacion_habilitada():
    try:
        origin = urlsplit(settings.PASSWORD_RESET_ORIGIN)
        origin.port
    except ValueError:
        return False
    secure = origin.scheme == "https" or (
        settings.DEBUG and origin.scheme == "http" and origin.hostname in ("localhost", "127.0.0.1")
    )
    if settings.EMAIL_BACKEND == "tutorias.email_backend.BrevoBackend":
        transport = bool(settings.BREVO_API_KEY)
    elif settings.EMAIL_BACKEND in CORREO_LOCAL:
        # Solo para pruebas en el equipo: el correo queda como archivo en correos_locales/.
        transport = settings.DEBUG
    else:
        transport = settings.EMAIL_HOST and settings.EMAIL_USE_TLS != settings.EMAIL_USE_SSL
    return bool(
        settings.PASSWORD_RESET_ENABLED
        and secure
        and origin.netloc
        and not origin.username
        and not origin.password
        and origin.path in ("", "/")
        and not origin.query
        and not origin.fragment
        and settings.DEFAULT_FROM_EMAIL
        and transport
    )


@escritura_atomica()
def permitir_intento(email, ip):
    ventana = int(time.time()) // 900
    LimiteRecuperacion.objects.filter(ventana__lt=ventana - 1).delete()
    allowed = True
    for kind, value, limit in (("correo", email.strip().lower(), 3), ("ip", ip, 10)):
        key = salted_hmac("uts-password-reset", f"{kind}:{value}", algorithm="sha256").hexdigest()
        row, _ = LimiteRecuperacion.objects.get_or_create(clave=key, ventana=ventana)
        row.intentos += 1
        allowed = allowed and row.intentos <= limit
        row.save(update_fields=["intentos"])
    return allowed


class RecuperacionForm(EstiloForm, PasswordResetForm):
    email = forms.CharField(
        max_length=254,
        label="Correo registrado o usuario",
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()

    def clean_email(self):
        return self.cleaned_data["email"].strip()

    def get_users(self, email):
        identity = email.strip()
        lookup = (
            Q(correo=identity.lower())
            if "@" in identity
            else Q(username=identity) | Q(perfil__cedula=identity)
        )
        users = list(
            User.objects.annotate(correo=Lower(Trim("email"))).filter(
                lookup, is_active=True, perfil__rol="ESTUDIANTE", is_superuser=False
            )[:2]
        )
        # Una identidad ambigua nunca puede restablecer dos cuentas.
        return [u for u in users if u.email and u.has_usable_password()] if len(users) == 1 else []

    def clave_limite(self):
        users = self.get_users(self.cleaned_data["email"])
        return users[0].email if users else self.cleaned_data["email"]

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string

        subject = "".join(render_to_string(subject_template_name, context).splitlines())
        message = EmailMultiAlternatives(
            subject, render_to_string(email_template_name, context), from_email, [to_email]
        )
        try:
            if message.send() != 1:
                raise OSError("Mensaje no aceptado")
        except (SMTPException, OSError, ValueError):
            # Sin traceback: los proveedores pueden incluir direcciones o secretos en errores.
            logging.getLogger(__name__).error("No fue posible enviar un mensaje de recuperacion.")


class NuevaClaveForm(EstiloForm, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class RecuperacionDisponible:
    def dispatch(self, request, *args, **kwargs):
        if not recuperacion_habilitada():
            return render(request, "registration/recuperacion_inactiva.html", status=503)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(never_cache, name="dispatch")
class SolicitarRecuperacion(RecuperacionDisponible, FormView):
    template_name = "registration/recuperar.html"
    form_class = RecuperacionForm
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        if permitir_intento(form.clave_limite(), self.request.META.get("REMOTE_ADDR", "")):
            origin = urlsplit(settings.PASSWORD_RESET_ORIGIN)
            try:
                form.save(
                    domain_override=origin.netloc,
                    use_https=origin.scheme == "https",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    email_template_name="registration/recuperacion_email.txt",
                    subject_template_name="registration/recuperacion_asunto.txt",
                    request=self.request,
                )
            except (SMTPException, OSError):
                logging.getLogger(__name__).error(
                    "No fue posible enviar un mensaje de recuperación."
                )
        # La respuesta es la misma para correos inexistentes, inactivos o limitados.
        return redirect(self.success_url)


class RecuperacionEnviada(RecuperacionDisponible, auth_views.PasswordResetDoneView):
    template_name = "registration/recuperacion_enviada.html"


class ConfirmarRecuperacion(RecuperacionDisponible, auth_views.PasswordResetConfirmView):
    template_name = "registration/restablecer.html"
    form_class = NuevaClaveForm
    success_url = reverse_lazy("password_reset_complete")

    def form_valid(self, form):
        from .seguridad import limpiar_clave_temporal, registrar

        with escritura_atomica():
            user = self.get_user(self.kwargs["uidb64"])
            token = self.request.session.get(auth_views.INTERNAL_RESET_SESSION_TOKEN)
            if not user or not self.token_generator.check_token(user, token):
                self.validlink = False
                return self.render_to_response(self.get_context_data())
            form.user = user
            response = super().form_valid(form)
            limpiar_clave_temporal(user)
            registrar(user, EventoSeguridad.RECUPERACION_CORREO, self.request, actor=user)
            return response

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        if (
            user
            and user.is_active
            and not user.is_superuser
            and getattr(getattr(user, "perfil", None), "rol", None) == "ESTUDIANTE"
        ):
            return user
        return None


class RecuperacionCompleta(RecuperacionDisponible, auth_views.PasswordResetCompleteView):
    template_name = "registration/recuperacion_completa.html"
