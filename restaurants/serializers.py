from rest_framework import serializers
from django.contrib.auth import get_user_model
import json
from .models import Restaurant, RestaurantGallery, Review

User = get_user_model()


class GallerySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantGallery
        fields = [
            "id",
            "image",
            "image_url",
            "created_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")

        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)

        return None


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_avatar = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user_name",
            "user_avatar",
            "rating",
            "comment",
            "helpful_count",
            "restaurant_response",
            "restaurant_response_date",
            "created_at",
        ]

        read_only_fields = [
            "helpful_count",
            "restaurant_response",
            "restaurant_response_date",
        ]

    def get_user_avatar(self, obj):
        request = self.context.get("request")

        if obj.user.avatar and request:
            return request.build_absolute_uri(obj.user.avatar.url)

        return None


# class AddReviewSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Review
#         fields = [
#             "rating",
#             "comment",
#         ]


class RespondReviewSerializer(serializers.Serializer):
    response = serializers.CharField()


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone_number",
        ]


class RestaurantListSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    total_deals = serializers.SerializerMethodField()
    total_happy_hours = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            "id",
            "name",
            "address",
            "city",
            "categories",
            "operating_hours",
            "rating",
            "total_reviews",
            "logo_url",
            "status",
            "owner_name",
            "owner_email",
            "total_deals",
            "total_happy_hours",
            "created_at",
        ]

    def get_logo_url(self, obj):
        request = self.context.get("request")

        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)

        return None

    def get_total_deals(self, obj):
        return obj.deals.count()

    def get_total_happy_hours(self, obj):
        return obj.happy_hours.count()

class RestaurantDetailSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    gallery = GallerySerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    owner = OwnerSerializer(read_only=True)

    total_deals = serializers.SerializerMethodField()
    total_happy_hours = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            "id",
            "name",
            "description",
            "logo",
            "logo_url",
            "address",
            "city",
            "latitude",
            "longitude",
            "phone",
            "email",
            "categories",
            "operating_hours",
            "rating",
            "total_reviews",
            "status",
            "gallery",
            "reviews",
            "owner",
            "total_deals",
            "total_happy_hours",
            "created_at",
        ]

    def get_logo_url(self, obj):
        request = self.context.get("request")

        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)

        return None

    def get_total_deals(self, obj):
        return obj.deals.count()

    def get_total_happy_hours(self, obj):
        return obj.happy_hours.count()


class CreateRestaurantSerializer(serializers.Serializer):
    owner_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6)
    phone = serializers.CharField(required=False, allow_blank=True)

    restaurant_name = serializers.CharField()
    location = serializers.CharField()
    city = serializers.CharField(required=False, default="", allow_blank=True)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=True,
    )

    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=True,
    )
    
    categories = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    
    def validate(self, attrs):
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")

        if latitude is None or longitude is None:
            raise serializers.ValidationError(
                {
                    "location": "Please mark the restaurant location on the map."
                }
            )

        if not (-90 <= float(latitude) <= 90):
            raise serializers.ValidationError(
                {
                    "latitude": "Latitude must be between -90 and 90."
                }
            )

        if not (-180 <= float(longitude) <= 180):
            raise serializers.ValidationError(
                {
                    "longitude": "Longitude must be between -180 and 180."
                }
            )

        return attrs

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")

        return value


class UpdateRestaurantSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(required=False, allow_blank=True, write_only=True)
    owner_email = serializers.EmailField(required=False, write_only=True)
    owner_phone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=6)

    class Meta:
        model = Restaurant
        fields = [
            "name",
            "description",
            "logo",
            "address",
            "city",
            "latitude",
            "longitude",
            "phone",
            "email",
            "categories",
            "operating_hours",

            # owner update fields
            "owner_name",
            "owner_email",
            "owner_phone",
            "password",
        ]
        
    def validate_categories(self, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return value
    
    def validate_operating_hours(self, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid operating hours format")
        return value

    def validate_owner_email(self, value):
        restaurant = self.instance

        if restaurant and User.objects.filter(email=value).exclude(id=restaurant.owner.id).exists():
            raise serializers.ValidationError("Email already registered")

        return value

    def update(self, instance, validated_data):
        owner_name = validated_data.pop("owner_name", None)
        owner_email = validated_data.pop("owner_email", None)
        owner_phone = validated_data.pop("owner_phone", None)
        password = validated_data.pop("password", None)

        owner = instance.owner

        if owner_name is not None:
            owner.full_name = owner_name

        if owner_email is not None:
            owner.email = owner_email

        if owner_phone is not None:
            owner.phone_number = owner_phone

        if password:
            owner.set_password(password)

        owner.save()

        return super().update(instance, validated_data)
    
from django.utils.timesince import timesince
from django.utils import timezone


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_avatar_url = serializers.SerializerMethodField()
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    time_ago = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "restaurant",
            "restaurant_name",
            "user",
            "user_name",
            "user_email",
            "user_avatar_url",
            "rating",
            "comment",
            "helpful_count",
            "restaurant_response",
            "restaurant_response_date",
            "is_hidden",
            "is_flagged",
            "flagged_reason",
            "created_at",
            "time_ago",
            "can_edit",
        ]

        read_only_fields = [
            "id",
            "restaurant",
            "user",
            "helpful_count",
            "restaurant_response",
            "restaurant_response_date",
            "is_hidden",
            "is_flagged",
            "flagged_reason",
            "created_at",
        ]

    def get_user_name(self, obj):
        return obj.user.full_name or obj.user.email

    def get_user_avatar_url(self, obj):
        request = self.context.get("request")

        if obj.user.avatar and request:
            return request.build_absolute_uri(obj.user.avatar.url)

        if obj.user.avatar:
            return obj.user.avatar.url

        return None

    def get_time_ago(self, obj):
        from django.utils.timesince import timesince
        from django.utils import timezone

        return f"{timesince(obj.created_at, timezone.now())} ago"

    def get_can_edit(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        return bool(user and user.is_authenticated and obj.user_id == user.id)

class AddReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            "rating",
            "comment",
        ]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")

        return value


class EditReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            "rating",
            "comment",
        ]

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")

        return value


class ReviewResponseSerializer(serializers.Serializer):
    response = serializers.CharField(required=True, allow_blank=False)


class FlagReviewSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)


class AdminReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "rating",
            "comment",
            "user",
            "user_name",
            "user_email",
            "restaurant",
            "restaurant_name",
            "helpful_count",
            "restaurant_response",
            "restaurant_response_date",
            "is_hidden",
            "is_flagged",
            "flagged_reason",
            "created_at",
            "time_ago",
        ]

    def get_user_name(self, obj):
        return obj.user.full_name or obj.user.email

    def get_time_ago(self, obj):
        from django.utils.timesince import timesince
        from django.utils import timezone

        return f"{timesince(obj.created_at, timezone.now())} ago"