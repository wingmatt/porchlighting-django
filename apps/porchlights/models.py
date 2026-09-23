"""Models for Porchlights, Memberships, Invitations, and Guest Access."""
import secrets
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.firebase import sync_porchlight_to_firebase


class PorchlightRole(models.TextChoices):
    """Permission roles for Porchlight access."""
    OWNER = 'OWNER', _('Owner')
    ADMIN = 'ADMIN', _('Admin')
    MEMBER = 'MEMBER', _('Member')
    GUEST = 'GUEST', _('Guest')


class Porchlight(models.Model):
    """Porchlight device model with state, configuration, and owner."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text=_('Friendly name of the porchlight'))
    description = models.TextField(blank=True, help_text=_('Optional location or description'))
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_porchlights',
    )
    is_on = models.BooleanField(default=False)
    brightness = models.PositiveSmallIntegerField(default=100, help_text=_('Brightness percentage (0-100)'))
    color = models.CharField(max_length=30, default='#FFD54F', help_text=_('Hex or CSS color code'))
    status_message = models.CharField(max_length=255, blank=True, help_text=_('Optional custom status or notice'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('porchlight')
        verbose_name_plural = _('porchlights')

    def __str__(self):
        return f"{self.name} ({'ON' if self.is_on else 'OFF'})"

    def get_firebase_payload(self) -> dict:
        """Serialize porchlight state for Firebase sync."""
        return {
            'id': str(self.id),
            'name': self.name,
            'is_on': self.is_on,
            'brightness': self.brightness,
            'color': self.color,
            'status_message': self.status_message,
            'owner_id': self.owner_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else timezone.now().isoformat(),
        }

    def sync_to_firebase(self) -> bool:
        """Push current state to Firebase Firestore / Realtime DB."""
        return sync_porchlight_to_firebase(str(self.id), self.get_firebase_payload())

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Automatically sync state to Firebase on save
        self.sync_to_firebase()


class PorchlightMember(models.Model):
    """Membership granting an authenticated user specific access level to a Porchlight."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    porchlight = models.ForeignKey(
        Porchlight,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='porchlight_memberships',
    )
    role = models.CharField(
        max_length=20,
        choices=PorchlightRole.choices,
        default=PorchlightRole.MEMBER,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('porchlight', 'user')
        verbose_name = _('porchlight member')
        verbose_name_plural = _('porchlight members')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.porchlight.name} ({self.get_role_display()})"


def generate_invitation_code():
    return secrets.token_urlsafe(24)


class Invitation(models.Model):
    """Invitations granting authenticated or guest access to a Porchlight."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=64,
        unique=True,
        default=generate_invitation_code,
        db_index=True,
    )
    porchlight = models.ForeignKey(
        Porchlight,
        on_delete=models.CASCADE,
        related_name='invitations',
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_invitations',
    )
    invited_email = models.EmailField(
        blank=True,
        null=True,
        help_text=_('Optional target email address for recipient'),
    )
    role = models.CharField(
        max_length=20,
        choices=PorchlightRole.choices,
        default=PorchlightRole.GUEST,
    )
    is_guest = models.BooleanField(
        default=False,
        help_text=_('True if this invitation provides instant guest access without requiring an account'),
    )
    max_uses = models.PositiveIntegerField(
        default=1,
        help_text=_('Maximum number of uses allowed (0 for unlimited)'),
    )
    uses_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(blank=True, null=True, help_text=_('Expiration timestamp'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('invitation')
        verbose_name_plural = _('invitations')

    def __str__(self):
        return f"Invitation for {self.porchlight.name} ({self.role}) - Code: {self.code[:8]}..."

    @property
    def is_expired(self) -> bool:
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    @property
    def is_exhausted(self) -> bool:
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return True
        return False

    def is_valid(self) -> bool:
        """Check if invitation is currently valid and usable."""
        return self.is_active and not self.is_expired and not self.is_exhausted

    def record_usage(self):
        """Increment usage count and deactivate if max uses reached."""
        self.uses_count += 1
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            self.is_active = False
        self.save()


class GuestSession(models.Model):
    """Guest session established via a valid guest invitation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invitation = models.ForeignKey(
        Invitation,
        on_delete=models.CASCADE,
        related_name='guest_sessions',
    )
    guest_token = models.CharField(
        max_length=64,
        unique=True,
        default=secrets.token_urlsafe,
        db_index=True,
    )
    guest_name = models.CharField(max_length=100, default='Guest')
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('guest session')
        verbose_name_plural = _('guest sessions')

    def __str__(self):
        return f"Guest ({self.guest_name}) for {self.invitation.porchlight.name}"

    def is_valid(self) -> bool:
        """Check if guest session is valid (invitation must not be expired)."""
        return not self.invitation.is_expired
