"""Permissions for Porchlight access, memberships, permissions, and guest sessions."""
from django.db.models import Q
from rest_framework import permissions
from .models import GuestSession, Invitation, Permission, Porchlight, PorchlightMember, PorchlightRole


def get_guest_session_from_request(request, porchlight=None):
    """Extract and validate a guest session from the dedicated request header."""
    guest_token = getattr(request, 'guest_token', None) or request.headers.get('X-Guest-Token')
    if not guest_token:
        return None

    try:
        session = GuestSession.objects.select_related('invitation__porchlight').get(guest_token=guest_token)
        if session.is_valid():
            if porchlight and session.invitation.porchlight_id != porchlight.id:
                return None
            return session
    except GuestSession.DoesNotExist:
        pass

    # Check permission table for guest_id
    if porchlight:
        perm = Permission.objects.filter(porchlight=porchlight, guest_id=guest_token).first()
        if perm:
            return perm

    return None


def can_view_porchlight(request, porchlight):
    """Return whether the current actor can see a bright or dim porchlight."""
    user = request.user if request.user and request.user.is_authenticated else None
    guest_token = (
        getattr(request, 'guest_token', None)
        or request.headers.get('X-Guest-Token')
    )

    if porchlight.brightness > 0:
        if user and (
            porchlight.owner_id == user.id
            or PorchlightMember.objects.filter(porchlight=porchlight, user=user).exists()
            or Permission.objects.filter(porchlight=porchlight, user=user).exists()
        ):
            return True
        return bool(guest_token and Permission.objects.filter(porchlight=porchlight, guest_id=guest_token).exists())

    if user:
        if porchlight.owner_id == user.id:
            return True
        if PorchlightMember.objects.filter(
            porchlight=porchlight,
            user=user,
            role__in=[PorchlightRole.OWNER, PorchlightRole.ADMIN, PorchlightRole.MEMBER],
        ).exists():
            return True
        if Permission.objects.filter(porchlight=porchlight, user=user).filter(
            Q(is_close=True)
            | Q(from_invitation__isnull=False)
            | Q(role__in=['owner', 'edit', 'share', 'admin'])
        ).exists():
            return True

    return bool(
        guest_token
        and Permission.objects.filter(porchlight=porchlight, guest_id=guest_token).filter(
            Q(is_close=True)
            | Q(from_invitation__isnull=False)
            | Q(role__in=['owner', 'edit', 'share', 'admin'])
        ).exists()
    )


def porchlight_visibility_filter(user=None, guest_token=None):
    """Build the queryset filter matching the dim/bright visibility rules."""
    if not user or not user.is_authenticated:
        user = None
    bright_access = (
        Q(owner=user) | Q(memberships__user=user) | Q(permission_grants__user=user)
    ) if user else Q(pk__in=[])
    dim_access = (
        Q(owner=user)
        | Q(memberships__user=user, memberships__role__in=[PorchlightRole.OWNER, PorchlightRole.ADMIN, PorchlightRole.MEMBER])
        | Q(
            permission_grants__user=user,
            permission_grants__is_close=True,
        )
        | Q(
            permission_grants__user=user,
            permission_grants__from_invitation__isnull=False,
        )
        | Q(
            permission_grants__user=user,
            permission_grants__role__in=['owner', 'edit', 'share', 'admin'],
        )
    ) if user else Q(pk__in=[])

    if guest_token:
        bright_access |= Q(permission_grants__guest_id=guest_token)
        dim_access |= Q(
            permission_grants__guest_id=guest_token,
            permission_grants__is_close=True,
        ) | Q(
            permission_grants__guest_id=guest_token,
            permission_grants__from_invitation__isnull=False,
        ) | Q(
            permission_grants__guest_id=guest_token,
            permission_grants__role__in=['owner', 'edit', 'share', 'admin'],
        )

    return (Q(brightness__gt=0) & bright_access) | (Q(brightness=0) & dim_access)


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

        if PorchlightMember.objects.filter(
            porchlight=porchlight,
            user=request.user,
            role__in=[PorchlightRole.ADMIN, PorchlightRole.OWNER],
        ).exists():
            return True

        return Permission.objects.filter(
            porchlight=porchlight,
            user=request.user,
            role__in=['owner', 'edit', 'share', 'admin'],
        ).exists()


class HasPorchlightAccess(permissions.BasePermission):
    """
    Permission allowing access to:
    1. Authenticated Owner
    2. Authenticated Members/Admins/Permission holders
    3. Guests with valid guest token / invitation code / permission
    """

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        porchlight = obj if isinstance(obj, Porchlight) else getattr(obj, 'porchlight', None)
        if not porchlight:
            return False
        return can_view_porchlight(request, porchlight)
