"""Admin interface configuration for Porchlights, Members, Invitations, Permissions, and RSVPs."""
from django.contrib import admin
from .models import GuestSession, Invitation, Permission, Porchlight, PorchlightMember, Rsvp


class PorchlightMemberInline(admin.TabularInline):
    model = PorchlightMember
    extra = 1


class InvitationInline(admin.TabularInline):
    model = Invitation
    extra = 0
    fields = ('code', 'numeric_id', 'invited_email', 'role', 'is_guest', 'max_uses', 'uses_count', 'is_active', 'expires_at')
    readonly_fields = ('code', 'numeric_id', 'uses_count')


class PermissionInline(admin.TabularInline):
    model = Permission
    extra = 0


class RsvpInline(admin.TabularInline):
    model = Rsvp
    extra = 0


@admin.register(Porchlight)
class PorchlightAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'owner', 'is_on', 'is_active', 'active_until', 'brightness', 'color', 'created_at')
    list_filter = ('is_on', 'type', 'created_at')
    search_fields = ('name', 'description', 'location', 'owner__email')
    inlines = [PorchlightMemberInline, InvitationInline, PermissionInline, RsvpInline]


@admin.register(PorchlightMember)
class PorchlightMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'porchlight', 'role', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__email', 'porchlight__name')


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'sqid',
        'numeric_id',
        'porchlight',
        'invited_by',
        'invited_email',
        'role',
        'is_guest',
        'uses_count',
        'max_uses',
        'is_active',
        'expires_at',
    )
    list_filter = ('role', 'is_guest', 'is_active')
    search_fields = ('code', 'invited_email', 'porchlight__name', 'invited_by__email')


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('porchlight', 'user', 'guest_id', 'role', 'from_invitation', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__email', 'guest_id', 'porchlight__name')


@admin.register(Rsvp)
class RsvpAdmin(admin.ModelAdmin):
    list_display = ('porchlight', 'user', 'guest_id', 'type', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('user__email', 'guest_id', 'porchlight__name')


@admin.register(GuestSession)
class GuestSessionAdmin(admin.ModelAdmin):
    list_display = ('guest_name', 'guest_token', 'invitation', 'created_at', 'last_active_at')
    search_fields = ('guest_name', 'guest_token', 'invitation__code')
