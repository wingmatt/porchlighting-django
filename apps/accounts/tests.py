"""Tests for custom User model and accounts authentication."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import FCMDeviceToken

User = get_user_model()


class UserModelTests(TestCase):
    """Test custom User model behavior."""

    def test_create_user_with_email_successful(self):
        email = 'test@example.com'
        password = 'SecurePassword123!'
        user = User.objects.create_user(email=email, password=password, first_name='Test', last_name='User')

        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.full_name, 'Test User')

    def test_create_user_without_email_raises_error(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='password123')

    def test_create_superuser_successful(self):
        email = 'admin@example.com'
        password = 'AdminPassword123!'
        admin = User.objects.create_superuser(email=email, password=password)

        self.assertEqual(admin.email, email)
        self.assertTrue(admin.check_password(password))
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthAPITests(TestCase):
    """Test Auth API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('accounts:register')
        self.login_url = reverse('accounts:login')
        self.me_url = reverse('accounts:me')

    def test_register_user_api(self):
        payload = {
            'email': 'newuser@example.com',
            'password': 'StrongPassword123',
            'password_confirm': 'StrongPassword123',
            'first_name': 'Jane',
            'last_name': 'Doe',
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user']['email'], 'newuser@example.com')
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Confirm your email address', mail.outbox[0].body)

    def test_confirm_email_activates_user_and_is_one_time(self):
        user = User.objects.create_user(email='confirm@example.com', password='Password123!', is_active=False)
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        url = reverse('accounts:confirm-email', kwargs={'uidb64': uid, 'token': token})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_user_api(self):
        User.objects.create_user(email='login@example.com', password='Password123!')
        payload = {'email': 'login@example.com', 'password': 'Password123!'}
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_me_api_authenticated(self):
        user = User.objects.create_user(email='me@example.com', password='Password123!', first_name='Me')
        self.client.force_authenticate(user=user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'me@example.com')
        self.assertEqual(response.data['first_name'], 'Me')

    def test_fcm_token_registration_authenticated_user(self):
        user = User.objects.create_user(email='fcm_user@example.com', password='Password123!')
        self.client.force_authenticate(user=user)
        url = reverse('accounts:fcm-register')
        payload = {
            'registration_token': 'test-fcm-token-12345',
            'device_id': 'device-abc',
            'device_type': 'android',
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(FCMDeviceToken.objects.filter(user=user, registration_token='test-fcm-token-12345').exists())

    def test_fcm_token_registration_guest(self):
        url = reverse('accounts:fcm-register')
        payload = {
            'registration_token': 'test-fcm-token-guest',
            'device_id': 'device-guest',
            'device_type': 'ios',
            'guest_token': 'guest-token-123',
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(FCMDeviceToken.objects.filter(guest_token='guest-token-123', registration_token='test-fcm-token-guest').exists())

    def test_fcm_token_unregister(self):
        token = FCMDeviceToken.objects.create(registration_token='token-to-delete', device_id='d1')
        self.assertTrue(token.is_active)
        url = reverse('accounts:fcm-unregister')
        res = self.client.post(url, {'registration_token': 'token-to-delete'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        token.refresh_from_db()
        self.assertFalse(token.is_active)

    def test_firebase_token_endpoint(self):
        user = User.objects.create_user(email='fbuser@example.com', password='Password123!')
        self.client.force_authenticate(user=user)
        url = reverse('accounts:firebase-token')
        res = self.client.get(url)
        # Firebase custom token generation may fail if credentials aren't present in test env or succeed if mock/dev
        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE])
