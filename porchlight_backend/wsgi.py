"""WSGI config for porchlight_backend project."""
import os

# The web server entry point must never load development settings, even if a
# stale service environment variable is present.
os.environ['DJANGO_ENV'] = 'production'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'porchlight_backend.settings')

from django.core.wsgi import get_wsgi_application

from porchlight_backend.monitoring import initialize_new_relic, initialize_sentry

initialize_new_relic()
initialize_sentry()
application = get_wsgi_application()
