from rest_framework import serializers
from .models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "inquiry_type",
            "subject",
            "message",
            "is_read",
            "email_sent",
            "created_at",
        ]
        read_only_fields = ["id", "is_read", "email_sent", "created_at"]

    def validate_name(self, value):
        val = (value or "").strip()
        if not val or len(val) < 2:
            raise serializers.ValidationError("Please provide a valid name (at least 2 characters).")
        return val

    def validate_email(self, value):
        val = (value or "").strip().lower()
        if not val:
            raise serializers.ValidationError("Email is required.")
        return val

    def validate_subject(self, value):
        val = (value or "").strip()
        if not val or len(val) < 2:
            raise serializers.ValidationError("Please enter a subject (at least 2 characters).")
        return val

    def validate_message(self, value):
        val = (value or "").strip()
        if not val or len(val) < 5:
            raise serializers.ValidationError("Message must be at least 5 characters long.")
        return val
