"""Admin interface configuration for Porchlights, Members, and Invitations."""
from django.contrib import admin
from .models import GuestSession, Invitation, Porchlight, PorchlightMember


class PorchlightMemberInline(admin.TabularInline):
    model = PorchlightMember
    extra = 1


class InvitationInline(admin.TabularInline):
    model = Invitation
    extra = 0
    fields = ('code', 'invited_email', 'role', 'is_guest', 'max_uses', 'uses_count', 'is_active', 'expires_at')
    readonly_fields = ('code', 'uses_count')


@admin.register(Porchlight)
class PorchlightAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_on', 'brightness', 'color', 'created_at')
    list_filter = ('is_on', 'created_at')
    search_fields = ('name', 'description', 'owner__email')
    inlines = [PorchlightMemberInline, InvitationInline]


@admin.register(PorchlightMember)
class PorchlightMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'porchlight', 'role', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__email', 'porchlight__name')


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        'code',
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


@admin.register(GuestSession)
class GuestSessionAdmin(admin.ModelAdmin):
    list_display = ('guest_name', 'guest_token', 'invitation', 'created_at', 'last_active_at')
    search_fields = ('guest_name', 'guest_token', 'invitation__code')
