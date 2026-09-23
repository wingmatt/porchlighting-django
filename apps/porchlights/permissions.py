"""Permissions for Porchlight access, memberships, and guest sessions."""
from rest_framework import permissions
from .models import GuestSession, Invitation, Porchlight, PorchlightMember, PorchlightRole


def get_guest_session_from_request(request, porchlight=None):
    """Extract and validate GuestSession from request headers or query parameters."""
    guest_token = (
        request.headers.get('X-Guest-Token')
        or request.query_params.get('guest_token')
        or request.data.get('guest_token') if isinstance(request.data, dict) else None
    )
    if not guest_token:
        # Also check if direct invitation code is provided
        invitation_code = (
            request.headers.get('X-Invitation-Code')
            or request.query_params.get('invitation_code')
            or request.data.get('invitation_code') if isinstance(request.data, dict) else None
        )
        if invitation_code:
            try:
                invitation = Invitation.objects.select_related('porchlight').get(code=invitation_code)
                if invitation.is_valid() and invitation.is_guest:
                    if porchlight and invitation.porchlight_id != porchlight.id:
                        return None
                    return invitation
            except Invitation.DoesNotExist:
                return None
        return None

    try:
        session = GuestSession.objects.select_related('invitation__porchlight').get(guest_token=guest_token)
        if session.is_valid():
            if porchlight and session.invitation.porchlight_id != porchlight.id:
                return None
            return session
    except GuestSession.DoesNotExist:
        return None
    return None


class IsPorchlightOwner(permissions.BasePermission):
    """Permission allowing access only to the Porchlight owner."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if isinstance(obj, Porchlight):
            return obj.owner_id == request.user.id
        if hasattr(obj, 'porchlight'):
            return obj.porchlight.owner_id == request.user.id
        return False


class IsPorchlightOwnerOrAdmin(permissions.BasePermission):
    """Permission allowing access to owner or ADMIN members."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        porchlight = obj if isinstance(obj, Porchlight) else getattr(obj, 'porchlight', None)
        if not porchlight:
            return False

        if porchlight.owner_id == request.user.id:
            return True

        return PorchlightMember.objects.filter(
            porchlight=porchlight,
            user=request.user,
            role__in=[PorchlightRole.ADMIN, PorchlightRole.OWNER],
        ).exists()


class HasPorchlightAccess(permissions.BasePermission):
    """
    Permission allowing access to:
    1. Authenticated Owner
    2. Authenticated Members/Admins
    3. Guests with valid guest token / invitation code
    """

    def has_permission(self, request, view):
        # Allow checking at object level
        return True

    def has_object_permission(self, request, view, obj):
        porchlight = obj if isinstance(obj, Porchlight) else getattr(obj, 'porchlight', None)
        if not porchlight:
            return False

        # 1. Authenticated User Check
        if request.user and request.user.is_authenticated:
            if porchlight.owner_id == request.user.id:
                return True
            if PorchlightMember.objects.filter(porchlight=porchlight, user=request.user).exists():
                return True

        # 2. Guest Token / Invitation Check
        guest_context = get_guest_session_from_request(request, porchlight)
        if guest_context:
            # Guests have read and safe state update access
            if request.method in permissions.SAFE_METHODS or request.method in ['POST', 'PATCH', 'PUT']:
                return True

        return False
