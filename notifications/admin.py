from django.contrib import admin
from .models import Notification, DeviceToken

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'title', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('user__email', 'title', 'message')
    ordering = ('-created_at',)

@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'platform', 'is_active', 'updated_at', 'created_at')
    list_filter = ('platform', 'is_active', 'created_at')
    search_fields = ('user__email', 'registration_id')
    ordering = ('-updated_at',)
