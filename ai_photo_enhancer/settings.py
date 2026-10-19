"""Django settings for the AI Photo Enhancer project."""
import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "0.0.0.0"]),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-dev-only-change-me-before-production",
)
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "enhancer.apps.EnhancerConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ai_photo_enhancer.urls"

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
                "enhancer.context_processors.engine_status",
            ],
        },
    },
]

WSGI_APPLICATION = "ai_photo_enhancer.wsgi.application"
ASGI_APPLICATION = "ai_photo_enhancer.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Manifest storage (cache-busting) is only used in production where
        # `collectstatic` has been run; in dev the plain backend avoids
        # "missing from manifest" errors during runserver.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Upload limits & validation
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=25)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = env.int("MAX_IMAGE_PIXELS", default=40_000_000)

ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
ALLOWED_IMAGE_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
]

# ---------------------------------------------------------------------------
# Real-ESRGAN (NCNN Vulkan) engine
# ---------------------------------------------------------------------------
REALESRGAN_BINARY = BASE_DIR / env("REALESRGAN_BINARY", default="bin/realesrgan-ncnn-vulkan")
REALESRGAN_MODELS_DIR = BASE_DIR / env("REALESRGAN_MODELS_DIR", default="bin/models")
REALESRGAN_GPU_ID = env.int("REALESRGAN_GPU_ID", default=-1)  # -1 = auto
REALESRGAN_MAX_WORKERS = env.int("REALESRGAN_MAX_WORKERS", default=1)
REALESRGAN_TIMEOUT_SECONDS = env.int("REALESRGAN_TIMEOUT_SECONDS", default=600)
REALESRGAN_DEFAULT_TILE = env.int("REALESRGAN_DEFAULT_TILE", default=0)  # 0 = auto

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
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
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "enhancer": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Production hardening (active when DEBUG=False)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Vercel (serverless) deployment overrides
# ---------------------------------------------------------------------------
if os.environ.get("VERCEL"):
    DEBUG = False
    ALLOWED_HOSTS = [".vercel.app", ".now.sh", "localhost", "127.0.0.1"]
    SECURE_SSL_REDIRECT = False
    # The function sandbox is ephemeral/read-only outside /tmp.
    DATABASES["default"]["NAME"] = "/tmp/db.sqlite3"
    MEDIA_ROOT = Path("/tmp/media")
    MEDIA_URL = "/media/"
    # Serve media through the app (there is no persistent volume).
    SERVE_MEDIA = True
    WHITENOISE_MANIFEST_STRICT = False
else:
    SERVE_MEDIA = env.bool("SERVE_MEDIA", default=False)

# Recompute now that DEBUG may have been flipped above.
STORAGES["staticfiles"]["BACKEND"] = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "ai_photo_enhancer.storage.ForgivingCompressedManifestStaticFilesStorage"
)
