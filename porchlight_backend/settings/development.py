"""Development settings for Porchlight Django."""
from .base import *  # noqa: F401, F403

DEBUG = True
ADMIN_ENABLED = True

ALLOWED_HOSTS = ['*']

# Development CORS settings. Keep the list explicit so credentialed requests
# are limited to the local web and Capacitor frontends.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost,capacitor://localhost,ionic://localhost',
    ).split(',')
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Development database configuration
# Defaults to SQLite for local development; allows overriding with local Postgres/PostGIS if configured
if os.getenv('DATABASE_URL') or os.getenv('USE_POSTGRES', 'False').lower() in ('true', '1', 't'):
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(database_url)
        engine = os.getenv(
            'DB_ENGINE',
            'django.contrib.gis.db.backends.postgis'
            if 'postgis' in parsed.scheme or 'postgres' in parsed.scheme
            else parsed.scheme,
        )
        DATABASES = {
            'default': {
                'ENGINE': engine,
                'NAME': parsed.path.lstrip('/'),
                'USER': parsed.username or '',
                'PASSWORD': parsed.password or '',
                'HOST': parsed.hostname or '',
                'PORT': str(parsed.port or 5432),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': os.getenv('DB_ENGINE', 'django.contrib.gis.db.backends.postgis'),
                'NAME': os.getenv('DB_NAME', os.getenv('POSTGRES_DB', 'porchlight_dev')),
                'USER': os.getenv('DB_USER', os.getenv('POSTGRES_USER', 'porchlight')),
                'PASSWORD': os.getenv('DB_PASSWORD', os.getenv('POSTGRES_PASSWORD', '')),
                'HOST': os.getenv('DB_HOST', os.getenv('POSTGRES_HOST', 'localhost')),
                'PORT': os.getenv('DB_PORT', os.getenv('POSTGRES_PORT', '5432')),
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Disable strict password validation in development if desired for easy testing
AUTH_PASSWORD_VALIDATORS = []

# MailPit accepts SMTP messages locally and exposes them at http://localhost:8025.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', '127.0.0.1')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '1025'))
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
