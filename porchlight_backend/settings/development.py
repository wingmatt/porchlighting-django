"""Development settings for Porchlight Django."""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ['*']

# Development CORS settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Disable strict password validation in development if desired for easy testing
AUTH_PASSWORD_VALIDATORS = []

# Optional: Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
