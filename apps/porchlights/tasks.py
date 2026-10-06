"""Celery background tasks for Firebase synchronization and FCM notifications."""
import logging
from celery import shared_task
from django.core.cache import cache
from django.db.models import Q

from apps.accounts.models import FCMDeviceToken
from apps.core.firebase import (
    delete_porchlight_from_firebase,
    send_fcm_multicast,
    sync_porchlight_to_firebase,
)

logger = logging.getLogger(__name__)

SYNC_PENDING_TIMEOUT = 60 * 15


def schedule_porchlight_sync(porchlight_id: str, notify_fcm: bool = True) -> bool:
    """Queue at most one pending sync for a Porchlight at a time."""
    porchlight_id = str(porchlight_id)
    pending_key = f'porchlight-sync-pending:{porchlight_id}'
    notify_key = f'porchlight-sync-notify:{porchlight_id}'

    if notify_fcm:
        cache.set(notify_key, True, timeout=SYNC_PENDING_TIMEOUT)
    if not cache.add(pending_key, True, timeout=SYNC_PENDING_TIMEOUT):
        return False

    sync_porchlight_to_firebase_task.delay(porchlight_id, notify_fcm=notify_fcm)
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def sync_porchlight_to_firebase_task(self, porchlight_id: str, notify_fcm: bool = True):
    """Sync Porchlight state and permissions to Firebase Firestore/Realtime DB."""
    from apps.porchlights.models import Porchlight

    pending_key = f'porchlight-sync-pending:{porchlight_id}'
    notify_key = f'porchlight-sync-notify:{porchlight_id}'
    try:
        porchlight = Porchlight.objects.get(pk=porchlight_id)
        payload = porchlight.get_firebase_payload()
        success = sync_porchlight_to_firebase(str(porchlight.id), payload)

        if notify_fcm or cache.get(notify_key, False):
            # Broadcast push / data notification to permitted devices
            send_porchlight_fcm_update_task.delay(str(porchlight.id))

        return success
    except Porchlight.DoesNotExist:
        logger.warning("Porchlight %s not found for Firebase sync.", porchlight_id)
        return False
    except Exception as exc:
        logger.error("Error in sync_porchlight_to_firebase_task for %s: %s", porchlight_id, exc)
        raise self.retry(exc=exc)
    finally:
        cache.delete(pending_key)
        cache.delete(notify_key)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def delete_porchlight_from_firebase_task(self, porchlight_id: str):
    """Remove Porchlight from Firebase when deleted in Django."""
    try:
        return delete_porchlight_from_firebase(str(porchlight_id))
    except Exception as exc:
        logger.error("Error in delete_porchlight_from_firebase_task for %s: %s", porchlight_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_porchlight_fcm_update_task(self, porchlight_id: str):
    """Send FCM notification to all active devices permitted to view the Porchlight."""
    from apps.porchlights.models import Porchlight

    try:
        porchlight = Porchlight.objects.get(pk=porchlight_id)

        user_ids = [porchlight.owner_id] + list(porchlight.memberships.values_list('user_id', flat=True))
        guest_tokens = list(
            porchlight.invitations.filter(is_guest=True, guest_sessions__isnull=False)
            .values_list('guest_sessions__guest_token', flat=True)
            .distinct()
        )

        device_tokens = list(
            FCMDeviceToken.objects.filter(is_active=True)
            .filter(Q(user_id__in=user_ids) | Q(guest_token__in=guest_tokens))
            .values_list('registration_token', flat=True)
            .distinct()
        )

        if not device_tokens:
            return {'sent': 0, 'status': 'no_tokens'}

        title = f"Porchlight '{porchlight.name}' Updated"
        state_str = "ON" if porchlight.is_on else "OFF"
        body = f"{porchlight.name} is now {state_str} (Brightness: {porchlight.brightness}%)"

        data = {
            'porchlight_id': str(porchlight.id),
            'name': porchlight.name,
            'is_on': str(porchlight.is_on),
            'brightness': str(porchlight.brightness),
            'color': porchlight.color,
            'status_message': porchlight.status_message or '',
            'type': 'porchlight_update',
        }

        result = send_fcm_multicast(device_tokens, title=title, body=body, data=data)
        return result
    except Porchlight.DoesNotExist:
        logger.warning("Porchlight %s not found for FCM update notification.", porchlight_id)
        return {'sent': 0, 'status': 'not_found'}
    except Exception as exc:
        logger.error("Error sending FCM update for porchlight %s: %s", porchlight_id, exc)
        raise self.retry(exc=exc)
