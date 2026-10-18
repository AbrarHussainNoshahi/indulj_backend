from rest_framework import serializers
from .models import HappyHour, HappyHourRSVP


class HappyHourRSVPSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = HappyHourRSVP
        fields = [
            "id",
            "happy_hour",
            "user",
            "user_name",
            "name",
            "avatar",
            "avatar_url",
            "status",
            "attendee_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "happy_hour", "user", "created_at", "updated_at"]

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar and hasattr(obj.avatar, "url"):
            try:
                if request:
                    return request.build_absolute_uri(obj.avatar.url)
                return obj.avatar.url
            except Exception:
                pass
        if obj.user and getattr(obj.user, "avatar", None):
            try:
                if request:
                    return request.build_absolute_uri(obj.user.avatar.url)
                return obj.user.avatar.url
            except Exception:
                pass
        return None


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
    restaurant_is_registered = serializers.SerializerMethodField()
    is_active_now = serializers.SerializerMethodField()
    is_deal = serializers.BooleanField(read_only=True)
    deal_id = serializers.IntegerField(source="deal.id", read_only=True, allow_null=True)

    confirmed_attendees_count = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    spots_remaining = serializers.IntegerField(read_only=True, allow_null=True)
    rsvp_summary = serializers.JSONField(read_only=True)

    def get_is_active_now(self, obj):
        try:
            return obj.is_live_now()
        except Exception:
            return False

    def get_restaurant_is_registered(self, obj):
        return bool(obj.restaurant and obj.restaurant.owner_id is not None)

    class Meta:
        model = HappyHour
        fields = [
            "id",
            "is_deal",
            "deal_id",
            "is_active_now",
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
            "restaurant_is_registered",
            "submitted_by_name",
            "latitude",
            "longitude",
            "image_url",
            "confirmed_attendees_count",
            "is_full",
            "spots_remaining",
            "rsvp_summary",
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
    rsvps = serializers.SerializerMethodField()

    class Meta(HappyHourListSerializer.Meta):
        fields = HappyHourListSerializer.Meta.fields + ["rsvps"]

    def get_rsvps(self, obj):
        if not getattr(obj, "is_deal", False):
            return []
        qs = obj.rsvps.all()
        return HappyHourRSVPSerializer(qs, many=True, context=self.context).data



class PlanHappyHourSerializer(serializers.Serializer):
    restaurant = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    restaurant_name = serializers.CharField(required=False, allow_blank=True, default="")

    title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        default="",
    )

    date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    event_type = serializers.CharField(
        required=False,
        default="casual",
    )

    group_size = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
    )

    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)

    vibe = serializers.CharField(
        required=False,
        default="casual",
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
    also_add_to_deals = serializers.BooleanField(required=False, default=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)

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