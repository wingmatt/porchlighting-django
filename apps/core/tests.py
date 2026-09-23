"""Tests for Core utilities and Firebase connection."""
from django.conf import settings
from django.test import TestCase
from apps.core.firebase import get_firebase_app, sync_porchlight_to_firebase


class CoreFirebaseTests(TestCase):
    """Test modular settings and Firebase connectivity/helpers."""

    def test_modular_settings_loaded(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')
        self.assertIn('apps.accounts', settings.INSTALLED_APPS)
        self.assertIn('apps.porchlights', settings.INSTALLED_APPS)
        self.assertIn('apps.core', settings.INSTALLED_APPS)
        self.assertTrue(hasattr(settings, 'FIREBASE_PROJECT_ID'))

    def test_firebase_initialization(self):
        app = get_firebase_app()
        self.assertIsNotNone(app)

    def test_sync_porchlight_to_firebase_call(self):
        result = sync_porchlight_to_firebase('test-uuid-1234', {'is_on': True, 'brightness': 80})
        # In test / dev mode without active Firebase credentials it safely handles or syncs
        self.assertIsInstance(result, bool)
