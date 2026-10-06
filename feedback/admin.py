from django.contrib import admin
from .models import PlatformFeedback


@admin.register(PlatformFeedback)
class PlatformFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'submitter_name',
        'rating',
        'ease_of_use',
        'usefulness',
        'smoothness',
        'category',
        'status',
        'is_liked',
        'created_at',
    ]
    list_filter = ['status', 'is_liked', 'rating', 'category', 'created_at']
    search_fields = [
        'user__full_name',
        'user__email',
        'user_name',
        'user_email',
        'comments',
        'difficulties',
        'confusing_aspects',
        'feature_requests',
        'admin_reply',
    ]
    readonly_fields = ['created_at', 'updated_at']
