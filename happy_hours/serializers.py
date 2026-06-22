from rest_framework import serializers
from .models import HappyHour


class HappyHourListSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_city = serializers.CharField(source="restaurant.city", read_only=True)
    restaurant_address = serializers.CharField(source="restaurant.address", read_only=True)
    restaurant_phone = serializers.CharField(source="restaurant.phone", read_only=True)
    restaurant_rating = serializers.DecimalField(
        source="restaurant.rating",
        max_digits=3,
        decimal_places=1,
        read_only=True,
    )
    restaurant_reviews = serializers.IntegerField(
        source="restaurant.total_reviews",
        read_only=True,
    )
    restaurant_categories = serializers.JSONField(
        source="restaurant.categories",
        read_only=True,
    )

    submitted_by_name = serializers.CharField(
        source="submitted_by.full_name",
        read_only=True,
    )

    latitude = serializers.FloatField(source="restaurant.latitude", read_only=True)
    longitude = serializers.FloatField(source="restaurant.longitude", read_only=True)

    image_url = serializers.SerializerMethodField()
    time_slots = serializers.SerializerMethodField()

    class Meta:
        model = HappyHour
        fields = [
            "id",
            "title",
            "description",
            "event_type",
            "group_size",
            "start_time",
            "end_time",
            "time_slots",
            "date",
            "days_of_week",
            "vibe",
            "location",
            "phone_number",
            "is_public",
            "discount_offer",
            "specials",
            "participants_count",
            "status",
            "rejection_reason",
            "restaurant_response",
            "views_count",
            "is_featured",
            "created_by_role",
            "restaurant",
            "restaurant_name",
            "restaurant_city",
            "restaurant_address",
            "restaurant_phone",
            "restaurant_rating",
            "restaurant_reviews",
            "restaurant_categories",
            "submitted_by_name",
            "latitude",
            "longitude",
            "image_url",
            "created_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_time_slots(self, obj):
        if obj.start_time and obj.end_time:
            return f"{obj.start_time.strftime('%I:%M %p')} - {obj.end_time.strftime('%I:%M %p')}"
        return None


class HappyHourDetailSerializer(HappyHourListSerializer):
    class Meta(HappyHourListSerializer.Meta):
        pass


class PlanHappyHourSerializer(serializers.Serializer):
    restaurant = serializers.IntegerField()

    title = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
    )

    date = serializers.DateField(
        required=True,
        allow_null=False,
    )

    event_type = serializers.ChoiceField(
        choices=HappyHour.EVENT_TYPE_CHOICES
    )

    group_size = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )

    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    vibe = serializers.ChoiceField(
        choices=HappyHour.VIBE_CHOICES
    )

    location = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    is_public = serializers.BooleanField(default=True)

    image = serializers.ImageField(
        required=False,
        allow_null=True,
    )

    specials = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {
                    "end_time": "End time must be after start time."
                }
            )

        return attrs

class CreateHappyHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = HappyHour
        fields = [
            "title",
            "description",
            "event_type",
            "group_size",
            "start_time",
            "end_time",
            "date",
            "days_of_week",
            "vibe",
            "location",
            "phone_number",
            "is_public",
            "discount_offer",
            "specials",
            "image",
            "is_featured",
            "status",
        ]

    def validate_status(self, value):
        allowed = ["active", "upcoming", "draft", "cancelled"]
        if value not in allowed:
            raise serializers.ValidationError(
                "Restaurant can only set status as active, upcoming, draft, or cancelled."
            )
        return value


class RestaurantResponseSerializer(serializers.Serializer):
    response = serializers.CharField(required=False, allow_blank=True)


class RejectHappyHourSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField()


class AdminUpdateHappyHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = HappyHour
        fields = [
            "title",
            "description",
            "event_type",
            "group_size",
            "start_time",
            "end_time",
            "date",
            "days_of_week",
            "vibe",
            "location",
            "phone_number",
            "is_public",
            "discount_offer",
            "specials",
            "image",
            "participants_count",
            "status",
            "rejection_reason",
            "restaurant_response",
            "is_featured",
        ]