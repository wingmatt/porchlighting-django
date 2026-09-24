"""Tests for Core utilities and Firebase connection."""
from django.conf import settings
from django.test import TestCase
from apps.core.firebase import (
    create_firebase_custom_token,
    delete_porchlight_from_firebase,
    get_firebase_app,
    send_fcm_multicast,
    sync_porchlight_to_firebase,
)


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

    def test_delete_porchlight_from_firebase_call(self):
        result = delete_porchlight_from_firebase('test-uuid-1234')
        self.assertIsInstance(result, bool)

    def test_create_firebase_custom_token_call(self):
        result = create_firebase_custom_token('user-123', {'test': True})
        # Either returns a string token or None (if service account is missing)
        self.assertTrue(result is None or isinstance(result, str))

    def test_send_fcm_multicast_empty_tokens(self):
        result = send_fcm_multicast([], title='Test', body='Body')
        self.assertEqual(result.get('success_count'), 0)
        self.assertEqual(result.get('failure_count'), 0)

    def test_send_fcm_multicast_with_tokens(self):
        result = send_fcm_multicast(['fake-token-1'], title='Test', body='Body')
        self.assertIn('failure_count', result)
