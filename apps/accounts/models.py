"""Custom User model implementing email-only authentication with AbstractBaseUser."""
import uuid
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Custom manager for User model where email is the unique identifier for auth."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError(_('The Email field must be set.'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom User model extending AbstractBaseUser with email-only authentication."""

    email = models.EmailField(
        _('email address'),
        unique=True,
        max_length=255,
        error_messages={
            'unique': _('A user with that email already exists.'),
        },
    )
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        """Return the user's full name or email if name is not set."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email

    @property
    def owned_beacons(self):
        """Alias for owned_porchlights to match Laravel beacon conventions."""
        return self.owned_porchlights


class FCMDeviceToken(models.Model):
    """FCM Device Registration Token for push notifications."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fcm_devices',
        null=True,
        blank=True,
    )
    guest_token = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text=_('Associated guest session token if unauthenticated guest'),
    )
    registration_token = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_('Firebase Cloud Messaging device token'),
    )
    device_id = models.CharField(max_length=255, blank=True, help_text=_('Unique hardware/app device ID'))
    device_type = models.CharField(max_length=50, blank=True, default='android', help_text=_('ios, android, web, etc.'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('FCM device token')
        verbose_name_plural = _('FCM device tokens')
        ordering = ['-updated_at']

    def __str__(self):
        target = self.user.email if self.user else f"Guest ({self.guest_token[:8] if self.guest_token else 'unknown'})"
        return f"FCM Token for {target} - {self.device_type}"


class WebPushSubscription(models.Model):
    """Standards-based browser Push API subscription for a user or guest."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='web_push_subscriptions',
        null=True,
        blank=True,
    )
    guest_token = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        target = self.user.email if self.user else f"Guest ({self.guest_token[:8] if self.guest_token else 'unknown'})"
        return f"Web Push subscription for {target}"
