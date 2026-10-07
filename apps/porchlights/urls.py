"""URL configuration for Porchlights and Beacons app."""
from django.urls import path
from .views_access import (
    GuestAccessView,
    PermissionListCreateView,
    PorchlightAccessView,
    PorchlightMemberDetailView,
    PorchlightMemberListView,
)
from .views_invitations import (
    AcceptInvitationView,
    InvitationDetailView,
    InvitationListCreateView,
    InvitationParticipantsView,
    InvitationRevokeAllView,
    ValidateInvitationView,
)
from .views_porchlights import (
    BeaconControlView,
    BeaconDetailView,
    BeaconListCreateView,
    GeocodeAddressView,
    NeighborhoodListView,
    PorchlightControlView,
    PorchlightDetailView,
    PorchlightListCreateView,
)
from .views_rsvps import RsvpDetailView, RsvpListCreateView

app_name = 'porchlights'

urlpatterns = [
    path('porchlights/geocode/', GeocodeAddressView.as_view(), name='porchlight-geocode'),
    path('neighborhood/', NeighborhoodListView.as_view(), name='neighborhood-list'),
    # Porchlight endpoints
    path('porchlights/', PorchlightListCreateView.as_view(), name='porchlight-list-create'),
    path('porchlights/<str:pk>/', PorchlightDetailView.as_view(), name='porchlight-detail'),
    path('porchlights/<str:pk>/control/', PorchlightControlView.as_view(), name='porchlight-control'),
    path('porchlights/<str:pk>/access/', PorchlightAccessView.as_view(), name='porchlight-access'),
    path('porchlights/<str:pk>/access/<uuid:access_id>/', PorchlightAccessView.as_view(), name='porchlight-access-detail'),
    path('porchlights/<str:pk>/members/', PorchlightMemberListView.as_view(), name='porchlight-members'),
    path('porchlights/<str:porchlight_pk>/members/<uuid:pk>/', PorchlightMemberDetailView.as_view(), name='porchlight-member-detail'),
    path('porchlights/<str:porchlight_pk>/permissions/', PermissionListCreateView.as_view(), name='porchlight-permissions'),
    path('porchlights/<str:porchlight_pk>/rsvps/', RsvpListCreateView.as_view(), name='porchlight-rsvps'),

    # Beacon endpoints (Laravel compatibility routes)
    path('beacons/', BeaconListCreateView.as_view(), name='beacon-list-create'),
    path('beacons/<str:pk>/', BeaconDetailView.as_view(), name='beacon-detail'),
    path('beacons/<str:pk>/control/', BeaconControlView.as_view(), name='beacon-control'),
    path('beacons/<str:pk>/members/', PorchlightMemberListView.as_view(), name='beacon-members'),
    path('beacons/<str:porchlight_pk>/permissions/', PermissionListCreateView.as_view(), name='beacon-permissions'),
    path('beacons/<str:porchlight_pk>/rsvps/', RsvpListCreateView.as_view(), name='beacon-rsvps'),

    # General RSVP endpoints
    path('rsvps/', RsvpListCreateView.as_view(), name='rsvp-list-create'),
    path('rsvps/<uuid:pk>/', RsvpDetailView.as_view(), name='rsvp-detail'),

    # General Permission endpoints
    path('permissions/', PermissionListCreateView.as_view(), name='permission-list-create'),

    # Invitation endpoints
    path('invitations/', InvitationListCreateView.as_view(), name='invitation-list-create'),
    path('invitations/<uuid:pk>/', InvitationDetailView.as_view(), name='invitation-detail'),
    path('invitations/validate/<str:code>/', ValidateInvitationView.as_view(), name='invitation-validate'),
    path('invitations/manage/<str:code>/', InvitationParticipantsView.as_view(), name='invitation-participants'),
    path('invitations/manage/<str:code>/revoke-all/', InvitationRevokeAllView.as_view(), name='invitation-revoke-all'),
    path('invitations/accept/', AcceptInvitationView.as_view(), name='invitation-accept'),

    # Guest Access endpoints
    path('guest/access/', GuestAccessView.as_view(), name='guest-access'),
]
