from django.contrib import admin

from .models import Restaurant, RestaurantGallery, Review


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "owner",
        "city",
        "status",
        "rating",
        "total_reviews",
        "created_at",
    ]
    list_filter = [
        "status",
        "city",
    ]
    search_fields = [
        "name",
        "owner__email",
        "city",
    ]
    ordering = ["-created_at"]


@admin.register(RestaurantGallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = [
        "restaurant",
        "created_at",
    ]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "restaurant",
        "user",
        "rating",
        "is_hidden",
        "is_flagged",
        "created_at",
    ]

    list_filter = [
        "rating",
        "is_hidden",
        "is_flagged",
        "created_at",
    ]

    search_fields = [
        "restaurant__name",
        "user__email",
        "user__full_name",
        "comment",
    ]

    actions = [
        "hide_reviews",
        "unhide_reviews",
        "clear_flags",
    ]

    def hide_reviews(self, request, queryset):
        queryset.update(is_hidden=True)

        for review in queryset.select_related("restaurant"):
            review.restaurant.update_rating()

    hide_reviews.short_description = "Hide selected reviews"

    def unhide_reviews(self, request, queryset):
        queryset.update(is_hidden=False)

        for review in queryset.select_related("restaurant"):
            review.restaurant.update_rating()

    unhide_reviews.short_description = "Unhide selected reviews"

    def clear_flags(self, request, queryset):
        queryset.update(is_flagged=False, flagged_reason="")

    clear_flags.short_description = "Clear selected flags"