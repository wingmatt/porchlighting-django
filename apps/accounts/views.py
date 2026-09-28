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


class RegisterView(generics.CreateAPIView):
    """Register a new user with email and password."""

    permission_classes = [permissions.AllowAny]
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

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
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

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid magic login link.'}, status=status.HTTP_400_BAD_REQUEST)
        if not user.is_active or not default_token_generator.check_token(user, token):
            return Response({'error': 'This magic login link is invalid or has already been used.'}, status=status.HTTP_400_BAD_REQUEST)
        api_token, _ = Token.objects.get_or_create(user=user)
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

    def post(self, request, *args, **kwargs):
        if request.user and request.user.is_authenticated:
            uid = str(request.user.id)
            claims = {'email': request.user.email}
        else:
            guest_token = (
                request.data.get('guest_token')
                or request.query_params.get('guest_token')
                or request.headers.get('X-Guest-Token')
            )
            if not guest_token:
                return Response(
                    {'error': 'Authentication or guest_token is required.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            guest_session = GuestSession.objects.filter(guest_token=guest_token).first()
            has_guest_access = guest_session and guest_session.is_valid()
            has_guest_access = has_guest_access or Permission.objects.filter(guest_id=guest_token).exists()
            if not has_guest_access:
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

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class FCMDeviceRegisterView(APIView):
    """Register or update an FCM device token for push notifications."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = FCMDeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration_token = serializer.validated_data['registration_token']
        device_id = serializer.validated_data.get('device_id', '')
        device_type = serializer.validated_data.get('device_type', 'android')
        guest_token = serializer.validated_data.get('guest_token')

        user = request.user if request.user and request.user.is_authenticated else None
        if not user and not guest_token:
            guest_token = request.headers.get('X-Guest-Token') or request.query_params.get('guest_token')

        device, created = FCMDeviceToken.objects.update_or_create(
            registration_token=registration_token,
            defaults={
                'user': user,
                'guest_token': guest_token,
                'device_id': device_id,
                'device_type': device_type,
                'is_active': True,
            },
        )

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

    def post(self, request, *args, **kwargs):
        serializer = FCMDeviceTokenUnregisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        registration_token = serializer.validated_data['registration_token']
        updated = FCMDeviceToken.objects.filter(registration_token=registration_token).update(is_active=False)

        if updated == 0:
            return Response({'message': 'Device token not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'message': 'Device token deactivated successfully.'}, status=status.HTTP_200_OK)


class WebPushRegisterView(APIView):
    """Register a browser Push API subscription for an authenticated user or guest."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = WebPushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user and request.user.is_authenticated else None
        guest_token = None if user else (request.headers.get('X-Guest-Token') or request.data.get('guest_token'))
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

    def post(self, request, *args, **kwargs):
        endpoint = request.data.get('endpoint')
        if not endpoint:
            return Response({'detail': 'An endpoint is required.'}, status=status.HTTP_400_BAD_REQUEST)
        updated = WebPushSubscription.objects.filter(endpoint=endpoint).update(is_active=False)
        return Response({'message': 'Web Push subscription removed.', 'updated': bool(updated)})
