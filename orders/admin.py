from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_number",
        "user",
        "restaurant",
        "order_type",
        "status",
        "quantity",
        "group_size",
        "booking_date",
        "booking_time",
        "total_amount",
        "created_at",
    ]

    list_filter = [
        "order_type",
        "status",
        "restaurant",
        "created_at",
    ]

    search_fields = [
        "order_number",
        "user__email",
        "user__full_name",
        "restaurant__name",
        "deal__title",
        "happy_hour__title",
    ]

    readonly_fields = [
        "order_number",
        "created_at",
        "updated_at",
        "confirmed_at",
        "rejected_at",
        "cancelled_at",
        "completed_at",
    ]

    actions = [
        "mark_confirmed",
        "mark_rejected",
        "mark_cancelled",
        "mark_completed",
    ]

    def mark_confirmed(self, request, queryset):
        for order in queryset.filter(status="pending"):
            order.mark_confirmed("Confirmed from admin panel")

    def mark_rejected(self, request, queryset):
        for order in queryset.filter(status="pending"):
            order.mark_rejected("Rejected from admin panel")

    def mark_cancelled(self, request, queryset):
        for order in queryset.exclude(status__in=["completed", "cancelled", "rejected"]):
            order.mark_cancelled()

    def mark_completed(self, request, queryset):
        for order in queryset.filter(status="confirmed"):
            order.mark_completed()