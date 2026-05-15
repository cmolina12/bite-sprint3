"""
Django settings for BITE.co Manejador de Reportes (Sprint 3).

Toda la configuración sensible se lee de variables de entorno (/etc/environment
en las EC2, similar a como hacen los labs del curso ISIS-2503).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# SECURITY
# =============================================================================
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-secret-key-only-for-local-NEVER-use-in-prod-change-me-please"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# ALLOWED_HOSTS = '*' porque el tráfico siempre viene del ALB y de Kong,
# nunca directo de internet. El ALB añade el Host header del cliente original.
ALLOWED_HOSTS = ["*"]

# Trust X-Forwarded-* headers del ALB y Kong (estamos detrás de 2 proxies)
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # BITE.co apps
    "reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # CSRF deshabilitado en /api/ porque usaremos JWT en lugar de cookies (Etapa 3)
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # ETAPA 3: Validación de tenant (ASR-SEG-01).
    # Si AUTH0_DOMAIN no está configurado, el middleware actúa en modo permisivo
    # (deja pasar todo) — útil para Etapa 1 antes de configurar Auth0.
    "reportes.middleware.tenant_auth.TenantAuthorizationMiddleware",
]

ROOT_URLCONF = "bite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bite.wsgi.application"

# =============================================================================
# DATABASE — PostgreSQL en RDS
# =============================================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": os.environ.get("DB_NAME", "bitedb"),
        "USER": os.environ.get("DB_USER", "biteadmin"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        # Connection pool — importante para evitar agotar conexiones de RDS
        # cuando 3 instancias × 4 gunicorn workers = 12 conexiones simultáneas.
        "CONN_MAX_AGE": 60,
    }
}

# =============================================================================
# CACHE — ElastiCache Redis
# =============================================================================
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 2,
            "SOCKET_TIMEOUT": 2,
            # Si Redis cae, no queremos que la app caiga con él
            "IGNORE_EXCEPTIONS": True,
        },
    }
}
DJANGO_REDIS_IGNORE_EXCEPTIONS = True

# =============================================================================
# AUTH — preparado para Auth0 (Etapa 3)
# =============================================================================
# Estos valores se llenan en la Etapa 3. Por ahora, vacíos.
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://bite.co/api")
AUTH0_TENANT_CLAIM = os.environ.get(
    "AUTH0_TENANT_CLAIM",
    f"{AUTH0_DOMAIN}/tenant_id" if AUTH0_DOMAIN else "tenant_id"
)

# Auth0 Management API (Etapa 4 - SEG-02, para bloqueo automático de cuentas)
AUTH0_MGMT_CLIENT_ID = os.environ.get("AUTH0_MGMT_CLIENT_ID", "")
AUTH0_MGMT_CLIENT_SECRET = os.environ.get("AUTH0_MGMT_CLIENT_SECRET", "")

# =============================================================================
# RABBITMQ — preparado para notificaciones (Etapa 4)
# =============================================================================
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
RABBITMQ_NOTIFICATIONS_QUEUE = "bite.security.notifications"

# =============================================================================
# I18N / TIMEZONE
# =============================================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC
# =============================================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# LOGGING — logs a stdout (los recoge journald en la EC2 + CloudWatch si se configura)
# =============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} ({module}.{funcName}:{lineno}) — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.db.backends": {
            "level": "WARNING",  # silencia SQL queries en INFO
        },
        "reportes": {
            "level": "DEBUG" if DEBUG else "INFO",
        },
    },
}

# Identificador de instancia (lo setea cloud-init con el instance-id de EC2)
# Útil para verificar el round-robin del ALB en el Experimento 1
INSTANCE_ID = os.environ.get("EC2_INSTANCE_ID", "local-dev")
