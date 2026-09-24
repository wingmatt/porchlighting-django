"""Admin configuration for custom User model."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import FCMDeviceToken, User


@admin.register(FCMDeviceToken)
class FCMDeviceTokenAdmin(admin.ModelAdmin):
    """Admin configuration for FCMDeviceToken."""

    list_display = ('registration_token', 'user', 'guest_token', 'device_type', 'is_active', 'updated_at')
    list_filter = ('is_active', 'device_type', 'created_at')
    search_fields = ('registration_token', 'device_id', 'user__email', 'guest_token')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for email-only User model."""

    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'is_staff', 'is_active'),
            },
        ),
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
