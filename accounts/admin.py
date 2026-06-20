from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPVerification, NotificationPreference, UserSession


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ['email', 'full_name', 'role', 'is_email_verified', 'is_suspended']
    list_filter   = ['role', 'is_email_verified', 'is_suspended']
    search_fields = ['email', 'full_name']
    ordering      = ['-date_joined']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('full_name', 'phone_number', 'avatar', 'location')}),
        ('Role & Status', {'fields': ('role', 'is_email_verified', 'is_suspended')}),
        ('Rewards', {'fields': ('points', 'referral_code')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'full_name', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(OTPVerification)
class OTPAdmin(admin.ModelAdmin):
    list_display = ['user', 'otp', 'created_at', 'expires_at', 'is_used']


@admin.register(NotificationPreference)
class NotificationPrefAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_deals', 'email_happy_hours', 'sms_deals']


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'device_info', 'location', 'last_active']