from datetime import date, datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Case, When
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from .db_lock import escritura_atomica
from .horarios import dentro_jornada
from .models import (
    FranjaLaboratorio,
    HorarioClase,
    Laboratorio,
    Materia,
    NivelMateria,
    PerfilUsuario,
    PeriodoAcademico,
    ReservaLaboratorio,
)


class EstiloForm:
    def estilo(self):
        for name, field in self.fields.items():
            widget = field.widget
            css = (
                "form-check-input"
                if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple))
                else (
                    "form-select"
                    if isinstance(widget, (forms.Select, forms.SelectMultiple))
                    else "form-control"
                )
            )
            widget.attrs["class"] = css
            if field.help_text:
                widget.attrs["aria-describedby"] = f"id_{name}_helptext"


def correo_institucional(value, user_id=None):
    value = value.strip().lower()
    domain = value.rsplit("@", 1)[-1]
    if domain not in settings.DOMAINS_CORREO_ESTUDIANTE:
        raise ValidationError("Usa tu correo institucional UTS.")
    if (
        User.objects.annotate(correo_normalizado=Lower(Trim("email")))
        .filter(correo_normalizado=value)
        .exclude(pk=user_id)
        .exists()
    ):
        raise ValidationError("Este correo ya está en uso")
    return value


class DatosEstudianteForm(EstiloForm, forms.ModelForm):
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo institucional", max_length=254)

    class Meta:
        model = PerfilUsuario
        fields = ("cedula", "first_name", "last_name", "email", "programa", "semestre")
        help_texts = {"semestre": "Tecnología: 1 a 6. Ingeniería: 7 a 10."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key in ("cedula", "programa", "semestre"):
            self.fields[key].required = True
        if self.instance.pk:
            for key in ("first_name", "last_name", "email"):
                self.initial[key] = getattr(self.instance.usuario, key)
        self.estilo()

    def clean_cedula(self):
        value = self.cleaned_data["cedula"]
        if User.objects.filter(username=value).exclude(pk=self.instance.usuario_id).exists():
            raise ValidationError("Esta cédula ya está vinculada a otra cuenta.")
        return value

    def clean_email(self):
        return correo_institucional(self.cleaned_data["email"], self.instance.usuario_id)

    @escritura_atomica()
    def save(self, commit=True):
        profile = super().save(commit=False)
        for key in ("first_name", "last_name", "email"):
            setattr(profile.usuario, key, self.cleaned_data[key])
        if commit:
            profile.usuario.save()
            profile.save()
        return profile


class RegistroEstudianteForm(EstiloForm, UserCreationForm):
    cedula = forms.CharField(label="Cédula", min_length=6, max_length=15)
    first_name = forms.CharField(label="Nombres", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo institucional", max_length=254)
    programa = forms.ChoiceField(choices=NivelMateria.choices)
    semestre = forms.IntegerField(
        min_value=1, max_value=10, help_text="Tecnología: 1 a 6. Ingeniería: 7 a 10."
    )

    class Meta:
        model = User
        fields = (
            "cedula",
            "first_name",
            "last_name",
            "email",
            "programa",
            "semestre",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()

    def clean_cedula(self):
        value = self.cleaned_data["cedula"].strip()
        if not value.isascii() or not value.isdigit():
            raise ValidationError("La cédula debe contener solo números.")
        if (
            PerfilUsuario.objects.filter(cedula=value).exists()
            or User.objects.filter(username=value).exists()
        ):
            raise ValidationError("Esta cédula ya tiene una cuenta.")
        self.instance.username = value
        return value

    def clean_email(self):
        return correo_institucional(self.cleaned_data["email"])

    def clean(self):
        data = super().clean()
        programa, semestre = data.get("programa"), data.get("semestre")
        if (
            programa
            and semestre
            and ((programa == "TEC" and semestre > 6) or (programa == "ING" and semestre < 7))
        ):
            self.add_error("semestre", "El semestre no corresponde al programa seleccionado.")
        return data

    @escritura_atomica()
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["cedula"]
        if commit:
            user.save()
            profile = user.perfil
            for key in ("cedula", "programa", "semestre"):
                setattr(profile, key, self.cleaned_data[key])
            profile.save()
        return user


class GenerarFranjasForm(EstiloForm, forms.Form):
    periodo = forms.ModelChoiceField(queryset=PeriodoAcademico.objects.all(), label="Semestre")
    laboratorios = forms.ModelMultipleChoiceField(
        queryset=Laboratorio.objects.filter(activo=True), widget=forms.CheckboxSelectMultiple
    )
    dias = forms.TypedMultipleChoiceField(
        choices=[
            (1, "Lunes"),
            (2, "Martes"),
            (3, "Miércoles"),
            (4, "Jueves"),
            (5, "Viernes"),
            (6, "Sábado"),
        ],
        coerce=int,
        initial=[1, 2, 3, 4, 5, 6],
        label="Días",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class LaboratorioForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Laboratorio
        fields = ("nombre", "ubicacion", "capacidad", "materias", "activo")
        help_texts = {"materias": "Materias técnicas habilitadas para reservar este laboratorio."}
        widgets = {"materias": forms.CheckboxSelectMultiple()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["materias"].queryset = Materia.objects.filter(tecnica=True, activa=True)
        if self.instance.pk:
            self.fields["materias"].queryset = self.fields["materias"].queryset.order_by(
                Case(When(pk__in=self.instance.materias.values("pk"), then=0), default=1),
                "semestre",
                "nombre",
            )
        self.fields["materias"].label_from_instance = lambda materia: (
            f"{materia.codigo} · {materia.nombre} · {materia.get_nivel_display()}"
        )
        self.estilo()

    def clean_materias(self):
        materias = self.cleaned_data["materias"]
        if (
            self.instance.pk
            and ReservaLaboratorio.objects.filter(
                laboratorio=self.instance, activa=True, fecha__gte=timezone.localdate()
            )
            .exclude(materia__in=materias)
            .exists()
        ):
            raise ValidationError(
                "No puedes retirar materias con reservas pendientes o confirmadas futuras. "
                "Revisa esas reservas primero."
            )
        return materias


class MateriaForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = Materia
        fields = ("codigo", "nombre", "nivel", "semestre", "linea", "activa")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()

    def save(self, commit=True):
        self.instance.tecnica = True
        return super().save(commit=commit)

    def clean_activa(self):
        activa = self.cleaned_data["activa"]
        if (
            not activa
            and self.instance.pk
            and ReservaLaboratorio.objects.filter(
                materia=self.instance, activa=True, fecha__gte=timezone.localdate()
            ).exists()
        ):
            raise ValidationError("Revisa las reservas futuras antes de desactivar esta materia.")
        return activa


class PeriodoForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = PeriodoAcademico
        fields = ("nombre", "fecha_inicio", "fecha_fin", "activo")
        widgets = {
            key: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
            for key in ("fecha_inicio", "fecha_fin")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class FranjaForm(EstiloForm, forms.ModelForm):
    def save(self, commit=True):
        if self._meta.model is FranjaLaboratorio:
            self.instance.automatica = False
        return super().save(commit=commit)

    class Meta:
        model = FranjaLaboratorio
        fields = (
            "periodo",
            "laboratorio",
            "dia_semana",
            "hora_inicio",
            "hora_fin",
            "capacidad",
            "activa",
        )
        widgets = {
            key: forms.TimeInput(format="%H:%M", attrs={"type": "time"})
            for key in ("hora_inicio", "hora_fin")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()

    def clean(self):
        data = super().clean()
        inicio, fin = data.get("hora_inicio"), data.get("hora_fin")
        if self._meta.model is FranjaLaboratorio and data.get("activa") and inicio and fin:
            if not dentro_jornada(inicio, fin):
                self.add_error(
                    "hora_inicio", "Las reservas deben estar entre las 09:00 y las 18:00."
                )
            elif datetime.combine(date.min, fin) - datetime.combine(date.min, inicio) != timedelta(
                minutes=45
            ):
                self.add_error("hora_fin", "Cada franja de reserva debe durar 45 minutos.")
        return data


class ClaseForm(FranjaForm):
    class Meta(FranjaForm.Meta):
        model = HorarioClase
        fields = (
            "periodo",
            "laboratorio",
            "materia",
            "dia_semana",
            "hora_inicio",
            "hora_fin",
            "grupo",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["materia"].queryset = Materia.objects.filter(tecnica=True, activa=True)


class CopiarHorarioForm(EstiloForm, forms.Form):
    incluir_franjas = forms.BooleanField(
        required=False,
        label="Copiar también las franjas existentes",
        help_text="Sin marcar: copia solo clases; después calcula la disponibilidad del nuevo semestre.",
    )
    origen = forms.ModelChoiceField(
        queryset=PeriodoAcademico.objects.all(), label="Semestre de origen"
    )
    destino = forms.ModelChoiceField(
        queryset=PeriodoAcademico.objects.all(), label="Semestre de destino"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()

    def clean(self):
        data = super().clean()
        if data.get("origen") and data.get("destino") and data["origen"] == data["destino"]:
            raise ValidationError("Selecciona dos semestres distintos.")
        return data


class RevisionForm(EstiloForm, forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ("revision", "notas_revision")
        widgets = {"notas_revision": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class FechaForm(EstiloForm, forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.estilo()


class ConfirmacionForm(forms.Form):
    franja = forms.IntegerField(min_value=1)
    materia = forms.IntegerField(min_value=1)
    fecha = forms.DateField()
