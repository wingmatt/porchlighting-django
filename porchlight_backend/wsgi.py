"""WSGI config for porchlight_backend project."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'porchlight_backend.settings')

from django.core.wsgi import get_wsgi_application

from porchlight_backend.monitoring import initialize_new_relic, initialize_sentry

initialize_new_relic()
initialize_sentry()
application = get_wsgi_application()
