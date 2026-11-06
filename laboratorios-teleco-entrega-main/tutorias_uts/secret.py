import os
import secrets


def clave_local(base_dir):
    configured = os.environ.get("DJANGO_SECRET_KEY")
    if configured:
        return configured
    path = base_dir / ".django-secret-key"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="ascii").strip()
    value = secrets.token_urlsafe(64)
    with os.fdopen(descriptor, "w", encoding="ascii") as file:
        file.write(value)
    return value
