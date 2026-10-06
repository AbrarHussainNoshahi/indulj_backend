from rest_framework import serializers
from .models import PlatformFeedback
from accounts.models import User


class SubmitterUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'display_username',
            'role',
            'avatar_url',
        ]

    def get_avatar_url(self, obj):
        if obj.avatar:
            try:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.avatar.url)
                return obj.avatar.url
            except Exception:
                return None
        return None


class RepliedByUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'admin_type',
            'designation',
            'avatar_url',
        ]

    def get_avatar_url(self, obj):
        if obj.avatar:
            try:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.avatar.url)
                return obj.avatar.url
            except Exception:
                return None
        return None


class PlatformFeedbackSerializer(serializers.ModelSerializer):
    user_details = SubmitterUserSerializer(source='user', read_only=True)
    replied_by_details = RepliedByUserSerializer(source='replied_by', read_only=True)
    submitter_name = serializers.ReadOnlyField()
    submitter_email = serializers.ReadOnlyField()

    class Meta:
        model = PlatformFeedback
        fields = [
            'id',
            'user',
            'user_details',
            'user_name',
            'user_email',
            'submitter_name',
            'submitter_email',
            'rating',
            'ease_of_use',
            'usefulness',
            'smoothness',
            'difficulties',
            'confusing_aspects',
            'feature_requests',
            'comments',
            'category',
            'is_liked',
            'status',
            'admin_reply',
            'replied_at',
            'replied_by',
            'replied_by_details',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'is_liked',
            'admin_reply',
            'replied_at',
            'replied_by',
            'created_at',
            'updated_at',
        ]


class PlatformFeedbackCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformFeedback
        fields = [
            'rating',
            'ease_of_use',
            'usefulness',
            'smoothness',
            'difficulties',
            'confusing_aspects',
            'feature_requests',
            'comments',
            'category',
            'user_name',
            'user_email',
        ]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate_ease_of_use(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Ease of use rating must be between 1 and 5.")
        return value

    def validate_usefulness(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Usefulness rating must be between 1 and 5.")
        return value

    def validate_smoothness(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Smoothness rating must be between 1 and 5.")
        return value


class PlatformFeedbackReplySerializer(serializers.Serializer):
    reply = serializers.CharField(required=True, allow_blank=False, min_length=2)
    status = serializers.ChoiceField(
        choices=PlatformFeedback.STATUS_CHOICES,
        required=False,
        default='reviewed'
    )


class PlatformFeedbackStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=PlatformFeedback.STATUS_CHOICES,
        required=True
    )
