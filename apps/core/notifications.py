"""Push notification delivery for Porchlight state changes."""
import logging
import json

from django.conf import settings
from django.db import models

from apps.accounts.models import FCMDeviceToken, WebPushSubscription
from apps.core.firebase import send_fcm_multicast

logger = logging.getLogger(__name__)


def notify_porchlight_turned_on(porchlight, actor_user=None, actor_guest_token=None):
    """Notify every permitted recipient except the actor who turned it on."""
    user_ids = set(porchlight.permission_grants.filter(user__isnull=False).values_list('user_id', flat=True))
    user_ids.update(porchlight.memberships.values_list('user_id', flat=True))
    user_ids.add(porchlight.owner_id)
    guest_tokens = set(porchlight.permission_grants.filter(guest_id__isnull=False).values_list('guest_id', flat=True))
    if actor_user:
        user_ids.discard(actor_user.id)
    if actor_guest_token:
        guest_tokens.discard(actor_guest_token)

    title = f'{porchlight.name} is on'
    body = f'{porchlight.name} was turned on.'
    data = {'porchlight_id': str(porchlight.id), 'porchlight_sqid': porchlight.sqid, 'event': 'turned_on'}
    recipient_filter = models.Q(user_id__in=user_ids) | models.Q(guest_token__in=guest_tokens)
    fcm_tokens = list(FCMDeviceToken.objects.filter(is_active=True).filter(recipient_filter).values_list('registration_token', flat=True))
    fcm_result = send_fcm_multicast(fcm_tokens, title=title, body=body, data=data)

    web_result = {'success_count': 0, 'failure_count': 0}
    subscriptions = WebPushSubscription.objects.filter(is_active=True).filter(recipient_filter)
    if getattr(settings, 'WEB_PUSH_VAPID_PRIVATE_KEY', '') and getattr(settings, 'WEB_PUSH_VAPID_CLAIMS', ''):
        from pywebpush import WebPushException, webpush
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info={
                        'endpoint': subscription.endpoint,
                        'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                    },
                    data=json.dumps({'title': title, 'body': body, 'url': f'/porchlight/{porchlight.sqid}', 'data': data}),
                    vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
                    vapid_claims={'sub': settings.WEB_PUSH_VAPID_CLAIMS},
                )
                web_result['success_count'] += 1
            except WebPushException as exc:
                web_result['failure_count'] += 1
                if getattr(exc, 'response', None) is not None and exc.response.status_code in (404, 410):
                    subscription.is_active = False
                    subscription.save(update_fields=['is_active', 'updated_at'])
                else:
                    logger.warning('Web Push delivery failed for subscription %s: %s', subscription.id, exc)
            except Exception:
                web_result['failure_count'] += 1
                logger.exception('Unexpected Web Push delivery failure for subscription %s', subscription.id)
    return {'fcm': fcm_result, 'web': web_result}