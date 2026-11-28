"""Django settings for the NewCompany project."""

import os
import re
from pathlib import Path
from django.urls import include, path
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def env_list(name, default=""):
    return [
        value.strip()
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    ]


def first_env_value(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


PLACEHOLDER_DATABASE_HOSTS = {
    "host",
    "hostname",
    "example.com",
    "localhost.localdomain",
}
REDACTED_ENV_VALUES = {"[SENSITIVE]", "SENSITIVE", "***", "*****"}


def clean_database_url(value):
    value = value.strip().strip("'\"")
    if value in REDACTED_ENV_VALUES:
        return ""

    match = re.search(r"""(?:postgres|postgresql)://[^\s'"]+""", value)
    return match.group(0) if match else value


def is_usable_database_url(value):
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        return False

    return (
        parsed.scheme in {"postgres", "postgresql"}
        and bool(hostname)
        and hostname not in PLACEHOLDER_DATABASE_HOSTS
    )


def first_database_url(*names):
    for name in names:
        raw_value = os.environ.get(name)
        if not raw_value:
            continue

        value = clean_database_url(raw_value)
        if value and "://" not in value:
            referenced_value = os.environ.get(value)
            if referenced_value:
                value = clean_database_url(referenced_value)

        if value and is_usable_database_url(value):
            return value

    return None


def database_url_requires_ssl(database_url):
    parsed = urlparse(database_url)
    return (
        parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        and "sslmode=" not in parsed.query
    )


def fallback_database_config():
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "NewCompany"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": (
            os.environ.get("LOCAL_DB_PASSWORD")
            or os.environ.get("POSTGRES_PASSWORD", "postgres")
        ),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }


IS_VERCEL_RUNTIME = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", not IS_VERCEL_RUNTIME))
SECRET_KEY = os.environ.get("SECRET_KEY")

VERCEL_CONFIGURATION_ERRORS = []
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-key"
    else:
        VERCEL_CONFIGURATION_ERRORS.append(
            "Set SECRET_KEY to a unique production value."
        )


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}


vercel_host = os.environ.get("VERCEL_URL", "").strip()
default_allowed_hosts = "127.0.0.1,localhost,.vercel.app"
default_csrf_origins = "https://*.vercel.app"

if vercel_host:
    default_allowed_hosts = f"{default_allowed_hosts},{vercel_host}"
    default_csrf_origins = f"{default_csrf_origins},https://{vercel_host}"

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    os.environ.get("ALLOWED_HOSTS", default_allowed_hosts),
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", default_csrf_origins)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "webroaster",
    "banking",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "webroaster.middleware.VercelConfigurationMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "webroaster.middleware.PasswordExpiryMiddleware",
    "webroaster.middleware.RequestAuditMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "NewCompany.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "NewCompany.wsgi.application"


# Database
database_url_aliases = (
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "postgresql",
)

# A supplied DATABASE_URL takes priority over integration-provided aliases.
if "DATABASE_URL" in os.environ:
    DATABASE_URL = first_database_url("DATABASE_URL")
else:
    DATABASE_URL = first_database_url(*database_url_aliases)

database_url_configured = (
    "DATABASE_URL" in os.environ
    or any(name in os.environ for name in database_url_aliases)
)

if DATABASE_URL:
    try:
        database_config = dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            conn_health_checks=True,
            ssl_require=database_url_requires_ssl(DATABASE_URL),
        )
    except Exception:
        raise ImproperlyConfigured(
            "Could not parse the PostgreSQL connection URL. "
            "Copy the complete connection string from Neon."
        ) from None

    database_host = database_config.get("HOST")
    if not database_host or not database_config.get("NAME"):
        raise ImproperlyConfigured(
            "The PostgreSQL connection URL must include a host "
            "and a database name."
        )

    if IS_VERCEL_RUNTIME and database_host.lower() in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ImproperlyConfigured(
            "Vercel requires a hosted PostgreSQL database. "
            "Set DATABASE_URL to the Neon connection string."
        )

    DATABASES = {"default": database_config}

elif database_url_configured or IS_VERCEL_RUNTIME:
    raise ImproperlyConfigured(
        "Set DATABASE_URL to a complete postgres:// or postgresql:// "
        "connection string for the intended database."
    )

else:
    DATABASES = {"default": fallback_database_config()}


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


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "NewCompany" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.environ.get(
        "DJANGO_MEDIA_ROOT",
        "/tmp/newcompany-media" if IS_VERCEL_RUNTIME else str(BASE_DIR / "media"),
    )
)


LOGIN_URL = "/staff/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
COMPANY_NAME = "NewCompany"

EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", bool(EMAIL_HOST) and EMAIL_PORT == 465)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", bool(EMAIL_HOST) and EMAIL_PORT == 587)
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "15"))
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "webmaster@localhost",
)


SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "SAMEORIGIN"

SECURE_HSTS_SECONDS = int(
    os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    not DEBUG,
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", not DEBUG)

SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_COOKIE_AGE", "1800"))
SESSION_SAVE_EVERY_REQUEST = True