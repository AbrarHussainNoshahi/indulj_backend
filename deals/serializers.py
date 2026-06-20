from rest_framework import serializers
from .models import Deal, SavedDeal


# ─────────────────────────────────────────────
# ADMIN CREATE DEAL
# ─────────────────────────────────────────────
class AdminCreateDealSerializer(serializers.Serializer):
    restaurant_name = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    price = serializers.DecimalField(max_digits=8, decimal_places=2)

    food_type = serializers.ChoiceField(choices=Deal.FOOD_TYPE_CHOICES)
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES)

    has_time_slots = serializers.BooleanField(default=False)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)

    location_branch = serializers.CharField(required=False, allow_blank=True)
    discount_percentage = serializers.CharField(required=False, allow_blank=True)

    image = serializers.ImageField(required=False, allow_null=True)

    is_hot_deal = serializers.BooleanField(default=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    status = serializers.ChoiceField(
        choices=Deal.STATUS_CHOICES,
        required=False,
        default="active",
    )


# ─────────────────────────────────────────────
# DEAL LIST (PUBLIC + ADMIN + RESTAURANT)
# ─────────────────────────────────────────────
class DealListSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_city = serializers.CharField(source="restaurant.city", read_only=True)

    submitted_by_name = serializers.CharField(
        source="submitted_by.full_name",
        read_only=True,
    )

    restaurant_categories = serializers.SerializerMethodField()

    image_url = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    latitude = serializers.FloatField(source="restaurant.latitude", read_only=True)
    longitude = serializers.FloatField(source="restaurant.longitude", read_only=True)

    class Meta:
        model = Deal
        fields = [
            "id",
            "title",
            "description",
            "price",
            "food_type",
            "day_of_week",
            "start_time",
            "end_time",
            "has_time_slots",
            "location_branch",
            "status",
            "rejection_reason",
            "discount_percentage",
            "image_url",
            "views_count",
            "redemptions_count",
            "is_hot_deal",
            "expires_at",
            "restaurant",
            "restaurant_name",
            "restaurant_city",
            "restaurant_categories",
            "submitted_by_name",
            "created_by_role",
            "is_saved",
            "latitude",
            "longitude",
            "created_at",
        ]

    # ─────────────────────────────
    # IMAGE URL SAFE
    # ─────────────────────────────
    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    # ─────────────────────────────
    # SAFE CATEGORIES (FIXED)
    # ─────────────────────────────
    def get_restaurant_categories(self, obj):
        try:
            return obj.restaurant.categories or []
        except Exception:
            return []

    # ─────────────────────────────
    # SAVE STATUS (FIXED PROPERLY)
    # ─────────────────────────────
    def get_is_saved(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return SavedDeal.objects.filter(
            user=request.user,
            deal=obj
        ).exists()


# ─────────────────────────────────────────────
# DEAL DETAIL (same as list)
# ─────────────────────────────────────────────
class DealDetailSerializer(DealListSerializer):
    pass


# ─────────────────────────────────────────────
# USER SUBMIT DEAL
# ─────────────────────────────────────────────
class SubmitDealSerializer(serializers.Serializer):
    restaurant_name = serializers.CharField()
    location_branch = serializers.CharField()

    price = serializers.DecimalField(max_digits=8, decimal_places=2)

    food_type = serializers.ChoiceField(choices=Deal.FOOD_TYPE_CHOICES)
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES)

    has_time_slots = serializers.BooleanField(default=False)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)

    description = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True, default="")

    image = serializers.ImageField(required=False, allow_null=True)


# ─────────────────────────────────────────────
# CREATE DEAL (MODEL)
# ─────────────────────────────────────────────
class CreateDealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deal
        fields = [
            "title",
            "description",
            "price",
            "food_type",
            "day_of_week",
            "start_time",
            "end_time",
            "has_time_slots",
            "location_branch",
            "discount_percentage",
            "image",
            "is_hot_deal",
            "expires_at",
        ]


# ─────────────────────────────────────────────
# REJECT DEAL
# ─────────────────────────────────────────────
class RejectDealSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField()


# ─────────────────────────────────────────────
# SAVED DEALS
# ─────────────────────────────────────────────
class SavedDealSerializer(serializers.ModelSerializer):
    deal = DealListSerializer(read_only=True)

    class Meta:
        model = SavedDeal
        fields = ["id", "deal", "saved_at"]