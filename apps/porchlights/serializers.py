"""Serializers for Porchlights, Members, Invitations, Permissions, RSVPs, and Guest Access."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import (
    GuestSession,
    Invitation,
    Permission,
    Porchlight,
    PorchlightMember,
    PorchlightRole,
    Rsvp,
)

User = get_user_model()


class PorchlightMemberSerializer(serializers.ModelSerializer):
    """Serializer for porchlight membership records."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = PorchlightMember
        fields = ['id', 'user', 'user_email', 'user_name', 'role', 'role_display', 'created_at']
        read_only_fields = ['id', 'created_at']


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for permission grants matching Laravel Permission model."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    guest_name = serializers.CharField(read_only=True)
    beacon_id = serializers.UUIDField(source='porchlight.id', read_only=True)

    class Meta:
        model = Permission
        fields = [
            'id',
            'porchlight',
            'beacon_id',
            'user',
            'user_email',
            'guest_id',
            'guest_name',
            'role',
            'is_close',
            'from_invitation',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RsvpSerializer(serializers.ModelSerializer):
    """Serializer for binary RSVP responses."""

    user_email = serializers.EmailField(source='user.email', read_only=True)
    beacon_id = serializers.UUIDField(source='porchlight.id', read_only=True)

    class Meta:
        model = Rsvp
        fields = [
            'id',
            'porchlight',
            'beacon_id',
            'user',
            'user_email',
            'guest_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PorchlightSerializer(serializers.ModelSerializer):
    """Serializer for Porchlight/Beacon list and general view."""

    brightness = serializers.IntegerField(default=100, min_value=0, max_value=100)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    user_role = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)
    coordinates = serializers.SerializerMethodField()
    sqid = serializers.CharField(read_only=True)
    rsvp_count = serializers.IntegerField(source='rsvps.count', read_only=True)
    has_rsvp = serializers.SerializerMethodField()
    rsvp_id = serializers.SerializerMethodField()
    has_close_permission = serializers.SerializerMethodField()

    class Meta:
        model = Porchlight
        fields = [
            'id',
            'sqid',
            'name',
            'type',
            'active_duration',
            'active_until',
            'is_active',
            'location',
            'coordinates',
            'description',
            'owner',
            'owner_email',
            'is_on',
            'brightness',
            'color',
            'status_message',
            'user_role',
            'is_owner',
            'created_at',
            'updated_at',
            'rsvp_count',
            'has_rsvp',
            'rsvp_id',
            'has_close_permission',
        ]
        read_only_fields = ['id', 'owner', 'is_active', 'coordinates', 'created_at', 'updated_at']

    def _current_rsvp(self, obj):
        request = self.context.get('request')
        if not request:
            return None
        if request.user and request.user.is_authenticated:
            return obj.rsvps.filter(user=request.user).first()
        guest_token = getattr(request, 'guest_token', None) or request.headers.get('X-Guest-Token')
        return obj.rsvps.filter(guest_id=guest_token).first() if guest_token else None

    def get_has_rsvp(self, obj) -> bool:
        return self._current_rsvp(obj) is not None

    def get_rsvp_id(self, obj):
        rsvp = self._current_rsvp(obj)
        return rsvp.id if rsvp else None

    def get_has_close_permission(self, obj) -> bool:
        return obj.permission_grants.filter(is_close=True).exists()

    def get_coordinates(self, obj) -> dict | None:
        return obj.coordinates

    def get_user_role(self, obj) -> str:
        request = self.context.get('request')
        if not request:
            return 'GUEST'
        if request.user and request.user.is_authenticated:
            if obj.owner_id == request.user.id:
                return 'OWNER'
            member = PorchlightMember.objects.filter(porchlight=obj, user=request.user).first()
            if member:
                return member.role
            perm = Permission.objects.filter(porchlight=obj, user=request.user).first()
            if perm:
                return perm.role.upper()
        # Check guest token
        guest_token = (
            getattr(request, 'guest_token', None)
            or request.headers.get('X-Guest-Token')
            or request.query_params.get('guest_token')
        )
        if guest_token:
            session = GuestSession.objects.filter(guest_token=guest_token, invitation__porchlight=obj).first()
            if session and session.is_valid():
                return session.invitation.role
            perm = Permission.objects.filter(porchlight=obj, guest_id=guest_token).first()
            if perm:
                return perm.role.upper()
        return 'GUEST'

    def get_is_owner(self, obj) -> bool:
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            return obj.owner_id == request.user.id
        return False

    def create(self, validated_data):
        # Set owner automatically from request
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['owner'] = request.user
        return super().create(validated_data)


# BeaconSerializer alias for Laravel compatibility
BeaconSerializer = PorchlightSerializer


class PorchlightDetailSerializer(PorchlightSerializer):
    """Detailed Porchlight serializer with members, permissions, and RSVPs."""

    members = PorchlightMemberSerializer(source='memberships', many=True, read_only=True)
    permissions = PermissionSerializer(source='permission_grants', many=True, read_only=True)
    rsvps = RsvpSerializer(many=True, read_only=True)

    class Meta(PorchlightSerializer.Meta):
        fields = PorchlightSerializer.Meta.fields + ['members', 'permissions', 'rsvps']


class PorchlightControlSerializer(serializers.ModelSerializer):
    """Serializer for toggling or updating Porchlight state."""

    brightness = serializers.IntegerField(min_value=0, max_value=100, required=False)

    class Meta:
        model = Porchlight
        fields = ['is_on', 'brightness', 'color', 'status_message', 'active_until', 'active_duration', 'location']


class InvitationSerializer(serializers.ModelSerializer):
    """Serializer for Porchlight/Beacon Invitations with Sqids support."""

    porchlight_name = serializers.CharField(source='porchlight.name', read_only=True)
    beacon_id = serializers.UUIDField(source='porchlight.id', read_only=True)
    invited_by_email = serializers.EmailField(source='invited_by.email', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    accepted_users_count = serializers.IntegerField(read_only=True)
    accepted_guests_count = serializers.IntegerField(read_only=True)
    accepted_count = serializers.IntegerField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    sqid = serializers.CharField(read_only=True)
    role_granted = serializers.CharField(read_only=True)
    active_until = serializers.DateTimeField(source='expires_at', read_only=True)

    class Meta:
        model = Invitation
        fields = [
            'id',
            'numeric_id',
            'code',
            'sqid',
            'porchlight',
            'beacon_id',
            'porchlight_name',
            'invited_by',
            'invited_by_email',
            'user',
            'user_email',
            'invited_email',
            'guest_token',
            'role',
            'role_display',
            'role_granted',
            'is_guest',
            'max_uses',
            'uses_count',
            'expires_at',
            'active_until',
            'is_active',
            'is_valid',
            'is_expired',
            'accepted_users_count',
            'accepted_guests_count',
            'accepted_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'numeric_id', 'code', 'sqid', 'invited_by', 'uses_count', 'created_at', 'updated_at']


class InvitationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating an invitation."""

    sqid = serializers.CharField(read_only=True)
    beacon = serializers.PrimaryKeyRelatedField(
        queryset=Porchlight.objects.all(),
        source='porchlight',
        required=False,
    )
    role_granted = serializers.CharField(required=False, write_only=True)
    active_until = serializers.DateTimeField(source='expires_at', required=False)

    class Meta:
        model = Invitation
        fields = [
            'id',
            'code',
            'sqid',
            'porchlight',
            'beacon',
            'user',
            'invited_email',
            'guest_token',
            'role',
            'role_granted',
            'is_guest',
            'max_uses',
            'expires_at',
            'active_until',
            'created_at',
        ]
        read_only_fields = ['id', 'code', 'sqid', 'created_at']

    def validate_porchlight(self, value):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication required.')

        is_owner = value.owner_id == request.user.id
        is_admin = PorchlightMember.objects.filter(
            porchlight=value,
            user=request.user,
            role=PorchlightRole.ADMIN,
        ).exists()
        has_share_permission = Permission.objects.filter(
            porchlight=value,
            user=request.user,
            role__in=['owner', 'edit', 'share', 'admin'],
        ).exists()

        if not (is_owner or is_admin or has_share_permission):
            raise serializers.ValidationError('You do not have permission to invite users to this Porchlight.')

        return value

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['invited_by'] = request.user
        role_granted = validated_data.pop('role_granted', None)
        instance = super().create(validated_data)
        if role_granted:
            instance.role_granted = role_granted
            instance.save(update_fields=['role'])
        return instance


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting an invitation by an authenticated user."""

    code = serializers.CharField(max_length=64)

    def validate_code(self, value):
        invitation = Invitation.get_by_sqid(value)
        if not invitation:
            raise serializers.ValidationError('Invalid invitation code.')

        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or has already been used.')

        return value


class GuestAccessSerializer(serializers.Serializer):
    """Serializer for initializing a guest session using an invitation code."""

    invitation_code = serializers.CharField(max_length=64)
    guest_name = serializers.CharField(max_length=100, required=False, default='')

    def validate_invitation_code(self, value):
        invitation = Invitation.get_by_sqid(value)
        if not invitation:
            raise serializers.ValidationError('Invalid invitation code.')

        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or has already reached maximum uses.')

        return value
