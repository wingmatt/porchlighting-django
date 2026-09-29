"""Production settings for Porchlight Django."""
import os
from .base import *  # noqa: F401, F403

DEBUG = False
ADMIN_ENABLED = False

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# Strict CORS settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()
]

# Database configuration for PostgreSQL with PostGIS in production
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.contrib.gis.db.backends.postgis'),
        'NAME': os.getenv('DB_NAME', os.getenv('POSTGRES_DB', 'porchlight')),
        'USER': os.getenv('DB_USER', os.getenv('POSTGRES_USER', 'porchlight')),
        'PASSWORD': os.getenv('DB_PASSWORD', os.getenv('POSTGRES_PASSWORD', '')),
        'HOST': os.getenv('DB_HOST', os.getenv('POSTGRES_HOST', 'localhost')),
        'PORT': os.getenv('DB_PORT', os.getenv('POSTGRES_PORT', '5432')),
    }
}

# Support DATABASE_URL in production if provided
database_url = os.getenv('DATABASE_URL')
if database_url:
    import urllib.parse
    parsed = urllib.parse.urlparse(database_url)
    engine = os.getenv(
        'DB_ENGINE',
        'django.contrib.gis.db.backends.postgis'
        if 'postgis' in parsed.scheme or 'postgres' in parsed.scheme
        else parsed.scheme
    )
    DATABASES['default'] = {
        'ENGINE': engine,
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username or '',
        'PASSWORD': parsed.password or '',
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or 5432),
    }

# Enable GeoDjango in production
if 'django.contrib.gis' not in INSTALLED_APPS:
    INSTALLED_APPS = list(INSTALLED_APPS) + ['django.contrib.gis']

# Security settings
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() == 'true'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# SendGrid SMTP configuration. The API key is supplied as the SMTP password
# and must never be committed to source control.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'apikey')
EMAIL_HOST_PASSWORD = os.getenv('SENDGRID_API_KEY', '')
