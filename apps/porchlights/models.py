"""Models for Porchlights, Beacons, Memberships, Invitations, Permissions, and RSVPs."""
import secrets
import uuid
from django.conf import settings
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from sqids import Sqids
from apps.core.firebase import sync_porchlight_to_firebase

sqids = Sqids(min_length=8)


class NumericIdAllocator(models.Model):
    """Transactional counters used for stable, human-facing Sqid identifiers."""

    key = models.CharField(max_length=32, unique=True)
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = _('numeric ID allocator')
        verbose_name_plural = _('numeric ID allocators')


def allocate_numeric_id(key: str) -> int:
    """Allocate the next identifier while locking one shared counter row."""
    with transaction.atomic():
        allocator = NumericIdAllocator.objects.select_for_update().get(key=key)
        value = allocator.next_value
        allocator.next_value = value + 1
        allocator.save(update_fields=['next_value'])
        return value


class PorchlightRole(models.TextChoices):
    """Permission roles for Porchlight access."""
    OWNER = 'OWNER', _('Owner')
    ADMIN = 'ADMIN', _('Admin')
    MEMBER = 'MEMBER', _('Member')
    GUEST = 'GUEST', _('Guest')


class Porchlight(models.Model):
    """Porchlight / Beacon device model with state, configuration, and owner."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numeric_id = models.PositiveIntegerField(unique=True, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255, help_text=_('Friendly name of the porchlight or beacon'))
    type = models.CharField(max_length=100, default='virtual', help_text=_('Type of beacon/porchlight'))
    active_duration = models.IntegerField(default=4, help_text=_('Active duration in hours'))
    active_until = models.DateTimeField(null=True, blank=True, help_text=_('Active expiration timestamp'))
    location = models.JSONField(
        null=True,
        blank=True,
        help_text=_('Geocoordinates (e.g. {"latitude": float, "longitude": float}) or location data'),
    )
    description = models.TextField(blank=True, help_text=_('Optional location description'))
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

    def save(self, *args, **kwargs):
        if self.numeric_id is None:
            self.numeric_id = allocate_numeric_id('porchlight')
        super().save(*args, **kwargs)

    @property
    def sqid(self) -> str:
        """URL-safe Sqids encoding for the porchlight ID."""
        return sqids.encode([self.numeric_id])

    @classmethod
    def get_by_sqid(cls, sqid_str: str):
        """Find a porchlight by its URL-safe Sqids identifier."""
        if not sqid_str:
            return None
        numbers = sqids.decode(sqid_str)
        if not numbers:
            return None
        return cls.objects.filter(numeric_id=numbers[0]).first()

    @property
    def coordinates(self) -> dict | None:
        """Extract normalized geocoordinates {latitude: float, longitude: float} if available."""
        if not self.location:
            return None
        if isinstance(self.location, dict):
            lat = self.location.get('latitude') if 'latitude' in self.location else self.location.get('lat')
            lng = (
                self.location.get('longitude')
                if 'longitude' in self.location
                else (self.location.get('lng') if 'lng' in self.location else self.location.get('lon'))
            )
            if lat is not None and lng is not None:
                try:
                    return {'latitude': float(lat), 'longitude': float(lng)}
                except (ValueError, TypeError):
                    pass
            # GeoJSON Point format
            coords = self.location.get('coordinates')
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                try:
                    return {'longitude': float(coords[0]), 'latitude': float(coords[1])}
                except (ValueError, TypeError):
                    pass
        elif isinstance(self.location, str):
            parts = [p.strip() for p in self.location.split(',') if p.strip()]
            if len(parts) == 2:
                try:
                    return {'latitude': float(parts[0]), 'longitude': float(parts[1])}
                except (ValueError, TypeError):
                    pass
        return None

    def is_active(self) -> bool:
        """Check if beacon/porchlight is currently active based on active_until."""
        return bool(self.active_until and self.active_until > timezone.now())

    def get_firebase_payload(self) -> dict:
        """Serialize porchlight state for Firebase sync."""
        member_ids = list(self.memberships.values_list('user_id', flat=True))
        perm_user_ids = list(self.permission_grants.filter(user__isnull=False).values_list('user_id', flat=True))
        allowed_users = list(set([str(self.owner_id)] + [str(uid) for uid in member_ids] + [str(uid) for uid in perm_user_ids]))

        guest_tokens = list(
            self.invitations.filter(is_guest=True, guest_sessions__isnull=False)
            .values_list('guest_sessions__guest_token', flat=True)
            .distinct()
        )
        perm_guest_ids = list(self.permission_grants.filter(guest_id__isnull=False).values_list('guest_id', flat=True))
        allowed_guests = list(set([str(gt) for gt in guest_tokens if gt] + [str(gid) for gid in perm_guest_ids if gid]))

        return {
            'id': str(self.id),
            'name': self.name,
            'type': self.type,
            'active_duration': self.active_duration,
            'active_until': self.active_until.isoformat() if self.active_until else None,
            'is_active': self.is_active(),
            'location': self.location or None,
            'coordinates': self.coordinates,
            'is_on': self.is_on,
            'brightness': self.brightness,
            'color': self.color,
            'status_message': self.status_message,
            'owner_id': str(self.owner_id),
            'allowed_users': allowed_users,
            'allowed_guest_tokens': allowed_guests,
            'updated_at': self.updated_at.isoformat() if self.updated_at else timezone.now().isoformat(),
        }

    def sync_to_firebase(self) -> bool:
        """Push current state to Firebase Firestore / Realtime DB."""
        return sync_porchlight_to_firebase(str(self.id), self.get_firebase_payload())


# Alias Beacon to Porchlight for Laravel compatibility
Beacon = Porchlight


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
    """Invitations granting authenticated or guest access to a Porchlight/Beacon."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numeric_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
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
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='received_invitations',
    )
    invited_email = models.EmailField(
        blank=True,
        null=True,
        help_text=_('Optional target email address for recipient'),
    )
    guest_token = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(
        max_length=50,
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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('invitation')
        verbose_name_plural = _('invitations')

    def __str__(self):
        return f"Invitation for {self.porchlight.name} ({self.role}) - Code: {self.code[:8]}..."

    def get_role_display(self):
        labels = {
            PorchlightRole.OWNER: 'Owner',
            PorchlightRole.ADMIN: 'Admin',
            PorchlightRole.MEMBER: 'Member',
            PorchlightRole.GUEST: 'Guest',
        }
        return labels.get(self.role, self.role)

    def save(self, *args, **kwargs):
        if self.numeric_id is None:
            self.numeric_id = allocate_numeric_id('invitation')
        super().save(*args, **kwargs)

    @property
    def beacon(self):
        return self.porchlight

    @beacon.setter
    def beacon(self, value):
        self.porchlight = value

    @property
    def active_until(self):
        return self.expires_at

    @active_until.setter
    def active_until(self, value):
        self.expires_at = value

    @property
    def role_granted(self) -> str:
        role_map = {
            PorchlightRole.OWNER: 'owner',
            PorchlightRole.ADMIN: 'share',
            PorchlightRole.MEMBER: 'edit',
            PorchlightRole.GUEST: 'view',
        }
        return role_map.get(self.role, str(self.role).lower())

    @role_granted.setter
    def role_granted(self, value: str):
        if not value:
            self.role = PorchlightRole.GUEST
            return
        val = value.lower()
        if val == 'owner':
            self.role = PorchlightRole.OWNER
        elif val in ('edit', 'admin'):
            self.role = PorchlightRole.MEMBER
        elif val == 'share':
            self.role = PorchlightRole.ADMIN
        elif val == 'view':
            self.role = PorchlightRole.GUEST
        else:
            self.role = value

    @property
    def sqid(self) -> str:
        """URL-safe Sqids encoding for invitation ID, without a route prefix."""
        num = self.numeric_id
        if num is None:
            num = (self.id.int % 2147483647) if isinstance(self.id, uuid.UUID) else int(self.id)
        return sqids.encode([num])

    @classmethod
    def get_by_sqid(cls, sqid_str: str):
        """Find invitation by Sqid representation or invitation code."""
        if not sqid_str:
            return None
        numbers = sqids.decode(sqid_str)
        if numbers:
            inv = cls.objects.filter(numeric_id=numbers[0]).first()
            if inv:
                return inv
        return cls.objects.filter(code=sqid_str).first()

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
        if not self.is_valid():
            return False
        self.uses_count += 1
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            self.is_active = False
        self.save(update_fields=['uses_count', 'is_active', 'updated_at'])
        return True


class Permission(models.Model):
    """Permission grant matching Laravel structure."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    porchlight = models.ForeignKey(
        Porchlight,
        related_name='permission_grants',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='permissions',
        on_delete=models.CASCADE,
    )
    guest_id = models.CharField(max_length=255, null=True, blank=True)
    guest_name = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=50)  # 'owner', 'edit', 'share', 'view'
    is_close = models.BooleanField(default=False)
    from_invitation = models.ForeignKey(
        Invitation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='permissions_granted',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('permission')
        verbose_name_plural = _('permissions')

    def __str__(self):
        target = self.user.email if self.user else f"Guest ({self.guest_id})"
        return f"Permission ({self.role}) on {self.porchlight.name} for {target}"

    @property
    def beacon(self):
        return self.porchlight

    @beacon.setter
    def beacon(self, value):
        self.porchlight = value


def reset_brightness_without_close_permission(porchlight):
    """Restore full brightness when a porchlight has no close permissions left."""
    if not porchlight.permission_grants.filter(is_close=True).exists() and porchlight.brightness != 100:
        porchlight.brightness = 100
        porchlight.save(update_fields=['brightness', 'updated_at'])


@receiver(post_delete, sender=Permission)
def reset_brightness_after_permission_delete(sender, instance, **kwargs):
    reset_brightness_without_close_permission(instance.porchlight)


class Rsvp(models.Model):
    """A binary RSVP from one user or guest for a porchlight."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    porchlight = models.ForeignKey(
        Porchlight,
        related_name='rsvps',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name='rsvps',
        on_delete=models.CASCADE,
    )
    guest_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('RSVP')
        verbose_name_plural = _('RSVPs')
        constraints = [
            models.UniqueConstraint(
                fields=['porchlight', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_user_rsvp_per_porchlight',
            ),
            models.UniqueConstraint(
                fields=['porchlight', 'guest_id'],
                condition=models.Q(guest_id__isnull=False),
                name='unique_guest_rsvp_per_porchlight',
            ),
        ]

    def __str__(self):
        target = self.user.email if self.user else f"Guest ({self.guest_id})"
        return f"RSVP for {self.porchlight.name} by {target}"

    @property
    def beacon(self):
        return self.porchlight

    @beacon.setter
    def beacon(self, value):
        self.porchlight = value


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
