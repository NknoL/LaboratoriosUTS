from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.db.models.functions import Lower, Trim

from .forms import EstiloForm
from .models import Laboratorio, PerfilUsuario


class AgendaLaboratoristaForm(EstiloForm, forms.Form):
    fecha = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    laboratorio = forms.ModelChoiceField(
        queryset=Laboratorio.objects.order_by("nombre"),
        required=False,
        empty_label="Todos los laboratorios",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class DatosLaboratoristaMixin(EstiloForm):
    def preparar_campos(self):
        self.fields["first_name"].label = "Nombres"
        self.fields["last_name"].label = "Apellidos"
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].label = "Correo"
        self.fields["email"].required = True
        self.estilo()

    def clean_email(self):
        correo = self.cleaned_data["email"].strip().lower()
        if (
            User.objects.annotate(correo_normalizado=Lower(Trim("email")))
            .filter(correo_normalizado=correo)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("Este correo ya está en uso")
        return correo


class CrearLaboratoristaForm(DatosLaboratoristaMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario de acceso"
        self.fields["password1"].label = "Contraseña temporal"
        self.fields["password2"].label = "Confirmar contraseña temporal"
        self.preparar_campos()

    def clean_username(self):
        usuario = super().clean_username()
        if PerfilUsuario.objects.filter(cedula=usuario).exists():
            raise forms.ValidationError("Este usuario ya está vinculado a otra cuenta.")
        return usuario


class EditarLaboratoristaForm(DatosLaboratoristaMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")
        labels = {"is_active": "Acceso habilitado"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparar_campos()


class ClaveLaboratoristaForm(EstiloForm, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Nueva contraseña temporal"
        self.fields["new_password2"].label = "Confirmar contraseña temporal"
        self.estilo()
