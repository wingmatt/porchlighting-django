"""Base settings shared across all environments."""
import os
from pathlib import Path
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'insecure-django-dev-secret-key-change-in-prod')

DEBUG = False

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    # Local apps
    'apps.accounts',
    'apps.porchlights',
    'apps.core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.GuestAuthMiddleware',
]

CORS_ALLOW_HEADERS = (*default_headers, 'x-guest-name', 'x-guest-token')

ROOT_URLCONF = 'porchlight_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'frontend' / 'dist'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'porchlight_backend.wsgi.application'
ASGI_APPLICATION = 'porchlight_backend.asgi.application'

# Database defaults to SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Custom User Model with email-only login
AUTH_USER_MODEL = 'accounts.User'

# Email configuration. Environment-specific settings select the backend and
# credentials; these values are shared by development and production.
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@porchlight.local')
EMAIL_CONFIRMATION_URL = os.getenv(
    'EMAIL_CONFIRMATION_URL',
    'http://localhost:5173/confirm-email/{uid}/{token}/',
)
PASSWORD_RESET_URL = os.getenv(
    'PASSWORD_RESET_URL',
    'http://localhost:5173/forgot-password/{uid}/{token}/',
)
MAGIC_LOGIN_URL = os.getenv(
    'MAGIC_LOGIN_URL',
    'http://localhost:5173/magic-login/{uid}/{token}/',
)

# Optional observability integrations. Startup modules initialize the SDKs only
# when their respective credentials are configured.
SENTRY_DSN = os.getenv('SENTRY_DSN', '')
SENTRY_ENVIRONMENT = os.getenv('SENTRY_ENVIRONMENT', os.getenv('DJANGO_ENV', 'development'))
SENTRY_TRACES_SAMPLE_RATE = os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')
SENTRY_PROFILES_SAMPLE_RATE = os.getenv('SENTRY_PROFILES_SAMPLE_RATE', '0.0')
NEW_RELIC_ENABLED = os.getenv('NEW_RELIC_ENABLED', 'False').lower() in ('true', '1', 't')
NEW_RELIC_APP_NAME = os.getenv('NEW_RELIC_APP_NAME', 'Porchlight Django')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [d for d in [BASE_DIR / 'static', BASE_DIR / 'frontend' / 'dist'] if d.exists()]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('DRF_ANON_RATE', '100/hour'),
        'user': os.getenv('DRF_USER_RATE', '1000/hour'),
        'auth': os.getenv('DRF_AUTH_RATE', '10/minute'),
        'guest': os.getenv('DRF_GUEST_RATE', '60/minute'),
    },
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}

# Browser security defaults. Production overrides the transport settings below,
# while these values remain safe for API clients and local development.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'

# Firebase Configuration
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', None)
FIREBASE_DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', '')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', '')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET', '')
GEOCODIO_API_KEY = os.getenv('GEOCODIO_API_KEY', '')
WEB_PUSH_VAPID_PUBLIC_KEY = os.getenv('WEB_PUSH_VAPID_PUBLIC_KEY', '')
WEB_PUSH_VAPID_PRIVATE_KEY = os.getenv('WEB_PUSH_VAPID_PRIVATE_KEY', '')
WEB_PUSH_VAPID_CLAIMS = os.getenv('WEB_PUSH_VAPID_CLAIMS', '')

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'memory://')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', None)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() in ('true', '1', 't')
