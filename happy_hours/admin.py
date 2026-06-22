from django.contrib import admin
from .models import HappyHour


@admin.register(HappyHour)
class HappyHourAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "restaurant",
        "event_type",
        "vibe",
        "group_size",
        "status",
        "created_by_role",
        "is_featured",
        "created_at",
    ]

    list_filter = [
        "status",
        "event_type",
        "vibe",
        "created_by_role",
        "is_featured",
    ]

    search_fields = [
        "title",
        "restaurant__name",
        "submitted_by__email",
    ]

    ordering = ["-created_at"]

    actions = [
        "accept_all",
        "activate_all",
        "reject_all",
        "cancel_all",
    ]

    def accept_all(self, request, queryset):
        queryset.update(status="upcoming", rejection_reason="")

    accept_all.short_description = "Accept selected happy hours"

    def activate_all(self, request, queryset):
        queryset.update(status="active", rejection_reason="")

    activate_all.short_description = "Activate selected happy hours"

    def reject_all(self, request, queryset):
        queryset.update(status="rejected")

    reject_all.short_description = "Reject selected happy hours"

    def cancel_all(self, request, queryset):
        queryset.update(status="cancelled")

    cancel_all.short_description = "Cancel selected happy hours"