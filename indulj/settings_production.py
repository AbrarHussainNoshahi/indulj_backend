from .settings import *
import os
import dj_database_url
from decouple import config


# ─────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────

DEBUG = False

SECRET_KEY = config("SECRET_KEY")

ALLOWED_HOSTS = [
    ".railway.app",
    ".up.railway.app",
    "indulj.vercel.app",
    "indulj-v1.vercel.app",
    "localhost",
    "127.0.0.1",
]

RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if RAILWAY_PUBLIC_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)


# ─────────────────────────────────────────────
# Database — Railway PostgreSQL
# ─────────────────────────────────────────────

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True,
    )
}


# ─────────────────────────────────────────────
# CORS / CSRF
# ─────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = [
    "https://indulj.vercel.app",
    "https://indulj-v1.vercel.app",
]

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "https://indulj.vercel.app",
    "https://indulj-v1.vercel.app",
    "https://*.railway.app",
    "https://*.up.railway.app",
]


# ─────────────────────────────────────────────
# HTTPS / Cookies
# ─────────────────────────────────────────────

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Keep False first on Railway to avoid redirect-loop issues.
# You can turn it True later after testing.
SECURE_SSL_REDIRECT = False

SIMPLE_JWT["AUTH_COOKIE_SECURE"] = True
SIMPLE_JWT["AUTH_COOKIE_SAMESITE"] = "None"
SIMPLE_JWT["AUTH_COOKIE_HTTP_ONLY"] = True


# ─────────────────────────────────────────────
# Static files — WhiteNoise
# ─────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

USE_CLOUDINARY = config("USE_CLOUDINARY", default=False, cast=bool)

if USE_CLOUDINARY:
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": config("CLOUDINARY_CLOUD_NAME", default=""),
        "API_KEY": config("CLOUDINARY_API_KEY", default=""),
        "API_SECRET": config("CLOUDINARY_API_SECRET", default=""),
    }
    STORAGES = {
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
        "documents": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
        "documents": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }


# ─────────────────────────────────────────────
# Email — Gmail SMTP
# ─────────────────────────────────────────────

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

EMAIL_HOST_USER = config("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

EMAIL_TIMEOUT = 20


# ─────────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────────

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")


# ─────────────────────────────────────────────
# Production safety
# ─────────────────────────────────────────────

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
]