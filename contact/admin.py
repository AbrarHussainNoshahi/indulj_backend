from django.contrib import admin
from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "email",
        "inquiry_type",
        "subject",
        "is_read",
        "email_sent",
        "created_at",
    )
    list_filter = (
        "inquiry_type",
        "is_read",
        "email_sent",
        "created_at",
    )
    search_fields = (
        "name",
        "email",
        "subject",
        "message",
        "phone",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "email_sent",
    )
    ordering = ("-created_at",)
