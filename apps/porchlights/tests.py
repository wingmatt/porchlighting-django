"""Tests for Porchlight models, Invitations, Memberships, and Permissions."""
import datetime
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .models import GuestSession, Invitation, Permission, Porchlight, PorchlightMember, PorchlightRole
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
        self.assertEqual(response.data[0]['sqid'], self.porchlight.sqid)

    @patch('apps.porchlights.views.settings.GEOCODIO_API_KEY', 'test-key')
    @patch('apps.porchlights.views.Geocodio')
    def test_geocode_address_returns_coordinates(self, mock_geocodio):
        mock_geocodio.return_value.geocode.return_value.results = [
            type('Result', (), {'location': type('Location', (), {'lat': 40.7128, 'lng': -74.006})()})()
        ]
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(
            reverse('porchlights:porchlight-geocode'),
            {'address': 'New York, NY'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'latitude': 40.7128, 'longitude': -74.006})
        mock_geocodio.assert_called_once_with('test-key')
        mock_geocodio.return_value.geocode.assert_called_once_with('New York, NY')

    def test_porchlight_urls_use_sqid(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.sqid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['sqid'], self.porchlight.sqid)

        uuid_url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.id})
        uuid_response = self.client.get(uuid_url)
        self.assertEqual(uuid_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_edit_permission_can_update_porchlight(self):
        Permission.objects.create(porchlight=self.porchlight, user=self.member, role='edit')
        self.client.force_authenticate(user=self.member)

        response = self.client.patch(
            reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.sqid}),
            {'name': 'Updated Porch'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.porchlight.refresh_from_db()
        self.assertEqual(self.porchlight.name, 'Updated Porch')

    def test_owner_can_toggle_porchlight_control(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.sqid}),
            {'action': 'toggle'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['porchlight']['is_on'])
        self.porchlight.refresh_from_db()
        self.assertTrue(self.porchlight.is_on)

    def test_porchlight_has_reusable_default_view_invitation(self):
        invitation = Invitation.objects.get(porchlight=self.porchlight, is_guest=False)
        self.assertIsNone(invitation.expires_at)
        self.assertEqual(invitation.max_uses, 0)
        self.assertEqual(invitation.role_granted, 'view')
        self.assertTrue(invitation.is_valid())

        validate_url = reverse('porchlights:invitation-validate', kwargs={'code': invitation.sqid})
        response = self.client.get(validate_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['has_permission'])

        self.client.force_authenticate(user=self.member)
        accept_url = reverse('porchlights:invitation-accept')
        response = self.client.post(accept_url, {'code': invitation.sqid}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        permission = Permission.objects.get(porchlight=self.porchlight, user=self.member)
        self.assertEqual(permission.role, 'view')
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_valid())

    def test_custom_invitation_role_creates_custom_permission(self):
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role='manage_schedule',
        )
        self.client.force_authenticate(user=self.member)
        response = self.client.post(
            reverse('porchlights:invitation-accept'), {'code': invitation.sqid}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['membership'])
        self.assertEqual(
            Permission.objects.get(porchlight=self.porchlight, user=self.member).role,
            'manage_schedule',
        )

    def test_stranger_cannot_access_unshared_porchlight(self):
        self.client.force_authenticate(user=self.stranger)
        url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.sqid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_edit_and_share_permissions_can_manage_invitations(self):
        Permission.objects.create(porchlight=self.porchlight, user=self.member, role='edit')
        expired = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            expires_at=timezone.now() - datetime.timedelta(minutes=1),
        )
        inactive = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_active=False,
        )
        active = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
        )

        self.client.force_authenticate(user=self.member)
        invitation_url = reverse('porchlights:invitation-list-create')
        response = self.client.get(invitation_url, {'porchlight': str(self.porchlight.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation_ids = {item['id'] for item in response.data}
        self.assertIn(str(active.id), invitation_ids)
        self.assertIn(str(expired.id), invitation_ids)
        self.assertNotIn(str(inactive.id), invitation_ids)

        create_response = self.client.post(
            invitation_url,
            {'porchlight': str(self.porchlight.id), 'role': PorchlightRole.GUEST},
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(create_response.data['id'], str(expired.id))
        self.assertNotEqual(create_response.data['id'], str(inactive.id))

    def test_owner_edit_and_share_users_can_copy_invitation_link(self):
        invitation = Invitation.objects.create(porchlight=self.porchlight, invited_by=self.owner)
        validate_url = reverse('porchlights:invitation-validate', kwargs={'code': invitation.sqid})

        self.client.force_authenticate(user=self.owner)
        response = self.client.get(validate_url)
        self.assertTrue(response.data['can_share'])

        for role in ('edit', 'share'):
            Permission.objects.create(porchlight=self.porchlight, user=self.member, role=role)
            self.client.force_authenticate(user=self.member)
            response = self.client.get(validate_url)
            self.assertTrue(response.data['can_share'])
            Permission.objects.filter(porchlight=self.porchlight, user=self.member).delete()

        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(validate_url)
        self.assertFalse(response.data['can_share'])

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
        detail_url = reverse('porchlights:porchlight-detail', kwargs={'pk': self.porchlight.sqid})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data['user_role'], 'MEMBER')

        control_url = reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.sqid})
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
        control_url = reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.sqid})
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

    def test_invitation_list_includes_expired_and_acceptance_counts(self):
        active_invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.MEMBER,
            is_guest=False,
            max_uses=0,
        )
        expired_invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
            expires_at=timezone.now() - datetime.timedelta(days=1),
        )
        Permission.objects.create(
            porchlight=self.porchlight,
            user=self.member,
            role='edit',
            from_invitation=active_invitation,
        )
        GuestSession.objects.create(invitation=active_invitation, guest_name='Party Guest')

        self.client.force_authenticate(user=self.member)
        response = self.client.get(
            reverse('porchlights:invitation-list-create'),
            {'porchlight': self.porchlight.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitations = {item['id']: item for item in response.data}
        self.assertIn(str(active_invitation.id), invitations)
        self.assertIn(str(expired_invitation.id), invitations)
        active_data = invitations[str(active_invitation.id)]
        self.assertEqual(active_data['accepted_users_count'], 1)
        self.assertEqual(active_data['accepted_guests_count'], 1)
        self.assertEqual(active_data['accepted_count'], 2)
        self.assertFalse(active_data['is_expired'])
        self.assertTrue(invitations[str(expired_invitation.id)]['is_expired'])

    def test_invitation_owner_can_list_and_revoke_participants(self):
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.MEMBER,
            is_guest=True,
            max_uses=0,
        )
        user_permission = Permission.objects.create(
            porchlight=self.porchlight,
            user=self.member,
            role='edit',
            from_invitation=invitation,
        )
        guest = GuestSession.objects.create(invitation=invitation, guest_name='Party Guest')
        guest_permission = Permission.objects.create(
            porchlight=self.porchlight,
            guest_id=guest.guest_token,
            role='view',
            from_invitation=invitation,
        )

        self.client.force_authenticate(user=self.owner)
        manage_url = reverse('porchlights:invitation-participants', kwargs={'code': invitation.sqid})
        response = self.client.get(manage_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['type'] for item in response.data['participants']}, {'user', 'guest'})

        response = self.client.delete(manage_url, {'permission_id': str(user_permission.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Permission.objects.filter(pk=user_permission.id).exists())

        response = self.client.delete(manage_url, {'permission_id': str(guest_permission.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GuestSession.objects.filter(pk=guest.id).exists())

    def test_edit_user_can_revoke_all_and_rotate_invitation_code(self):
        invitation = Invitation.objects.create(porchlight=self.porchlight, invited_by=self.owner, max_uses=1)
        Permission.objects.create(porchlight=self.porchlight, user=self.member, role='edit', from_invitation=invitation)
        old_code = invitation.code
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            reverse('porchlights:invitation-revoke-all', kwargs={'code': invitation.sqid}),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertNotEqual(invitation.code, old_code)
        self.assertEqual(invitation.uses_count, 0)
        self.assertFalse(Permission.objects.filter(from_invitation=invitation).exists())

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

    def test_beacon_compatibility_endpoints(self):
        self.client.force_authenticate(user=self.owner)
        # Test listing beacons
        url = reverse('porchlights:beacon-list-create')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        # Test beacon detail
        detail_url = reverse('porchlights:beacon-detail', kwargs={'pk': self.porchlight.sqid})
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], 'Front Porch Light')

        # Test beacon control
        control_url = reverse('porchlights:beacon-control', kwargs={'pk': self.porchlight.sqid})
        res = self.client.post(control_url, {'action': 'turn_on'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_sqids_invitation_encoding_and_lookup(self):
        invitation = Invitation.objects.create(
            porchlight=self.porchlight,
            invited_by=self.owner,
            role=PorchlightRole.GUEST,
            is_guest=True,
        )
        sqid = invitation.sqid
        self.assertIsNotNone(sqid)
        found_invitation = Invitation.get_by_sqid(sqid)
        self.assertEqual(found_invitation.id, invitation.id)

        # Test validate endpoint with sqid
        validate_url = reverse('porchlights:invitation-validate', kwargs={'code': sqid})
        res = self.client.get(validate_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['sqid'], sqid)

    def test_rsvps_and_permissions_endpoints(self):
        self.client.force_authenticate(user=self.member)
        # Create RSVP
        rsvp_url = reverse('porchlights:rsvp-list-create')
        res = self.client.post(
            rsvp_url,
            {'porchlight': str(self.porchlight.id), 'type': 'yes'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['type'], 'yes')

        # List RSVPs for beacon
        beacon_rsvps_url = reverse('porchlights:beacon-rsvps', kwargs={'porchlight_pk': self.porchlight.sqid})
        res = self.client.get(beacon_rsvps_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        # Create Permission as owner
        self.client.force_authenticate(user=self.owner)
        perm_url = reverse('porchlights:permission-list-create')
        res = self.client.post(
            perm_url,
            {'porchlight': str(self.porchlight.id), 'user': self.member.id, 'role': 'edit'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_location_geocoordinates_and_firebase_broadcast(self):
        # 1. Update location with geocoordinates dictionary
        coords = {'latitude': 37.774929, 'longitude': -122.419416}
        self.client.force_authenticate(user=self.owner)
        control_url = reverse('porchlights:porchlight-control', kwargs={'pk': self.porchlight.sqid})
        res = self.client.post(
            control_url,
            {'location': coords},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.porchlight.refresh_from_db()
        self.assertEqual(self.porchlight.location, coords)
        self.assertIsNotNone(self.porchlight.coordinates)
        self.assertAlmostEqual(self.porchlight.coordinates['latitude'], 37.774929, places=5)
        self.assertAlmostEqual(self.porchlight.coordinates['longitude'], -122.419416, places=5)

        # 2. Verify payload for Firebase broadcast includes location and coordinates
        payload = self.porchlight.get_firebase_payload()
        self.assertEqual(payload['location'], coords)
        self.assertIsNotNone(payload['coordinates'])
        self.assertAlmostEqual(payload['coordinates']['latitude'], 37.774929, places=5)
        self.assertAlmostEqual(payload['coordinates']['longitude'], -122.419416, places=5)

        # 3. Test string coordinates parsing
        self.porchlight.location = "40.7128, -74.0060"
        self.porchlight.save()
        self.assertIsNotNone(self.porchlight.coordinates)
        self.assertAlmostEqual(self.porchlight.coordinates['latitude'], 40.7128, places=4)
        self.assertAlmostEqual(self.porchlight.coordinates['longitude'], -74.0060, places=4)
