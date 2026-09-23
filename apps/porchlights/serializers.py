"""Serializers for Porchlights, Members, Invitations, and Guest Access."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import GuestSession, Invitation, Porchlight, PorchlightMember, PorchlightRole

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


class PorchlightSerializer(serializers.ModelSerializer):
    """Serializer for Porchlight list and general view."""

    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    user_role = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Porchlight
        fields = [
            'id',
            'name',
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
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']

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
        # Check guest token
        guest_token = request.headers.get('X-Guest-Token') or request.query_params.get('guest_token')
        if guest_token:
            session = GuestSession.objects.filter(guest_token=guest_token, invitation__porchlight=obj).first()
            if session and session.is_valid():
                return session.invitation.role
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


class PorchlightDetailSerializer(PorchlightSerializer):
    """Detailed Porchlight serializer with members and invitations for managers."""

    members = PorchlightMemberSerializer(source='memberships', many=True, read_only=True)

    class Meta(PorchlightSerializer.Meta):
        fields = PorchlightSerializer.Meta.fields + ['members']


class PorchlightControlSerializer(serializers.ModelSerializer):
    """Serializer for toggling or updating Porchlight state."""

    class Meta:
        model = Porchlight
        fields = ['is_on', 'brightness', 'color', 'status_message']


class InvitationSerializer(serializers.ModelSerializer):
    """Serializer for Porchlight Invitations."""

    porchlight_name = serializers.CharField(source='porchlight.name', read_only=True)
    invited_by_email = serializers.EmailField(source='invited_by.email', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = Invitation
        fields = [
            'id',
            'code',
            'porchlight',
            'porchlight_name',
            'invited_by',
            'invited_by_email',
            'invited_email',
            'role',
            'role_display',
            'is_guest',
            'max_uses',
            'uses_count',
            'expires_at',
            'is_active',
            'is_valid',
            'created_at',
        ]
        read_only_fields = ['id', 'code', 'invited_by', 'uses_count', 'created_at']


class InvitationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating an invitation."""

    class Meta:
        model = Invitation
        fields = ['id', 'code', 'porchlight', 'invited_email', 'role', 'is_guest', 'max_uses', 'expires_at', 'created_at']
        read_only_fields = ['id', 'code', 'created_at']

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

        if not (is_owner or is_admin):
            raise serializers.ValidationError('You do not have permission to invite users to this Porchlight.')

        return value

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['invited_by'] = request.user
        return super().create(validated_data)


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting an invitation by an authenticated user."""

    code = serializers.CharField(max_length=64)

    def validate_code(self, value):
        try:
            invitation = Invitation.objects.select_related('porchlight', 'invited_by').get(code=value)
        except Invitation.DoesNotExist:
            raise serializers.ValidationError('Invalid invitation code.')

        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or has already been used.')

        return value


class GuestAccessSerializer(serializers.Serializer):
    """Serializer for initializing a guest session using an invitation code."""

    invitation_code = serializers.CharField(max_length=64)
    guest_name = serializers.CharField(max_length=100, required=False, default='Guest')

    def validate_invitation_code(self, value):
        try:
            invitation = Invitation.objects.select_related('porchlight').get(code=value)
        except Invitation.DoesNotExist:
            raise serializers.ValidationError('Invalid invitation code.')

        if not invitation.is_valid():
            raise serializers.ValidationError('This invitation has expired or has already reached maximum uses.')

        if not invitation.is_guest:
            raise serializers.ValidationError('This invitation is reserved for registered users. Please log in.')

        return value
