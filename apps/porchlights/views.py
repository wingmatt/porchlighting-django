"""API views for Porchlights, Beacons, Invitations, Permissions, RSVPs, Memberships, and Guest Access."""

from django.conf import settings
from django.http import Http404
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from geocodio import Geocodio
from geocodio.exceptions import GeocodioError
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.firebase import create_firebase_custom_token
from apps.core.notifications import notify_porchlight_turned_on
from .models import (
    GuestSession,
    Invitation,
    Permission,
    Porchlight,
    PorchlightMember,
    PorchlightRole,
    Rsvp,
    generate_invitation_code,
)
from .permissions import (
    HasPorchlightAccess,
    IsPorchlightOwner,
    IsPorchlightOwnerOrAdmin,
    get_guest_session_from_request,
)
from .serializers import (
    AcceptInvitationSerializer,
    GuestAccessSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    PermissionSerializer,
    PorchlightControlSerializer,
    PorchlightDetailSerializer,
    PorchlightMemberSerializer,
    PorchlightSerializer,
    RsvpSerializer,
)


def get_porchlight_by_sqid_or_404(identifier):
    """Resolve a URL Sqid to a porchlight or raise a not-found response."""
    porchlight = Porchlight.get_by_sqid(identifier)
    if not porchlight:
        raise Http404
    return porchlight


def get_porchlight_by_identifier(identifier):
    """Resolve a Sqid or internal UUID used in a request body or query string."""
    porchlight = Porchlight.get_by_sqid(identifier)
    if porchlight:
        return porchlight
    try:
        return Porchlight.objects.filter(pk=identifier).first()
    except (TypeError, ValueError):
        return None


class PorchlightListCreateView(generics.ListCreateAPIView):
    """List porchlights/beacons accessible to user or create a new porchlight/beacon."""

    serializer_class = PorchlightSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Porchlight.objects.filter(
            Q(owner=user) | Q(memberships__user=user) | Q(permission_grants__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class NeighborhoodListView(generics.ListAPIView):
    """List every Porchlight accessible to the current user or guest."""

    serializer_class = PorchlightSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        guest_token = getattr(self.request, 'guest_token', None) or self.request.headers.get('X-Guest-Token')
        access_filter = Q()
        if user:
            access_filter |= (
                Q(owner=user)
                | Q(memberships__user=user)
                | Q(permission_grants__user=user)
            )
        if guest_token:
            access_filter |= Q(permission_grants__guest_id=guest_token)
        return Porchlight.objects.filter(access_filter).distinct() if access_filter else Porchlight.objects.none()


class GeocodeAddressView(APIView):
    """Resolve a street address through Geocodio without exposing its API key."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        address = str(request.data.get('address', '')).strip()
        if not address:
            return Response({'detail': 'An address is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not settings.GEOCODIO_API_KEY:
            return Response(
                {'detail': 'Address lookup is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            response = Geocodio(settings.GEOCODIO_API_KEY).geocode(address)
        except (GeocodioError, OSError, TimeoutError):
            return Response(
                {'detail': 'Unable to find coordinates for that address.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not response.results:
            return Response(
                {'detail': 'No coordinates were found for that address.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        location = response.results[0].location
        if location is None:
            return Response(
                {'detail': 'Geocodio returned an invalid coordinate.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({'latitude': float(location.lat), 'longitude': float(location.lng)})


# BeaconListCreateView alias for Laravel migration route compatibility
BeaconListCreateView = PorchlightListCreateView


class PorchlightDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a porchlight/beacon."""

    queryset = Porchlight.objects.all()
    permission_classes = [HasPorchlightAccess]

    def get_object(self):
        porchlight = get_porchlight_by_sqid_or_404(self.kwargs['pk'])
        self.check_object_permissions(self.request, porchlight)
        return porchlight

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return PorchlightDetailSerializer
        return PorchlightSerializer

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH']:
            return [IsPorchlightOwnerOrAdmin()]
        elif self.request.method == 'DELETE':
            return [IsPorchlightOwner()]
        return [HasPorchlightAccess()]


# BeaconDetailView alias
BeaconDetailView = PorchlightDetailView


class PorchlightControlView(APIView):
    """Toggle power, change brightness, color, location, duration, or status message."""

    permission_classes = [HasPorchlightAccess]

    def post(self, request, pk, *args, **kwargs):
        porchlight = get_porchlight_by_sqid_or_404(pk)
        self.check_object_permissions(request, porchlight)
        was_on = porchlight.is_on

        action = request.data.get('action')
        if action == 'toggle':
            porchlight.is_on = not porchlight.is_on
        elif action == 'turn_on':
            porchlight.is_on = True
        elif action == 'turn_off':
            porchlight.is_on = False

        serializer = PorchlightControlSerializer(porchlight, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        if not was_on and porchlight.is_on:
            actor_user = request.user if request.user and request.user.is_authenticated else None
            actor_guest = request.headers.get('X-Guest-Token') or getattr(request, 'guest_token', None)
            notify_porchlight_turned_on(porchlight, actor_user=actor_user, actor_guest_token=actor_guest)

        # Update last active timestamp if guest session
        guest_session = get_guest_session_from_request(request, porchlight)
        if isinstance(guest_session, GuestSession):
            guest_session.save(update_fields=['last_active_at'])

        return Response(
            {
                'message': f"Porchlight is now {'ON' if porchlight.is_on else 'OFF'}.",
                'porchlight': PorchlightSerializer(porchlight, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


# BeaconControlView alias
BeaconControlView = PorchlightControlView


class InvitationListCreateView(generics.ListCreateAPIView):
    """List or create invitations for porchlights/beacons."""

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InvitationCreateSerializer
        return InvitationSerializer

    def get_queryset(self):
        user = self.request.user
        porchlight_id = self.request.query_params.get('porchlight') or self.request.query_params.get('beacon')
        queryset = Invitation.objects.filter(
            Q(porchlight__owner=user)
            | Q(porchlight__memberships__user=user, porchlight__memberships__role=PorchlightRole.ADMIN)
            | Q(porchlight__permission_grants__user=user, porchlight__permission_grants__role__in=['owner', 'edit', 'share', 'admin'])
        ).filter(
            Q(
                Q(is_active=True)
                & (Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                & (Q(max_uses=0) | Q(uses_count__lt=models.F('max_uses'))),
            )
            | Q(expires_at__lt=timezone.now())
        ).annotate(
            accepted_users_count=models.Count(
                'permissions_granted__user',
                filter=Q(permissions_granted__user__isnull=False),
                distinct=True,
            ),
            accepted_guests_count=models.Count('guest_sessions', distinct=True),
        ).annotate(
            accepted_count=models.F('accepted_users_count') + models.F('accepted_guests_count'),
        ).distinct()

        if porchlight_id:
            queryset = queryset.filter(porchlight_id=porchlight_id)

        return queryset


class InvitationDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or revoke an invitation."""

    queryset = Invitation.objects.all()
    serializer_class = InvitationSerializer
    permission_classes = [IsPorchlightOwnerOrAdmin]


class ValidateInvitationView(APIView):
    """Validate an invitation code or Sqid and return basic invitation info."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, code, *args, **kwargs):
        invitation = Invitation.get_by_sqid(code)
        if not invitation:
            return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)

        has_permission = bool(
            request.user.is_authenticated
            and (
                invitation.porchlight.owner_id == request.user.id
                or Permission.objects.filter(porchlight=invitation.porchlight, user=request.user).exists()
            )
        )
        can_manage = bool(
            request.user.is_authenticated
            and (
                invitation.porchlight.owner_id == request.user.id
                or Permission.objects.filter(
                    porchlight=invitation.porchlight,
                    user=request.user,
                    role__in=['owner', 'edit'],
                ).exists()
            )
        )
        can_share = bool(
            request.user.is_authenticated
            and (
                invitation.porchlight.owner_id == request.user.id
                or Permission.objects.filter(
                    porchlight=invitation.porchlight,
                    user=request.user,
                    role__in=['owner', 'edit', 'share', 'admin'],
                ).exists()
            )
        )
        return Response(
            {
                'id': str(invitation.id),
                'code': invitation.code,
                'sqid': invitation.sqid,
                'porchlight_id': str(invitation.porchlight_id),
                'beacon_id': str(invitation.porchlight_id),
                'porchlight_name': invitation.porchlight.name,
                'invited_by': invitation.invited_by.full_name if invitation.invited_by else 'Owner',
                'role': invitation.role,
                'role_display': invitation.get_role_display(),
                'role_granted': invitation.role_granted,
                'is_guest': invitation.is_guest,
                'is_valid': invitation.is_valid(),
                'is_expired': invitation.is_expired,
                'is_exhausted': invitation.is_exhausted,
                'expires_at': invitation.expires_at,
                'active_until': invitation.active_until,
                'has_permission': has_permission,
                'can_manage': can_manage,
                'can_share': can_share,
                'porchlight': PorchlightSerializer(invitation.porchlight, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


def can_manage_invitation(request, invitation):
    """Return whether the request user may manage invitation participants."""
    return bool(
        request.user.is_authenticated
        and (
            invitation.porchlight.owner_id == request.user.id
            or Permission.objects.filter(
                porchlight=invitation.porchlight,
                user=request.user,
                role__in=['owner', 'edit'],
            ).exists()
        )
    )


def can_manage_porchlight_access(request, porchlight):
    """Return whether the request user may manage all access grants."""
    return bool(
        request.user.is_authenticated
        and (
            porchlight.owner_id == request.user.id
            or Permission.objects.filter(
                porchlight=porchlight,
                user=request.user,
                role__in=['owner', 'edit'],
            ).exists()
        )
    )


def porchlight_access_data(porchlight):
    """Serialize every user and guest that can access a porchlight."""
    entries = [{
        'id': str(porchlight.owner_id),
        'type': 'user',
        'email': porchlight.owner.email,
        'name': porchlight.owner.full_name,
        'role': 'owner',
        'source': 'owner',
        'is_close': False,
        'created_at': porchlight.created_at.isoformat(),
        'from_invitation': None,
        'editable': False,
    }]
    seen_users = {porchlight.owner_id}
    for member in porchlight.memberships.select_related('user').all():
        if member.user_id in seen_users:
            continue
        seen_users.add(member.user_id)
        entries.append({
            'id': str(member.id),
            'type': 'user',
            'email': member.user.email,
            'name': member.user.full_name,
            'role': {'OWNER': 'owner', 'ADMIN': 'share', 'MEMBER': 'edit', 'GUEST': 'view'}.get(member.role, 'view'),
            'source': 'membership',
            'is_close': False,
            'created_at': member.created_at.isoformat(),
            'from_invitation': None,
            'editable': True,
        })
    for permission in porchlight.permission_grants.select_related('user').all():
        if permission.user_id and permission.user_id in seen_users:
            continue
        if permission.user_id:
            seen_users.add(permission.user_id)
            entries.append({
                'id': str(permission.id),
                'type': 'user',
                'email': permission.user.email,
                'name': permission.user.full_name,
                'role': permission.role,
                'source': 'permission',
                'is_close': permission.is_close,
                'created_at': permission.created_at.isoformat(),
                'from_invitation': str(permission.from_invitation_id) if permission.from_invitation_id else None,
                'guest_name': None,
                'editable': True,
            })
        elif permission.guest_id:
            entries.append({
                'id': str(permission.id),
                'type': 'guest',
                'name': permission.guest_name or 'Guest',
                'role': permission.role,
                'source': 'permission',
                'is_close': permission.is_close,
                'created_at': permission.created_at.isoformat(),
                'from_invitation': str(permission.from_invitation_id) if permission.from_invitation_id else None,
                'guest_name': permission.guest_name,
                'editable': True,
            })
    return entries


class PorchlightAccessView(APIView):
    """List and update every user or guest with porchlight access."""

    permission_classes = [permissions.IsAuthenticated]

    def get_porchlight(self, pk):
        return get_porchlight_by_sqid_or_404(pk)

    def get(self, request, pk, *args, **kwargs):
        porchlight = self.get_porchlight(pk)
        if not can_manage_porchlight_access(request, porchlight):
            return Response({'detail': 'You do not have permission to manage this porchlight.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'access': porchlight_access_data(porchlight)})

    def patch(self, request, pk, access_id, *args, **kwargs):
        porchlight = self.get_porchlight(pk)
        if not can_manage_porchlight_access(request, porchlight):
            return Response({'detail': 'You do not have permission to manage this porchlight.'}, status=status.HTTP_403_FORBIDDEN)
        role = str(request.data.get('role', '')).lower()
        if role and role not in {'view', 'edit', 'share'}:
            return Response({'role': 'Choose view, edit, or share.'}, status=status.HTTP_400_BAD_REQUEST)
        permission = porchlight.permission_grants.filter(pk=access_id).first()
        if permission:
            update_fields = ['updated_at']
            if role:
                permission.role = role
                update_fields.append('role')
            if 'is_close' in request.data:
                is_close = request.data['is_close']
                if isinstance(is_close, str):
                    is_close = is_close.lower() in {'true', '1', 'yes', 'on'}
                if not isinstance(is_close, bool):
                    return Response({'is_close': 'Expected a boolean value.'}, status=status.HTTP_400_BAD_REQUEST)
                permission.is_close = is_close
                update_fields.append('is_close')
            permission.save(update_fields=update_fields)
            return Response(next(item for item in porchlight_access_data(porchlight) if item['id'] == str(permission.id)))
        member = porchlight.memberships.filter(pk=access_id).first()
        if member:
            if not role:
                return Response({'role': 'Choose view, edit, or share.'}, status=status.HTTP_400_BAD_REQUEST)
            member.role = {'view': PorchlightRole.GUEST, 'edit': PorchlightRole.MEMBER, 'share': PorchlightRole.ADMIN}[role]
            member.save(update_fields=['role'])
            return Response(next(item for item in porchlight_access_data(porchlight) if item['id'] == str(member.id)))
        return Response({'detail': 'Access entry not found.'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk, access_id, *args, **kwargs):
        porchlight = self.get_porchlight(pk)
        if not can_manage_porchlight_access(request, porchlight):
            return Response({'detail': 'You do not have permission to manage this porchlight.'}, status=status.HTTP_403_FORBIDDEN)
        permission = porchlight.permission_grants.filter(pk=access_id).first()
        if permission:
            permission.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        member = porchlight.memberships.filter(pk=access_id).first()
        if member:
            member.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'detail': 'Access entry not found.'}, status=status.HTTP_404_NOT_FOUND)


def invitation_participant_data(invitation):
    """Serialize accepted users and guests for invitation management."""
    participants = []
    permissions = invitation.permissions_granted.select_related('user').all()
    sessions = {session.guest_token: session for session in invitation.guest_sessions.all()}
    for permission in permissions:
        if permission.user_id:
            participants.append(
                {
                    'id': str(permission.id),
                    'type': 'user',
                    'email': permission.user.email,
                    'name': permission.user.full_name,
                    'role': permission.role,
                }
            )
        elif permission.guest_id:
            session = sessions.get(permission.guest_id)
            participants.append(
                {
                    'id': str(permission.id),
                    'type': 'guest',
                    'guest_token': permission.guest_id,
                    'name': permission.guest_name or (session.guest_name if session else 'Guest'),
                    'role': permission.role,
                }
            )
    return participants


class InvitationParticipantsView(APIView):
    """List or revoke participants accepted through an invitation."""

    permission_classes = [permissions.IsAuthenticated]

    def get_invitation(self, code):
        invitation = Invitation.get_by_sqid(code)
        if not invitation:
            raise Http404
        return invitation

    def get(self, request, code, *args, **kwargs):
        invitation = self.get_invitation(code)
        if not can_manage_invitation(request, invitation):
            return Response({'detail': 'You do not have permission to manage this invitation.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'participants': invitation_participant_data(invitation), 'code': invitation.code})

    def delete(self, request, code, *args, **kwargs):
        invitation = self.get_invitation(code)
        if not can_manage_invitation(request, invitation):
            return Response({'detail': 'You do not have permission to manage this invitation.'}, status=status.HTTP_403_FORBIDDEN)

        permission = invitation.permissions_granted.filter(pk=request.data.get('permission_id')).first()
        if not permission:
            return Response({'detail': 'Participant not found.'}, status=status.HTTP_404_NOT_FOUND)
        if permission.guest_id:
            GuestSession.objects.filter(invitation=invitation, guest_token=permission.guest_id).delete()
        permission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationRevokeAllView(APIView):
    """Revoke all invitation participants and rotate its invitation code."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, code, *args, **kwargs):
        invitation = Invitation.get_by_sqid(code)
        if not invitation:
            raise Http404
        if not can_manage_invitation(request, invitation):
            return Response({'detail': 'You do not have permission to manage this invitation.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            invitation.permissions_granted.all().delete()
            invitation.guest_sessions.all().delete()
            max_numeric_id = Invitation.objects.aggregate(max_id=models.Max('numeric_id'))['max_id'] or 0
            invitation.numeric_id = max_numeric_id + 1
            invitation.code = generate_invitation_code()
            invitation.uses_count = 0
            invitation.is_active = True
            invitation.save(update_fields=['numeric_id', 'code', 'uses_count', 'is_active', 'updated_at'])

        return Response({'code': invitation.code, 'sqid': invitation.sqid, 'participants': []})


class AcceptInvitationView(APIView):
    """Accept an invitation as an authenticated user to gain member access."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']
        with transaction.atomic():
            invitation = Invitation.get_by_sqid(code)
            if not invitation:
                return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if not invitation.is_valid():
                return Response(
                    {'error': 'This invitation has expired or has already been used.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if invitation.porchlight.owner_id == request.user.id:
                return Response(
                    {'error': 'You are already the owner of this Porchlight.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            member = None
            if invitation.role in PorchlightRole.values:
                member, _ = PorchlightMember.objects.update_or_create(
                    porchlight=invitation.porchlight,
                    user=request.user,
                    defaults={'role': invitation.role},
                )

            Permission.objects.update_or_create(
                porchlight=invitation.porchlight,
                user=request.user,
                defaults={
                    'role': invitation.role_granted,
                    'from_invitation': invitation,
                },
            )
            invitation.record_usage()

        return Response(
            {
                'message': f"Successfully joined {invitation.porchlight.name}.",
                'membership': PorchlightMemberSerializer(member).data if member else None,
                'porchlight': PorchlightSerializer(invitation.porchlight, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


class GuestAccessView(APIView):
    """Obtain guest access session and token using an invitation code or Sqid."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'guest'

    def post(self, request, *args, **kwargs):
        serializer = GuestAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invitation_code = serializer.validated_data['invitation_code']
        guest_token = request.headers.get('X-Guest-Token')
        invitation = Invitation.get_by_sqid(invitation_code)
        if not invitation:
            return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)

        session = GuestSession.objects.filter(guest_token=guest_token).first() if guest_token else None
        if guest_token and (not session or not session.is_valid()):
            return Response({'error': 'This guest session is no longer valid.'}, status=status.HTTP_400_BAD_REQUEST)

        guest_name = session.guest_name if session else serializer.validated_data.get('guest_name', '').strip()
        if not guest_name:
            return Response({'error': 'A name is required to join as a guest.'}, status=status.HTTP_400_BAD_REQUEST)

        if not session:
            session = GuestSession.objects.create(
                invitation=invitation,
                guest_name=guest_name,
            )
            guest_token = session.guest_token

        # Also record permission grant for guest
        Permission.objects.get_or_create(
            porchlight=invitation.porchlight,
            guest_id=guest_token,
            from_invitation=invitation,
            defaults={
                'guest_name': guest_name,
                'role': invitation.role_granted,
            },
        )

        invitation.record_usage()
        firebase_token = create_firebase_custom_token(
            f"guest_{session.guest_token}",
            {'guest': True, 'guest_token': session.guest_token, 'porchlight_id': str(invitation.porchlight_id)},
        )

        return Response(
            {
                'guest_token': guest_token,
                'guest_name': guest_name,
                'role': invitation.role,
                'role_granted': invitation.role_granted,
                'porchlight': PorchlightSerializer(invitation.porchlight).data,
                'beacon': PorchlightSerializer(invitation.porchlight).data,
                'firebase_token': firebase_token,
            },
            status=status.HTTP_200_OK,
        )


class PorchlightMemberListView(generics.ListCreateAPIView):
    """List or add members to a porchlight."""

    serializer_class = PorchlightMemberSerializer
    permission_classes = [IsPorchlightOwnerOrAdmin]

    def get_queryset(self):
        porchlight_pk = self.kwargs.get('porchlight_pk') or self.kwargs.get('pk')
        porchlight = Porchlight.get_by_sqid(porchlight_pk)
        return PorchlightMember.objects.filter(porchlight=porchlight) if porchlight else PorchlightMember.objects.none()

    def perform_create(self, serializer):
        porchlight_pk = self.kwargs.get('porchlight_pk') or self.kwargs.get('pk')
        porchlight = get_porchlight_by_sqid_or_404(porchlight_pk)
        self.check_object_permissions(self.request, porchlight)
        serializer.save(porchlight=porchlight)


class PorchlightMemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Manage a specific porchlight membership."""

    queryset = PorchlightMember.objects.all()
    serializer_class = PorchlightMemberSerializer
    permission_classes = [IsPorchlightOwnerOrAdmin]


class RsvpListCreateView(generics.ListCreateAPIView):
    """List or create binary RSVPs for accessible Beacons/Porchlights."""

    serializer_class = RsvpSerializer
    permission_classes = [permissions.AllowAny]

    def _actor(self):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        guest_id = getattr(self.request, 'guest_token', None) or self.request.headers.get('X-Guest-Token')
        return user, guest_id

    def _porchlight(self):
        porchlight_id = (
            self.request.query_params.get('porchlight')
            or self.request.query_params.get('beacon')
            or self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
            or self.request.data.get('porchlight')
            or self.request.data.get('beacon')
        )
        return get_porchlight_by_identifier(porchlight_id) if porchlight_id else None

    def _check_access(self, porchlight):
        if not porchlight:
            raise ValidationError({'porchlight': 'A valid porchlight is required.'})
        if not HasPorchlightAccess().has_object_permission(self.request, self, porchlight):
            raise PermissionDenied('You do not have permission to RSVP for this porchlight.')
        return porchlight

    def get_queryset(self):
        porchlight = self._porchlight()
        if porchlight:
            self._check_access(porchlight)
        user, guest_id = self._actor()
        actor_filter = {'user': user} if user else {'guest_id': guest_id}
        return Rsvp.objects.filter(porchlight=porchlight, **actor_filter) if porchlight else Rsvp.objects.none()

    def perform_create(self, serializer):
        porchlight = self._check_access(self._porchlight())
        user, guest_id = self._actor()
        if not user and not guest_id:
            raise PermissionDenied('Authentication or a guest token is required.')
        if Rsvp.objects.filter(porchlight=porchlight, **({'user': user} if user else {'guest_id': guest_id})).exists():
            raise ValidationError({'detail': 'RSVP already exists.'})
        serializer.save(user=user, guest_id=guest_id, porchlight=porchlight)


class RsvpDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an RSVP response."""

    permission_classes = [permissions.AllowAny]
    serializer_class = RsvpSerializer

    def get_queryset(self):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        guest_id = getattr(self.request, 'guest_token', None) or self.request.headers.get('X-Guest-Token')
        return Rsvp.objects.filter(user=user) if user else Rsvp.objects.filter(guest_id=guest_id)


class PermissionListCreateView(generics.ListCreateAPIView):
    """List or grant permissions for Beacons/Porchlights."""

    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        porchlight_id = (
            self.request.query_params.get('porchlight')
            or self.request.query_params.get('beacon')
            or self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
        )
        queryset = Permission.objects.filter(
            Q(porchlight__owner=user) | Q(user=user)
        ).distinct()
        if porchlight_id:
            porchlight = get_porchlight_by_identifier(porchlight_id)
            queryset = queryset.filter(porchlight=porchlight) if porchlight else queryset.none()
        return queryset

    def perform_create(self, serializer):
        porchlight_id = (
            self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
            or self.request.data.get('porchlight')
            or self.request.data.get('beacon')
        )
        if porchlight_id:
            porchlight = get_porchlight_by_identifier(porchlight_id)
            if not porchlight:
                raise Http404
            serializer.save(porchlight=porchlight)
        else:
            serializer.save()
