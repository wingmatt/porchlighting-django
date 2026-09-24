"""Django signals for synchronizing Porchlight and membership changes to Firebase."""
import logging
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import GuestSession, Porchlight, PorchlightMember
from .tasks import (
    delete_porchlight_from_firebase_task,
    sync_porchlight_to_firebase_task,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Porchlight)
def handle_porchlight_saved(sender, instance, created, **kwargs):
    """Trigger background Firebase sync when Porchlight is created or updated."""
    porchlight_id = str(instance.id)
    transaction.on_commit(lambda: sync_porchlight_to_firebase_task.delay(porchlight_id))


@receiver(post_delete, sender=Porchlight)
def handle_porchlight_deleted(sender, instance, **kwargs):
    """Trigger background Firebase deletion when Porchlight is deleted."""
    porchlight_id = str(instance.id)
    transaction.on_commit(lambda: delete_porchlight_from_firebase_task.delay(porchlight_id))


@receiver(post_save, sender=PorchlightMember)
def handle_porchlight_member_saved(sender, instance, **kwargs):
    """Re-sync Porchlight permissions when a member is added or modified."""
    porchlight_id = str(instance.porchlight_id)
    transaction.on_commit(lambda: sync_porchlight_to_firebase_task.delay(porchlight_id, notify_fcm=False))


@receiver(post_delete, sender=PorchlightMember)
def handle_porchlight_member_deleted(sender, instance, **kwargs):
    """Re-sync Porchlight permissions when a member is removed."""
    porchlight_id = str(instance.porchlight_id)
    transaction.on_commit(lambda: sync_porchlight_to_firebase_task.delay(porchlight_id, notify_fcm=False))


@receiver(post_save, sender=GuestSession)
def handle_guest_session_saved(sender, instance, **kwargs):
    """Re-sync Porchlight permissions when a guest session is created."""
    porchlight_id = str(instance.invitation.porchlight_id)
    transaction.on_commit(lambda: sync_porchlight_to_firebase_task.delay(porchlight_id, notify_fcm=False))


@receiver(post_delete, sender=GuestSession)
def handle_guest_session_deleted(sender, instance, **kwargs):
    """Re-sync Porchlight permissions when a guest session is deleted."""
    porchlight_id = str(instance.invitation.porchlight_id)
    transaction.on_commit(lambda: sync_porchlight_to_firebase_task.delay(porchlight_id, notify_fcm=False))
