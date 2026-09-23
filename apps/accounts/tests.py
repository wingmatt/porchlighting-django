"""Tests for custom User model and accounts authentication."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

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
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['email'], 'newuser@example.com')

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
