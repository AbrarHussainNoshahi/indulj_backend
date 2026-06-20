from django.contrib import admin

from .models import Deal, SavedDeal


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "restaurant",
        "food_type",
        "price",
        "status",
        "created_by_role",
        "is_hot_deal",
        "views_count",
        "redemptions_count",
        "created_at",
    ]

    list_filter = [
        "status",
        "food_type",
        "day_of_week",
        "created_by_role",
        "is_hot_deal",
    ]

    search_fields = [
        "title",
        "restaurant__name",
        "submitted_by__email",
    ]

    ordering = ["-created_at"]

    actions = [
        "approve_deals",
        "reject_deals",
    ]

    def approve_deals(self, request, queryset):
        queryset.update(status="active", rejection_reason="")

    approve_deals.short_description = "Approve selected deals"

    def reject_deals(self, request, queryset):
        queryset.update(status="rejected")

    reject_deals.short_description = "Reject selected deals"


@admin.register(SavedDeal)
class SavedDealAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "deal",
        "saved_at",
    ]

    search_fields = [
        "user__email",
        "deal__title",
    ]

    ordering = ["-saved_at"]