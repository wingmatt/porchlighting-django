"""Serializers for accounts authentication and user profiles."""
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from .models import FCMDeviceToken, WebPushSubscription

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User profile details."""

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration with email and password."""

    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'password', 'password_confirm']
        read_only_fields = ['id']

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            is_active=False,
        )
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user authentication using email and password."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                email=email,
                password=password
            )
            if not user:
                raise serializers.ValidationError('Invalid email or password.')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')
        else:
            raise serializers.ValidationError('Must include both "email" and "password".')

        attrs['user'] = user
        return attrs


class FCMDeviceTokenSerializer(serializers.ModelSerializer):
    """Serializer for registering or updating FCM device tokens."""

    class Meta:
        model = FCMDeviceToken
        fields = ['id', 'registration_token', 'device_id', 'device_type', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'registration_token': {
                'validators': [],
                'write_only': True,
            },  # Allow ownership checks before update_or_create
        }


class FCMDeviceTokenUnregisterSerializer(serializers.Serializer):
    """Serializer for unregistering an FCM device token."""

    registration_token = serializers.CharField(max_length=255)


class WebPushSubscriptionSerializer(serializers.ModelSerializer):
    """Validate the browser Push API subscription payload."""

    class Meta:
        model = WebPushSubscription
        fields = ['endpoint', 'p256dh', 'auth']
        extra_kwargs = {
            'endpoint': {'validators': []},  # Allow update_or_create on an existing browser subscription
        }

    def validate_endpoint(self, value):
        if not value.startswith('https://'):
            raise serializers.ValidationError('A secure HTTPS push endpoint is required.')
        if len(value) > 2048:
            raise serializers.ValidationError('The push endpoint is too long.')
        return value
