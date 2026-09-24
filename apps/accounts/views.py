"""API Views for accounts registration, login, logout, and profile management."""
from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.firebase import create_firebase_custom_token
from .models import FCMDeviceToken
from .serializers import (
    FCMDeviceTokenSerializer,
    FCMDeviceTokenUnregisterSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
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
        token, _ = Token.objects.get_or_create(user=user)
        firebase_token = create_firebase_custom_token(str(user.id), {'email': user.email})
        return Response(
            {
                'user': UserSerializer(user).data,
                'token': token.key,
                'firebase_token': firebase_token,
                'message': 'Registration successful.',
            },
            status=status.HTTP_201_CREATED,
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
