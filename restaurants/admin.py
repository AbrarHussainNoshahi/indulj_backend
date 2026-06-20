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
        "restaurant",
        "user",
        "rating",
        "helpful_count",
        "created_at",
    ]
    list_filter = [
        "rating",
    ]
    search_fields = [
        "restaurant__name",
        "user__email",
    ]