import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured

from .secret import clave_local

BASE_DIR = Path(__file__).resolve().parent.parent


def cargar_env(path):
    """Lee KEY=VALOR de un archivo .env privado. Las variables ya definidas en el sistema ganan."""
    try:
        lineas = path.read_text(encoding="utf-8-sig").splitlines()
    except (FileNotFoundError, PermissionError) as error:
        if os.environ.get("UTS_ENV_FILE"):
            raise ImproperlyConfigured(
                "No se puede leer UTS_ENV_FILE. Revisa su ruta y permisos."
            ) from error
        return
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        os.environ.setdefault(clave.strip(), valor)


# Configuración privada del equipo o servidor (no se sube a GitHub). Ver .env.example.
cargar_env(Path(os.environ.get("UTS_ENV_FILE", BASE_DIR / ".env")))

ENTORNO = os.environ.get("DJANGO_ENV", "development").strip().lower()
if ENTORNO not in {"development", "production"}:
    raise ImproperlyConfigured("DJANGO_ENV debe ser development o production.")
PRODUCTION = ENTORNO == "production"
if PRODUCTION and not os.environ.get("DJANGO_SECRET_KEY"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY es obligatoria en producción.")
SECRET_KEY = clave_local(BASE_DIR)
if PRODUCTION and (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith("django-insecure-")
    or "REEMPLAZAR" in SECRET_KEY
):
    raise ImproperlyConfigured("Genera una DJANGO_SECRET_KEY aleatoria y exclusiva de producción.")
DEBUG = not PRODUCTION
ALLOWED_HOSTS = [
    v.strip()
    for v in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else ""
    ).split(",")
    if v.strip()
]
if PRODUCTION and (not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS)):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS requiere nombres explícitos, sin comodines.")
# En un servidor privado sin certificado (solo intranet) usar DJANGO_HTTPS=0.
HTTPS = os.environ.get("DJANGO_HTTPS", "1") == "1"
CSRF_TRUSTED_ORIGINS = [
    ("https://" if HTTPS else "http://") + host
    for host in ALLOWED_HOSTS
    if host not in ("localhost", "127.0.0.1", "[::1]")
]
if PRODUCTION and HTTPS:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "tutorias.apps.TutoriasConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "tutorias.seguridad.ClaveTemporalMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "tutorias_uts.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tutorias.context_processors.rol_usuario",
            ],
        },
    },
]

WSGI_APPLICATION = "tutorias_uts.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
MYSQL_ENGINE = "django.db.backends.mysql"
POSTGRES_ENGINE = "django.db.backends.postgresql"
# Cotejamiento recomendado: existe en MySQL 5.7/8.x y en MariaDB (XAMPP, phpMyAdmin).
MYSQL_COLLATION = os.environ.get("DB_COLLATION", "utf8mb4_unicode_ci")


def configurar_mysql(db):
    options = db.setdefault("OPTIONS", {})
    options.update(
        {
            "charset": "utf8mb4",
            "connect_timeout": 10,
            # Modo estricto (evita truncados silenciosos) y espera de bloqueos acotada,
            "init_command": (
                "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO',"
                f" collation_connection='{MYSQL_COLLATION}', innodb_lock_wait_timeout=10"
            ),
            "isolation_level": "read committed",
        }
    )
    if os.environ.get("DB_SSL_CA"):
        options["ssl"] = {"ca": os.environ["DB_SSL_CA"]}
    db["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": MYSQL_COLLATION}
    return db


if os.environ.get("DATABASE_URL"):
    DATABASES["default"] = dj_database_url.parse(
        os.environ["DATABASE_URL"], conn_max_age=0, conn_health_checks=True
    )
    if DATABASES["default"]["ENGINE"] != MYSQL_ENGINE:
        raise ImproperlyConfigured(
            "DATABASE_URL debe apuntar a MySQL/MariaDB (mysql://usuario:clave@host:3306/base)."
        )
    configurar_mysql(DATABASES["default"])
elif PRODUCTION:
    raise ImproperlyConfigured("DATABASE_URL es obligatoria; no se usa SQLite en producción.")
if PRODUCTION and (
    not DATABASES["default"].get("USER")
    or DATABASES["default"]["USER"].lower() == "root"
    or not DATABASES["default"].get("PASSWORD")
):
    raise ImproperlyConfigured(
        "Producción requiere un usuario MySQL dedicado, distinto de root y con contraseña."
    )

# Solo durante el traslado: base PostgreSQL de origen, de lectura (manage.py trasladar_base).
if os.environ.get("DATABASE_URL_ORIGEN"):
    DATABASES["origen"] = dj_database_url.parse(os.environ["DATABASE_URL_ORIGEN"], conn_max_age=0)
    if DATABASES["origen"]["ENGINE"] == POSTGRES_ENGINE:
        DATABASES["origen"].setdefault("OPTIONS", {})["connect_timeout"] = 10
        DATABASES["origen"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    elif DATABASES["origen"]["ENGINE"] == MYSQL_ENGINE:
        configurar_mysql(DATABASES["origen"])

# MySQL no admite índices únicos parciales (WHERE). La migración 0006 crea el equivalente
# con una columna generada, así que la advertencia de Django no aplica.
if DATABASES["default"]["ENGINE"] == MYSQL_ENGINE:
    SILENCED_SYSTEM_CHECKS = ["models.W036"]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
DOMAINS_CORREO_ESTUDIANTE = {"uts.edu.co", "correo.uts.edu.co"}
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("UTS_STATIC_ROOT", BASE_DIR / "staticfiles"))
if PRODUCTION:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "tutorias.backends.AccesoLaboratoriosBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
# Compartir IP no debe bloquear a otros estudiantes de la misma red.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_CLIENT_IP_CALLABLE = "tutorias.acceso.direccion_cliente"
AXES_USERNAME_CALLABLE = "tutorias.acceso.identidad_acceso"
AXES_LOCKOUT_TEMPLATE = "registration/acceso_limitado.html"
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_DISABLE_ACCESS_LOG = True
AXES_ENABLE_ACCESS_FAILURE_LOG = False
AXES_SENSITIVE_PARAMETERS = ["username", "ip_address", "password", "csrfmiddlewaretoken"]
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Enlace de recuperación por correo: vence en 1 hora y sirve una sola vez.
PASSWORD_RESET_TIMEOUT = 3600
PASSWORD_RESET_ENABLED = os.environ.get("UTS_PASSWORD_RESET_ENABLED", "0") == "1"
PASSWORD_RESET_ORIGIN = os.environ.get("UTS_PASSWORD_RESET_ORIGIN", "")
# Dirección pública del sitio, para los enlaces de los correos de aviso.
SITIO_URL = (
    os.environ.get("UTS_SITIO_URL") or PASSWORD_RESET_ORIGIN or "http://127.0.0.1:8000"
).rstrip("/")
# Clave temporal que entrega coordinación: horas de validez antes del primer ingreso.
CLAVE_TEMPORAL_HORAS = int(os.environ.get("UTS_CLAVE_TEMPORAL_HORAS", "24"))
# Sin servidor de correo en el equipo local, los correos se guardan como archivos en correos_locales/.
EMAIL_BACKEND = os.environ.get("UTS_EMAIL_BACKEND") or (
    "django.core.mail.backends.filebased.EmailBackend"
    if DEBUG and not os.environ.get("UTS_EMAIL_HOST")
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_FILE_PATH = BASE_DIR / "correos_locales"
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
EMAIL_HOST = os.environ.get("UTS_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("UTS_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("UTS_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("UTS_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("UTS_EMAIL_TLS", "1") == "1"
EMAIL_USE_SSL = os.environ.get("UTS_EMAIL_SSL", "0") == "1"
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("Activa UTS_EMAIL_TLS o UTS_EMAIL_SSL, no ambos.")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("UTS_EMAIL_FROM", "")

# Avisos a coordinación por cada nueva solicitud de laboratorio.
# Correos separados por comas; vacío = correos de todos los coordinadores activos.
NOTIFICAR_CORREOS = [
    c.strip() for c in os.environ.get("UTS_NOTIFICAR_CORREOS", "").split(",") if c.strip()
]
# Opcional y gratuito: aviso instantáneo al celular por Telegram.
TELEGRAM_BOT_TOKEN = os.environ.get("UTS_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("UTS_TELEGRAM_CHAT_ID", "")
# El envío corre en segundo plano para que el estudiante no espere al servidor de correo.
NOTIFICACIONES_EN_SEGUNDO_PLANO = os.environ.get("UTS_NOTIFICACIONES_SEGUNDO_PLANO", "1") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "()": "tutorias_uts.logging.FormatoPrivado" if PRODUCTION else "logging.Formatter",
            "format": "{asctime} {levelname} {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "console"}},
    "loggers": {
        "tutorias": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}


# Al iniciar runserver se indica qué base de datos se está usando.
if (
    DEBUG
    and len(sys.argv) > 1
    and sys.argv[1] == "runserver"
    and os.environ.get("RUN_MAIN") != "true"
):
    _db = DATABASES["default"]
    if _db["ENGINE"] == MYSQL_ENGINE:
        print(
            f"Base de datos: MySQL/MariaDB · {_db['NAME']} en {_db.get('HOST') or 'localhost'}",
            file=sys.stderr,
        )
    else:
        print(
            "AVISO: usando SQLite (db.sqlite3). Para MariaDB define DATABASE_URL en el archivo .env",
            file=sys.stderr,
        )
    if EMAIL_BACKEND.endswith("filebased.EmailBackend"):
        print(
            f"Correo: modo local, NO se envia a Internet; archivos en {EMAIL_FILE_PATH}",
            file=sys.stderr,
        )
    elif EMAIL_BACKEND.endswith("smtp.EmailBackend"):
        print(f"Correo: SMTP {EMAIL_HOST} como {EMAIL_HOST_USER}", file=sys.stderr)
