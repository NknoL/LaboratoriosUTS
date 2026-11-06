from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilUsuario, RolUsuario


@receiver(post_save, sender=get_user_model())
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw", False):
        PerfilUsuario.objects.create(
            usuario=instance,
            rol=RolUsuario.COORDINADOR if instance.is_superuser else RolUsuario.ESTUDIANTE,
        )
