"""API views for Porchlights, Invitations, Memberships, and Guest Access."""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GuestSession, Invitation, Porchlight, PorchlightMember, PorchlightRole
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
    PorchlightControlSerializer,
    PorchlightDetailSerializer,
    PorchlightMemberSerializer,
    PorchlightSerializer,
)


class PorchlightListCreateView(generics.ListCreateAPIView):
    """List porchlights accessible to user or create a new porchlight."""

    serializer_class = PorchlightSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Porchlight.objects.filter(
            Q(owner=user) | Q(memberships__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class PorchlightDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a porchlight."""

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


class PorchlightControlView(APIView):
    """Toggle power, change brightness, color, or status message of a Porchlight."""

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


class InvitationListCreateView(generics.ListCreateAPIView):
    """List or create invitations for porchlights."""

    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return InvitationCreateSerializer
        return InvitationSerializer

    def get_queryset(self):
        user = self.request.user
        porchlight_id = self.request.query_params.get('porchlight')
        queryset = Invitation.objects.filter(
            Q(porchlight__owner=user)
            | Q(porchlight__memberships__user=user, porchlight__memberships__role=PorchlightRole.ADMIN)
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
    """Validate an invitation code and return basic invitation info."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, code, *args, **kwargs):
        try:
            invitation = Invitation.objects.select_related('porchlight', 'invited_by').get(code=code)
        except Invitation.DoesNotExist:
            return Response({'error': 'Invitation not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                'code': invitation.code,
                'porchlight_id': str(invitation.porchlight_id),
                'porchlight_name': invitation.porchlight.name,
                'invited_by': invitation.invited_by.full_name,
                'role': invitation.role,
                'role_display': invitation.get_role_display(),
                'is_guest': invitation.is_guest,
                'is_valid': invitation.is_valid(),
                'is_expired': invitation.is_expired,
                'is_exhausted': invitation.is_exhausted,
                'expires_at': invitation.expires_at,
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
        invitation = Invitation.objects.select_related('porchlight').get(code=code)

        # Ensure user isn't already the owner
        if invitation.porchlight.owner_id == request.user.id:
            return Response(
                {'error': 'You are already the owner of this Porchlight.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or update membership
        member, created = PorchlightMember.objects.update_or_create(
            porchlight=invitation.porchlight,
            user=request.user,
            defaults={'role': invitation.role},
        )

        invitation.record_usage()

        return Response(
            {
                'message': f"Successfully joined {invitation.porchlight.name} as {member.get_role_display()}.",
                'membership': PorchlightMemberSerializer(member).data,
                'porchlight': PorchlightSerializer(invitation.porchlight, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


class GuestAccessView(APIView):
    """Obtain guest access session and token using an invitation code."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = GuestAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invitation_code = serializer.validated_data['invitation_code']
        guest_name = serializer.validated_data.get('guest_name', 'Guest')
        invitation = Invitation.objects.select_related('porchlight').get(code=invitation_code)

        # Create guest session
        session = GuestSession.objects.create(
            invitation=invitation,
            guest_name=guest_name,
        )

        invitation.record_usage()

        return Response(
            {
                'message': f"Guest access granted to {invitation.porchlight.name}.",
                'guest_token': session.guest_token,
                'guest_name': session.guest_name,
                'role': invitation.role,
                'porchlight': PorchlightSerializer(
                    invitation.porchlight,
                    context={'request': request},
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class PorchlightMemberListView(generics.ListAPIView):
    """List members for a specific Porchlight."""

    serializer_class = PorchlightMemberSerializer
    permission_classes = [HasPorchlightAccess]

    def get_queryset(self):
        porchlight_id = self.kwargs.get('pk')
        porchlight = get_object_or_404(Porchlight, pk=porchlight_id)
        self.check_object_permissions(self.request, porchlight)
        return porchlight.memberships.all()
