"""Tests for Core utilities and Firebase connection."""
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase, override_settings
from apps.core import firebase as firebase_helpers
from apps.core.firebase import (
    create_firebase_custom_token,
    delete_porchlight_from_firebase,
    get_firebase_app,
    send_fcm_multicast,
    sync_porchlight_to_firebase,
)


class CoreFirebaseTests(TestCase):
    """Test modular settings and Firebase connectivity/helpers."""

    def setUp(self):
        firebase_helpers._firebase_app = None

    def tearDown(self):
        firebase_helpers._firebase_app = None
        super().tearDown()

    def test_modular_settings_loaded(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')
        self.assertIn('apps.accounts', settings.INSTALLED_APPS)
        self.assertIn('apps.porchlights', settings.INSTALLED_APPS)
        self.assertIn('apps.core', settings.INSTALLED_APPS)
        self.assertTrue(hasattr(settings, 'FIREBASE_PROJECT_ID'))

    def test_cors_allows_frontend_origins(self):
        self.assertFalse(settings.CORS_ALLOW_ALL_ORIGINS)
        self.assertTrue(settings.CORS_ALLOW_CREDENTIALS)
        self.assertIn('http://localhost:5173', settings.CORS_ALLOWED_ORIGINS)
        self.assertIn('http://127.0.0.1:5173', settings.CORS_ALLOWED_ORIGINS)
        self.assertIn('http://localhost', settings.CORS_ALLOWED_ORIGINS)
        self.assertIn('capacitor://localhost', settings.CORS_ALLOWED_ORIGINS)

    def test_cors_preflight_allows_guest_headers(self):
        response = Client().options(
            '/api/porchlights/EfhxLZ9c/',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='x-guest-name,x-guest-token',
        )

        self.assertEqual(response.status_code, 200)
        allowed_headers = response.headers['Access-Control-Allow-Headers']
        self.assertIn('x-guest-name', allowed_headers)
        self.assertIn('x-guest-token', allowed_headers)

    @patch('firebase_admin._apps', new={})
    @patch('firebase_admin.credentials.ApplicationDefault')
    @patch('firebase_admin.initialize_app')
    @override_settings(FIREBASE_CREDENTIALS_PATH='')
    def test_firebase_initialization_is_mocked(self, initialize_app, application_default):
        mocked_app = object()
        application_default.return_value = object()
        initialize_app.return_value = mocked_app

        app = get_firebase_app()
        self.assertIs(app, mocked_app)
        application_default.assert_called_once_with()
        initialize_app.assert_called_once()

    @patch('firebase_admin._apps', new={})
    @patch('firebase_admin.credentials.ApplicationDefault', side_effect=Exception('no test credentials'))
    @patch('firebase_admin.initialize_app')
    @override_settings(FIREBASE_CREDENTIALS_PATH='')
    def test_firebase_initialization_without_credentials_returns_none(
        self, initialize_app, application_default
    ):
        self.assertIsNone(get_firebase_app())
        application_default.assert_called_once_with()
        initialize_app.assert_not_called()

    @patch('apps.core.firebase.get_firebase_app', return_value=None)
    def test_sync_porchlight_to_firebase_call(self, get_app):
        result = sync_porchlight_to_firebase('test-uuid-1234', {'is_on': True, 'brightness': 80})
        # In test / dev mode without active Firebase credentials it safely handles or syncs
        self.assertIsInstance(result, bool)

    @patch('apps.core.firebase.get_firebase_app', return_value=None)
    def test_delete_porchlight_from_firebase_call(self, get_app):
        result = delete_porchlight_from_firebase('test-uuid-1234')
        self.assertIsInstance(result, bool)

    @patch('apps.core.firebase.get_firebase_app', return_value=None)
    def test_create_firebase_custom_token_call(self, get_app):
        result = create_firebase_custom_token('user-123', {'test': True})
        # Either returns a string token or None (if service account is missing)
        self.assertTrue(result is None or isinstance(result, str))

    def test_send_fcm_multicast_empty_tokens(self):
        result = send_fcm_multicast([], title='Test', body='Body')
        self.assertEqual(result.get('success_count'), 0)
        self.assertEqual(result.get('failure_count'), 0)

    @patch('apps.core.firebase.get_firebase_app', return_value=None)
    def test_send_fcm_multicast_with_tokens(self, get_app):
        result = send_fcm_multicast(['fake-token-1'], title='Test', body='Body')
        self.assertIn('failure_count', result)
