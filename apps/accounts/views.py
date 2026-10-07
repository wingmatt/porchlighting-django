"""API Views for accounts registration, login, logout, and profile management."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import Http404
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.firebase import create_firebase_custom_token
from apps.porchlights.models import GuestSession, Permission
from .models import FCMDeviceToken, WebPushSubscription
from .serializers import (
    FCMDeviceTokenSerializer,
    FCMDeviceTokenUnregisterSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
    WebPushSubscriptionSerializer,
)

User = get_user_model()


def _request_guest_token(request):
    """Return only the middleware/header guest credential, never body or URL input."""
    return getattr(request, 'guest_token', None) or request.headers.get('X-Guest-Token')


def _valid_guest_token(token):
    """Check that a guest credential still maps to an active access grant."""
    if not token:
        return False
    session = GuestSession.objects.select_related('invitation').filter(guest_token=token).first()
    return bool(session and session.is_valid()) or Permission.objects.filter(guest_id=token).exists()


def _request_actor(request):
    """Return the authenticated user or a validated guest token, exclusively."""
    if request.user and request.user.is_authenticated:
        return request.user, None
    guest_token = _request_guest_token(request)
    if _valid_guest_token(guest_token):
        return None, guest_token
    return None, None


class RegisterView(generics.CreateAPIView):
    """Register a new user with email and password."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        confirmation_token = default_token_generator.make_token(user)
        confirmation_url = settings.EMAIL_CONFIRMATION_URL.format(
            uid=uid,
            token=confirmation_token,
        )
        send_mail(
            subject='Confirm your Porchlight account',
            message=(
                f'Welcome to Porchlight! Confirm your email address by visiting:\n\n'
                f'{confirmation_url}\n\n'
                'This link can only be used once.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return Response(
            {
                'user': UserSerializer(user).data,
                'message': 'Registration successful. Check your email to confirm your account.',
            },
            status=status.HTTP_201_CREATED,
        )


class ConfirmEmailView(APIView):
    """Activate a newly registered user using the emailed confirmation link."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise Http404('Invalid email confirmation link.')

        if user.is_active or not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'This email confirmation link is invalid or has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response(
            {'message': 'Email confirmed successfully. You can now log in.'},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """Authenticate a user using email and password, returning an API token."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        firebase_token = create_firebase_custom_token(str(user.id), {'email': user.email})
        return Response(
            {
                'user': UserSerializer(user).data,
                'token': token.key,
                'firebase_token': firebase_token,
                'message': 'Login successful.',
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """Send a password reset link without revealing whether an address exists."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request, *args, **kwargs):
        email = request.data.get('email', '').strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = settings.PASSWORD_RESET_URL.format(uid=uid, token=token)
            send_mail(
                subject='Reset your Porchlight password',
                message=f'Reset your Porchlight password by visiting:\n\n{reset_url}\n\nThis link can only be used once.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        return Response({'message': 'If an account exists for that email, a password reset link has been sent.'})


class PasswordResetConfirmView(APIView):
    """Set a new password using a one-time reset token."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request, uidb64, token, *args, **kwargs):
        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid password reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        password = request.data.get('password', '')
        if len(password) < 6:
            return Response({'password': ['Password must be at least 6 characters.']}, status=status.HTTP_400_BAD_REQUEST)
        if password != request.data.get('password_confirm'):
            return Response({'password_confirm': ['Passwords do not match.']}, status=status.HTTP_400_BAD_REQUEST)
        if not default_token_generator.check_token(user, token):
            return Response({'error': 'This password reset link is invalid or has already been used.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()
        return Response({'message': 'Password reset successfully. You can now log in.'})


class MagicLoginRequestView(APIView):
    """Send a one-time passwordless login link."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def post(self, request, *args, **kwargs):
        email = request.data.get('email', '').strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            login_url = settings.MAGIC_LOGIN_URL.format(uid=uid, token=token)
            send_mail(
                subject='Your Porchlight magic login link',
                message=f'Log in to Porchlight by visiting:\n\n{login_url}\n\nThis link can only be used once.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        return Response({'message': 'If an account exists for that email, a magic login link has been sent.'})


class MagicLoginConfirmView(APIView):
    """Exchange a one-time magic login token for a DRF API token."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'auth'

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid magic login link.'}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active or not default_token_generator.check_token(user, token):
            return Response({'error': 'This magic login link is invalid or has already been used.'}, status=status.HTTP_400_BAD_REQUEST)
        Token.objects.filter(user=user).delete()
        api_token = Token.objects.create(user=user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        firebase_token = create_firebase_custom_token(str(user.id), {'email': user.email})
        return Response({'token': api_token.key, 'user': UserSerializer(user).data, 'firebase_token': firebase_token, 'message': 'Login successful.'})


class LogoutView(APIView):
    """Log out authenticated user by removing their authentication token."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        Token.objects.filter(user=request.user).delete()
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class MeView(generics.RetrieveUpdateAPIView):
    """Retrieve or update current authenticated user's details."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class FirebaseCustomTokenView(APIView):
    """Mint a Firebase Custom Auth Token for authenticated users or guest tokens."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'provider'

    def post(self, request, *args, **kwargs):
        if request.user and request.user.is_authenticated:
            uid = str(request.user.id)
            claims = {'email': request.user.email}
        else:
            guest_token = _request_guest_token(request)
            if not guest_token:
                return Response(
                    {'error': 'Authentication or guest_token is required.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not _valid_guest_token(guest_token):
                return Response(
                    {'error': 'The guest token is invalid or expired.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            uid = f"guest_{guest_token}"
            claims = {'guest': True, 'guest_token': guest_token}

        firebase_token = create_firebase_custom_token(uid, claims)
        if not firebase_token:
            return Response(
                {'error': 'Could not generate Firebase token.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'firebase_token': firebase_token, 'uid': uid}, status=status.HTTP_200_OK)

class FCMDeviceRegisterView(APIView):
    """Register or update an FCM device token for push notifications."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'provider'

    def post(self, request, *args, **kwargs):
        serializer = FCMDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration_token = serializer.validated_data['registration_token']
        device_id = serializer.validated_data.get('device_id', '')
        device_type = serializer.validated_data.get('device_type', 'android')
        user, guest_token = _request_actor(request)
        if not user and not guest_token:
            return Response({'detail': 'Authentication or a valid guest token is required.'}, status=status.HTTP_401_UNAUTHORIZED)

        device = FCMDeviceToken.objects.filter(registration_token=registration_token).first()
        if device and (device.user_id != getattr(user, 'id', None) or device.guest_token != guest_token):
            return Response({'detail': 'This device token belongs to another actor.'}, status=status.HTTP_403_FORBIDDEN)
        if device:
            device.user = user
            device.guest_token = guest_token
            device.device_id = device_id
            device.device_type = device_type
            device.is_active = True
            device.save(update_fields=['user', 'guest_token', 'device_id', 'device_type', 'is_active', 'updated_at'])
            created = False
        else:
            device = FCMDeviceToken.objects.create(
                registration_token=registration_token,
                user=user,
                guest_token=guest_token,
                device_id=device_id,
                device_type=device_type,
                is_active=True,
            )
            created = True

        return Response(
            {
                'message': 'FCM device token registered successfully.',
                'device': FCMDeviceTokenSerializer(device).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class FCMDeviceUnregisterView(APIView):
    """Unregister/deactivate an FCM device token."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'provider'

    def post(self, request, *args, **kwargs):
        serializer = FCMDeviceTokenUnregisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration_token = serializer.validated_data['registration_token']
        user, guest_token = _request_actor(request)
        if not user and not guest_token:
            return Response({'detail': 'Authentication or a valid guest token is required.'}, status=status.HTTP_401_UNAUTHORIZED)
        owner_filter = {'user': user} if user else {'guest_token': guest_token}
        updated = FCMDeviceToken.objects.filter(registration_token=registration_token, **owner_filter).update(is_active=False)

        if updated == 0:
            return Response({'message': 'Device token not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'message': 'Device token deactivated successfully.'}, status=status.HTTP_200_OK)


class WebPushRegisterView(APIView):
    """Register a browser Push API subscription for an authenticated user or guest."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'provider'

    def post(self, request, *args, **kwargs):
        serializer = WebPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user and request.user.is_authenticated else None
        guest_token = None if user else _request_guest_token(request)
        if not user and not _valid_guest_token(guest_token):
            return Response({'detail': 'Authentication or a valid guest token is required.'}, status=status.HTTP_401_UNAUTHORIZED)
        existing = WebPushSubscription.objects.filter(endpoint=serializer.validated_data['endpoint']).first()
        if existing and (existing.user_id != getattr(user, 'id', None) or existing.guest_token != guest_token):
            return Response({'detail': 'This subscription belongs to another actor.'}, status=status.HTTP_403_FORBIDDEN)
        if not user and not guest_token:
            return Response({'detail': 'Authentication or a guest token is required.'}, status=status.HTTP_401_UNAUTHORIZED)
        subscription, created = WebPushSubscription.objects.update_or_create(
            endpoint=serializer.validated_data['endpoint'],
            defaults={**serializer.validated_data, 'user': user, 'guest_token': guest_token, 'is_active': True},
        )
        return Response({'message': 'Web Push subscription registered.', 'id': str(subscription.id)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WebPushUnregisterView(APIView):
    """Deactivate a browser Push API subscription."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'provider'

    def post(self, request, *args, **kwargs):
        endpoint = request.data.get('endpoint')
        if not endpoint:
            return Response({'detail': 'An endpoint is required.'}, status=status.HTTP_400_BAD_REQUEST)
        user, guest_token = _request_actor(request)
        if not user and not guest_token:
            return Response({'detail': 'Authentication or a valid guest token is required.'}, status=status.HTTP_401_UNAUTHORIZED)
        owner_filter = {'user': user} if user else {'guest_token': guest_token}
        updated = WebPushSubscription.objects.filter(endpoint=endpoint, **owner_filter).update(is_active=False)
        return Response({'message': 'Web Push subscription removed.', 'updated': bool(updated)})
