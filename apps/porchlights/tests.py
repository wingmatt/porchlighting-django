"""Tests for Porchlight models, Invitations, Memberships, and Permissions."""
import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import GuestSession, Invitation, Porchlight, PorchlightMember, PorchlightRole
from .tasks import (
    delete_porchlight_from_firebase_task,
    send_porchlight_fcm_update_task,
    sync_porchlight_to_firebase_task,
)
from apps.accounts.models import FCMDeviceToken

User = get_user_model()


class PorchlightAndPermissionTests(TestCase):
    """Test Porchlights, member access, guest invitations, and controls."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(email='owner@example.com', password='Password123!', first_name='Owner')
        self.member = User.objects.create_user(email='member@example.com', password='Password123!', first_name='Member')
        self.stranger = User.objects.create_user(email='stranger@example.com', password='Password123!', first_name='Stranger')

        self.porchlight = Porchlight.objects.create(
            name='Front Porch Light',
            description='Main entryway light',
            owner=self.owner,
            is_on=False,
            brightness=80,
            color='#FFAA00',
        )

    def test_porchlight_creation_and_owner_access(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse('porchlights:porchlight-list-create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Front Porch Light')
        self.assertEqual(response.data[0]['user_role'], 'OWNER')

    def test_stranger_cannot_access_unshared_porchlight(self):
        self.client.force_authenticate(user=self.stranger)
        url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_invitation_and_acceptance(self):
        # 1. Owner creates invitation for member
        self.client.force_authenticate(user=self.owner)
        invitation_url = reverse('porchlights:invitation-list-create')
        invitation_payload = {
            'porchlight': str(self.porchlight.id),
            'role': PorchlightRole.MEMBER,
            'is_guest': False,
            'max_uses': 1,
        }
        res = self.client.post(invitation_url, invitation_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        code = res.data['code']

        # 2. Member accepts invitation
        self.client.force_authenticate(user=self.member)
        accept_url = reverse('porchlights:invitation-accept')
        accept_res = self.client.post(accept_url, {'code': code}, format='json')
        self.assertEqual(accept_res.status_code, status.HTTP_200_OK)
        self.assertTrue(PorchlightMember.objects.filter(porchlight=self.porchlight, user=self.member).exists())

        # 3. Member can now view and control the porchlight
        detail_url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.id})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data['user_role'], 'MEMBER')

        control_url = reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.id})
        ctrl_res = self.client.post(control_url, {'action': 'turn_on', 'brightness': 100}, format='json')
        self.assertEqual(ctrl_res.status_code, status.HTTP_200_OK)
        self.porchlight.refresh_from_db()
        self.assertTrue(self.porchlight.is_on)
        self.assertEqual(self.porchlight.brightness, 100)

    def test_guest_invitation_and_guest_control(self):
        # 1. Create a guest invitation
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
            max_uses=2,
        )

        # 2. Unauthenticated client requests guest session
        guest_access_url = reverse('porchlights:guest-access')
        guest_res = self.client.post(
            guest_access_url,
            {'invitation_code': invitation.code, 'guest_name': 'Party Guest'},
            format='json',
        )
        self.assertEqual(guest_res.status_code, status.HTTP_200_OK)
        guest_token = guest_res.data['guest_token']
        self.assertIsNotNone(guest_token)

        # 3. Guest controls porchlight using X-Guest-Token header
        control_url = reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.id})
        ctrl_res = self.client.post(
            control_url,
            {'action': 'toggle', 'color': '#00FF00'},
            format='json',
            HTTP_X_GUEST_TOKEN=guest_token,
        )
        self.assertEqual(ctrl_res.status_code, status.HTTP_200_OK)
        self.porchlight.refresh_from_db()
        self.assertTrue(self.porchlight.is_on)
        self.assertEqual(self.porchlight.color, '#00FF00')

    def test_expired_invitation_rejection(self):
        expired_invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
            expires_at=timezone.now() - datetime.timedelta(days=1),
        )
        guest_access_url = reverse('porchlights:guest-access')
        res = self.client.post(
            guest_access_url,
            {'invitation_code': expired_invitation.code},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_firebase_payload_contains_permissions(self):
        PorchlightMember.objects.create(
            porchlight=self.porchlight,
            user=self.member,
            role=PorchlightRole.MEMBER,
        )
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
        )
        session = GuestSession.objects.create(
            invitation=invitation,
            guest_name='Guest1',
        )

        payload = self.porchlight.get_firebase_payload()
        self.assertEqual(payload['id'], str(self.porchlight.id))
        self.assertIn(str(self.owner.id), payload['allowed_users'])
        self.assertIn(str(self.member.id), payload['allowed_users'])
        self.assertIn(session.guest_token, payload['allowed_guest_tokens'])

    def test_celery_tasks_execution(self):
        # 1. Register device token for owner
        FCMDeviceToken.objects.create(
            user=self.owner,
            registration_token='device-token-owner-123',
            is_active=True,
        )

        # 2. Test sync task
        sync_result = sync_porchlight_to_firebase_task(str(self.porchlight.id), notify_fcm=False)
        self.assertIsInstance(sync_result, bool)

        # 3. Test fcm update task
        fcm_result = send_porchlight_fcm_update_task(str(self.porchlight.id))
        self.assertIsInstance(fcm_result, dict)

        # 4. Test delete task
        delete_result = delete_porchlight_from_firebase_task(str(self.porchlight.id))
        self.assertIsInstance(delete_result, bool)

    def test_guest_access_returns_firebase_token_field(self):
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
        )
        guest_access_url = reverse('porchlights:guest-access')
        guest_res = self.client.post(
            guest_access_url,
            {'invitation_code': invitation.code, 'guest_name': 'Party Guest'},
            format='json',
        )
        self.assertEqual(guest_res.status_code, status.HTTP_200_OK)
        self.assertIn('firebase_token', guest_res.data)
