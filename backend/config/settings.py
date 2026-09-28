"""
Django settings for the DocuMind backend.

This file intentionally reads everything sensitive from environment
variables (via .env) rather than hardcoding it, so the same settings
file works in local dev and in production — only the .env changes.
"""
import os
from pathlib import Path
from datetime import timedelta
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from the .env file at the project root (chat_bot/.env).
# In production (Render, etc.) there usually is no .env file — the host's
# own environment variable panel provides these instead, and load_dotenv()
# simply does nothing if the file doesn't exist, so this line is safe either way.
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    # DocuMind apps
    "users",
    "documents",
    "chat",
    "usage",
    "subscriptions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files (like the Django admin's CSS/JS)
    # directly from Django in production — without it, the admin panel
    # renders as unstyled plain HTML once DEBUG=False, since Django stops
    # auto-serving static files outside of local development.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

# ---- Database ----
# Falls back to SQLite for zero-friction local development if DATABASE_URL
# isn't set. Switch to the Postgres DATABASE_URL from .env once Postgres
# (with pgvector) is running — see README for setup instructions.
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
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

STATIC_URL = "static/"
# Where `collectstatic` gathers static files to, for WhiteNoise to serve in
# production. Not needed for local dev (runserver serves static files
# itself when DEBUG=True), but required once DEBUG=False.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Media files (user uploads: documents, avatars) ----
# Explicitly set rather than left as Django's default ('', which resolves
# relative to wherever the server process happens to be started from) —
# pinning it to BASE_DIR means uploads always land in the same place
# regardless of your current working directory when you run runserver.
#
# HONEST PRODUCTION NOTE: this stores uploaded files on local disk, which
# works for local dev, but most free hosting tiers (including Render's
# free plan) do NOT guarantee that disk persists across restarts/redeploys.
# Document TEXT/embeddings live safely in the database, so chat and study
# features keep working — but the original uploaded files and avatar
# images can disappear. The proper fix is object storage (e.g. Cloudflare
# R2), which hasn't been added yet.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---- DRF / JWT ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# ---- CORS ----
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173"
).split(",")

# ---- CSRF ----
# Only matters for cookie/session-authenticated requests (e.g. the Django
# admin login form) — the JWT-authenticated API itself isn't cookie-based,
# so this doesn't affect normal app usage. Still needed so /admin/ works
# correctly if ever accessed over HTTPS on a production domain.
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []

# ---- Security (only meaningfully active when DEBUG=False, i.e. production) ----
if not DEBUG:
    # Render (like most hosts) terminates HTTPS at its own proxy and then
    # talks plain HTTP to Django. Without this line, Django never learns the
    # ORIGINAL request was HTTPS, so SECURE_SSL_REDIRECT below would redirect
    # every request to HTTPS forever — an infinite redirect loop. This tells
    # Django to trust the proxy's X-Forwarded-Proto header instead.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---- Internal service-to-service auth (Django -> FastAPI) ----
FASTAPI_BASE_URL = os.environ.get("FASTAPI_BASE_URL", "http://localhost:8001")
FASTAPI_INTERNAL_KEY = os.environ.get("FASTAPI_INTERNAL_KEY", "changeme-shared-secret")

# ---- SaaS plan limits (configurable, not hardcoded per-feature) ----
FREE_MAX_DOCUMENTS = int(os.environ.get("FREE_MAX_DOCUMENTS", 5))
FREE_MAX_QUESTIONS = int(os.environ.get("FREE_MAX_QUESTIONS", 30))
PRO_MAX_DOCUMENTS = int(os.environ.get("PRO_MAX_DOCUMENTS", 100))
PRO_MAX_QUESTIONS = int(os.environ.get("PRO_MAX_QUESTIONS", 1000))
