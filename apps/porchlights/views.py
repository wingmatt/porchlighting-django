"""API views for Porchlights, Beacons, Invitations, Permissions, RSVPs, Memberships, and Guest Access."""
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.firebase import create_firebase_custom_token
from .models import (
    GuestSession,
    Invitation,
    Permission,
    Porchlight,
    PorchlightMember,
    PorchlightRole,
    Rsvp,
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


# BeaconListCreateView alias for Laravel migration route compatibility
BeaconListCreateView = PorchlightListCreateView


class PorchlightDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a porchlight/beacon."""

    queryset = Porchlight.objects.all()
    permission_classes = [HasPorchlightAccess]

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
        porchlight = get_object_or_404(Porchlight, pk=pk)
        self.check_object_permissions(request, porchlight)

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
            | Q(porchlight__permission_grants__user=user, porchlight__permission_grants__role__in=['owner', 'share', 'admin'])
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
                'porchlight': PorchlightSerializer(invitation.porchlight, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


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

    def post(self, request, *args, **kwargs):
        serializer = GuestAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invitation_code = serializer.validated_data['invitation_code']
        guest_name = serializer.validated_data.get('guest_name', 'Guest')
        invitation = Invitation.get_by_sqid(invitation_code)
        if not invitation:
            return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Create guest session
        session = GuestSession.objects.create(
            invitation=invitation,
            guest_name=guest_name,
        )

        # Also record permission grant for guest
        Permission.objects.create(
            porchlight=invitation.porchlight,
            guest_id=session.guest_token,
            role=invitation.role_granted,
            from_invitation=invitation,
        )

        invitation.record_usage()
        firebase_token = create_firebase_custom_token(
            f"guest_{session.guest_token}",
            {'guest': True, 'guest_token': session.guest_token, 'porchlight_id': str(invitation.porchlight_id)},
        )

        return Response(
            {
                'guest_token': session.guest_token,
                'guest_name': session.guest_name,
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
        return PorchlightMember.objects.filter(porchlight_id=porchlight_pk)

    def perform_create(self, serializer):
        porchlight_pk = self.kwargs.get('porchlight_pk') or self.kwargs.get('pk')
        porchlight = get_object_or_404(Porchlight, pk=porchlight_pk)
        self.check_object_permissions(self.request, porchlight)
        serializer.save(porchlight=porchlight)


class PorchlightMemberDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Manage a specific porchlight membership."""

    queryset = PorchlightMember.objects.all()
    serializer_class = PorchlightMemberSerializer
    permission_classes = [IsPorchlightOwnerOrAdmin]


class RsvpListCreateView(generics.ListCreateAPIView):
    """List or create RSVPs for Beacons/Porchlights."""

    serializer_class = RsvpSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        porchlight_id = (
            self.request.query_params.get('porchlight')
            or self.request.query_params.get('beacon')
            or self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
        )
        queryset = Rsvp.objects.all()
        if porchlight_id:
            queryset = queryset.filter(porchlight_id=porchlight_id)
        elif self.request.user and self.request.user.is_authenticated:
            queryset = queryset.filter(user=self.request.user)
        elif getattr(self.request, 'guest_token', None):
            queryset = queryset.filter(guest_id=self.request.guest_token)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        guest_id = (
            getattr(self.request, 'guest_token', None)
            or self.request.headers.get('X-Guest-Token')
            or self.request.data.get('guest_id')
        )
        porchlight_id = (
            self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
            or self.request.data.get('porchlight')
            or self.request.data.get('beacon')
        )
        if porchlight_id:
            porchlight = get_object_or_404(Porchlight, pk=porchlight_id)
            serializer.save(user=user, guest_id=guest_id, porchlight=porchlight)
        else:
            serializer.save(user=user, guest_id=guest_id)


class RsvpDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an RSVP response."""

    queryset = Rsvp.objects.all()
    serializer_class = RsvpSerializer
    permission_classes = [permissions.AllowAny]


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
            queryset = queryset.filter(porchlight_id=porchlight_id)
        return queryset

    def perform_create(self, serializer):
        porchlight_id = (
            self.kwargs.get('porchlight_pk')
            or self.kwargs.get('pk')
            or self.request.data.get('porchlight')
            or self.request.data.get('beacon')
        )
        if porchlight_id:
            porchlight = get_object_or_404(Porchlight, pk=porchlight_id)
            serializer.save(porchlight=porchlight)
        else:
            serializer.save()
