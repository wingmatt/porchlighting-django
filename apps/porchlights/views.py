"""Public view API for the Porchlights app.

Domain-specific modules expose the endpoint groups, while this facade keeps
the historical ``apps.porchlights.views`` import path stable.
"""

from django.conf import settings
from apps.core.notifications import notify_porchlight_turned_on
from geocodio import Geocodio

from .views_legacy import (
    can_manage_invitation,
    can_manage_porchlight_access,
    get_porchlight_by_identifier,
    get_porchlight_by_sqid_or_404,
    invitation_participant_data,
    porchlight_access_data,
    porchlight_queryset,
)
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

__all__ = [name for name in globals() if not name.startswith('_')]