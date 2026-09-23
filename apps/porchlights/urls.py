"""URL configuration for Porchlights app."""
from django.urls import path
from .views import (
    AcceptInvitationView,
    GuestAccessView,
    InvitationDetailView,
    InvitationListCreateView,
    PorchlightControlView,
    PorchlightDetailView,
    PorchlightListCreateView,
    PorchlightMemberListView,
    ValidateInvitationView,
)

app_name = 'porchlights'

urlpatterns = [
    # Porchlight endpoints
    path('porchlights/', PorchlightListCreateView.as_view(), name='porchlight-list-create'),
    path('porchlights/<uuid:pk>/', PorchlightDetailView.as_view(), name='porchlight-detail'),
    path('porchlights/<uuid:pk>/control/', PorchlightControlView.as_view(), name='porchlight-control'),
    path('porchlights/<uuid:pk>/members/', PorchlightMemberListView.as_view(), name='porchlight-members'),

    # Invitation endpoints
    path('invitations/', InvitationListCreateView.as_view(), name='invitation-list-create'),
    path('invitations/<uuid:pk>/', InvitationDetailView.as_view(), name='invitation-detail'),
    path('invitations/validate/<str:code>/', ValidateInvitationView.as_view(), name='invitation-validate'),
    path('invitations/accept/', AcceptInvitationView.as_view(), name='invitation-accept'),

    # Guest Access endpoints
    path('guest/access/', GuestAccessView.as_view(), name='guest-access'),
]
