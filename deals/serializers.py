from rest_framework import serializers
from .models import Deal, SavedDeal


def normalize_food_type_input(raw):
    if not raw:
        return "other"
    if isinstance(raw, list):
        items = [str(x).strip().replace("_", " ") for x in raw if str(x).strip()]
        return ", ".join(items) if items else "other"
    if isinstance(raw, str):
        trimmed = raw.strip()
        if trimmed.startswith("[") and trimmed.endswith("]"):
            try:
                import json
                parsed = json.loads(trimmed)
                if isinstance(parsed, list):
                    items = [str(x).strip().replace("_", " ") for x in parsed if str(x).strip()]
                    return ", ".join(items) if items else "other"
            except Exception:
                pass
        return trimmed or "other"
    return str(raw)


def normalize_days_of_week_input(raw):
    if not raw:
        return []
    import json
    result = []
    def _extract(val):
        if not val:
            return
        if isinstance(val, (list, tuple)):
            for item in val:
                _extract(item)
        elif isinstance(val, str):
            trimmed = val.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                try:
                    parsed = json.loads(trimmed)
                    _extract(parsed)
                    return
                except Exception:
                    pass
            for part in trimmed.split(","):
                cleaned = part.strip().strip('"').strip("'").lower()
                if cleaned:
                    result.append(cleaned)
    _extract(raw)
    valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    cleaned_result = []
    for d in result:
        if d in valid_days and d not in cleaned_result:
            cleaned_result.append(d)
        elif d in {"everyday", "daily", "all"}:
            for vd in valid_days:
                if vd not in cleaned_result:
                    cleaned_result.append(vd)
        elif d == "weekdays":
            for vd in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
                if vd not in cleaned_result:
                    cleaned_result.append(vd)
        elif d == "weekends":
            for vd in ["saturday", "sunday"]:
                if vd not in cleaned_result:
                    cleaned_result.append(vd)
    return cleaned_result


def compute_single_day_of_week(days_list):
    if not days_list:
        return "everyday"
    if len(days_list) == 7:
        return "everyday"
    if len(days_list) == 5 and all(d in days_list for d in ["monday", "tuesday", "wednesday", "thursday", "friday"]):
        return "weekdays"
    if len(days_list) == 2 and all(d in days_list for d in ["saturday", "sunday"]):
        return "weekends"
    return days_list[0]


class DaysOfWeekField(serializers.Field):
    """
    Custom serializer field that accepts days_of_week in any format
    (JSON string, list, comma-separated string, or single string)
    and avoids QueryDict list stringification issues.
    """
    def get_value(self, dictionary):
        if self.field_name in dictionary:
            return dictionary.get(self.field_name)
        return serializers.empty

    def to_internal_value(self, data):
        return normalize_days_of_week_input(data)

    def to_representation(self, value):
        return normalize_days_of_week_input(value)


# ─────────────────────────────────────────────
# ADMIN CREATE DEAL
# ─────────────────────────────────────────────
class AdminCreateDealSerializer(serializers.Serializer):
    restaurant_name = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    price = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)

    food_type = serializers.CharField(required=False, allow_blank=True, default="other")
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES, required=False, default="everyday")

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

    post_to_happy_hour = serializers.BooleanField(required=False, default=False)
    hh_date = serializers.DateField(required=False, allow_null=True)
    hh_group_size = serializers.IntegerField(required=False, default=1)
    hh_event_type = serializers.CharField(required=False, default="casual")
    hh_vibe = serializers.CharField(required=False, default="casual")
    hh_discount_offer = serializers.CharField(required=False, allow_blank=True, default="")
    days_of_week = DaysOfWeekField(required=False, default=list)
    hh_days_of_week = serializers.CharField(required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        if hasattr(data, "dict"):
            data = data.dict()
        elif hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data)

        raw_food = data.get("food_type") if "food_type" in data else data.get("food_types")
        if raw_food is not None:
            data["food_type"] = normalize_food_type_input(raw_food)
        raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
        norm_days = normalize_days_of_week_input(raw_days)
        if norm_days:
            data["days_of_week"] = norm_days
            data["day_of_week"] = compute_single_day_of_week(norm_days)
        elif "day_of_week" in data:
            day_norm = normalize_days_of_week_input(data["day_of_week"])
            data["day_of_week"] = compute_single_day_of_week(day_norm)
            data["days_of_week"] = day_norm or [data["day_of_week"]]
        return super().to_internal_value(data)

    def validate(self, attrs):
        price = attrs.get("price")
        discount = attrs.get("discount_percentage") or attrs.get("discount_offer") or attrs.get("hh_discount_offer")
        if price is None and not str(discount or "").strip():
            raise serializers.ValidationError({
                "price": "Either a price or a discount offer must be provided."
            })
        return attrs


# ─────────────────────────────────────────────
# ADMIN UPDATE DEAL
# ─────────────────────────────────────────────
class AdminUpdateDealSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    food_type = serializers.CharField(required=False, allow_blank=True, default="other")
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES, required=False)
    days_of_week = DaysOfWeekField(required=False)

    class Meta:
        model = Deal
        fields = [
            "title",
            "description",
            "price",
            "food_type",
            "day_of_week",
            "days_of_week",
            "start_time",
            "end_time",
            "has_time_slots",
            "location_branch",
            "discount_percentage",
            "image",
            "is_hot_deal",
            "expires_at",
            "status",
            "rejection_reason",
        ]

    def to_internal_value(self, data):
        if hasattr(data, "dict"):
            data = data.dict()
        elif hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data)

        raw_food = data.get("food_type") if "food_type" in data else data.get("food_types")
        if raw_food is not None:
            data["food_type"] = normalize_food_type_input(raw_food)
        if "image" in data and isinstance(data["image"], str):
            data.pop("image", None)
        raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
        if raw_days is not None:
            norm_days = normalize_days_of_week_input(raw_days)
            data["days_of_week"] = norm_days
            data["day_of_week"] = compute_single_day_of_week(norm_days)
        elif "day_of_week" in data:
            day_norm = normalize_days_of_week_input(data["day_of_week"])
            data["day_of_week"] = compute_single_day_of_week(day_norm)
        return super().to_internal_value(data)

    def validate(self, attrs):
        price = attrs.get("price") if "price" in attrs else getattr(self.instance, "price", None)
        discount = attrs.get("discount_percentage") if "discount_percentage" in attrs else getattr(self.instance, "discount_percentage", "")
        if price is None and not str(discount or "").strip():
            raise serializers.ValidationError({
                "price": "Either a price or a discount offer must be provided."
            })
        return attrs


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
    food_types = serializers.SerializerMethodField()

    image_url = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    latitude = serializers.FloatField(source="restaurant.latitude", read_only=True)
    longitude = serializers.FloatField(source="restaurant.longitude", read_only=True)
    restaurant_phone = serializers.CharField(source="restaurant.phone", read_only=True, default="")
    restaurant_address = serializers.CharField(source="restaurant.address", read_only=True, default="")
    restaurant_rating = serializers.FloatField(source="restaurant.rating", read_only=True, default=0.0)
    restaurant_reviews = serializers.IntegerField(source="restaurant.total_reviews", read_only=True, default=0)
    restaurant_is_registered = serializers.SerializerMethodField()

    duplicate_of_id = serializers.IntegerField(source="duplicate_of.id", read_only=True)
    duplicate_of_title = serializers.CharField(source="duplicate_of.title", read_only=True)
    duplicate_of = serializers.SerializerMethodField()
    days_of_week = serializers.SerializerMethodField()
    discount_offer = serializers.CharField(source="discount_percentage", read_only=True)

    def get_days_of_week(self, obj):
        raw = getattr(obj, "days_of_week", None)
        cleaned = normalize_days_of_week_input(raw)
        if cleaned:
            return cleaned
        linked_hh = getattr(obj, "linked_happy_hours", None)
        if linked_hh:
            first_hh = linked_hh.first()
            if first_hh and first_hh.days_of_week:
                hh_clean = normalize_days_of_week_input(first_hh.days_of_week)
                if hh_clean:
                    return hh_clean
        day = (obj.day_of_week or "").lower().strip()
        cleaned_day = normalize_days_of_week_input(day)
        if cleaned_day:
            return cleaned_day
        return ["everyday"]

    def get_restaurant_is_registered(self, obj):
        return bool(obj.restaurant and obj.restaurant.owner_id is not None)

    def get_duplicate_of(self, obj):
        if not obj.duplicate_of:
            return None
        d = obj.duplicate_of
        return {
            "id": d.id,
            "title": d.title,
            "price": str(d.price) if d.price is not None else None,
            "discount_percentage": d.discount_percentage,
            "discount_offer": d.discount_percentage,
            "day_of_week": d.day_of_week,
            "status": d.status,
            "created_at": d.created_at,
            "submitted_by_name": d.submitted_by.full_name if d.submitted_by else "Restaurant/Admin",
            "description": d.description,
        }

    class Meta:
        model = Deal
        fields = [
            "id",
            "title",
            "description",
            "price",
            "food_type",
            "food_types",
            "day_of_week",
            "days_of_week",
            "start_time",
            "end_time",
            "has_time_slots",
            "location_branch",
            "status",
            "rejection_reason",
            "discount_percentage",
            "discount_offer",
            "image_url",
            "views_count",
            "redemptions_count",
            "is_hot_deal",
            "expires_at",
            "restaurant",
            "restaurant_name",
            "restaurant_city",
            "restaurant_phone",
            "restaurant_address",
            "restaurant_rating",
            "restaurant_reviews",
            "restaurant_categories",
            "restaurant_is_registered",
            "submitted_by_name",
            "created_by_role",
            "is_saved",
            "latitude",
            "longitude",
            "is_potential_duplicate",
            "duplicate_of_id",
            "duplicate_of_title",
            "duplicate_of",
            "duplicate_score",
            "duplicate_reasons",
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

    def get_food_types(self, obj):
        val = obj.food_type
        if not val:
            return []
        if isinstance(val, list):
            return [str(x).strip().replace("_", " ") for x in val if str(x).strip()]
        if isinstance(val, str):
            val_strip = val.strip()
            if val_strip.startswith("[") and val_strip.endswith("]"):
                try:
                    import json
                    parsed = json.loads(val_strip)
                    if isinstance(parsed, list):
                        return [str(x).strip().replace("_", " ") for x in parsed if str(x).strip()]
                except Exception:
                    pass
            return [s.strip().replace("_", " ") for s in val.split(",") if s.strip()]
        return [str(val)]

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

    price = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    discount_percentage = serializers.CharField(required=False, allow_blank=True, default="")
    discount_offer = serializers.CharField(required=False, allow_blank=True, default="")

    food_type = serializers.CharField(required=False, allow_blank=True, default="other")
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES)

    has_time_slots = serializers.BooleanField(default=False)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)

    description = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True, default="")

    image = serializers.ImageField(required=False, allow_null=True)

    post_to_happy_hour = serializers.BooleanField(required=False, default=False)
    hh_date = serializers.DateField(required=False, allow_null=True)
    hh_start_time = serializers.CharField(required=False, allow_blank=True, default="")
    hh_end_time = serializers.CharField(required=False, allow_blank=True, default="")
    hh_group_size = serializers.IntegerField(required=False, default=1)
    hh_event_type = serializers.CharField(required=False, allow_blank=True, default="casual")
    hh_vibe = serializers.CharField(required=False, allow_blank=True, default="casual")
    hh_discount_offer = serializers.CharField(required=False, allow_blank=True, default="")
    days_of_week = DaysOfWeekField(required=False, default=list)
    hh_days_of_week = serializers.CharField(required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        if hasattr(data, "dict"):
            data = data.dict()
        elif hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data)

        raw_food = data.get("food_type") if "food_type" in data else data.get("food_types")
        if raw_food is not None:
            data["food_type"] = normalize_food_type_input(raw_food)
        raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
        norm_days = normalize_days_of_week_input(raw_days)
        if norm_days:
            data["days_of_week"] = norm_days
            data["day_of_week"] = compute_single_day_of_week(norm_days)
        elif "day_of_week" in data:
            day_norm = normalize_days_of_week_input(data["day_of_week"])
            data["day_of_week"] = compute_single_day_of_week(day_norm)
            data["days_of_week"] = day_norm or [data["day_of_week"]]
        return super().to_internal_value(data)

    def validate(self, attrs):
        price = attrs.get("price")
        discount = attrs.get("discount_percentage") or attrs.get("discount_offer") or attrs.get("hh_discount_offer")
        if price is None and not str(discount or "").strip():
            raise serializers.ValidationError({
                "price": "Either a price or a discount offer must be provided."
            })
        return attrs


# ─────────────────────────────────────────────
# CREATE DEAL (MODEL)
# ─────────────────────────────────────────────
class CreateDealSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=8, decimal_places=2, required=False, allow_null=True)
    food_type = serializers.CharField(required=False, allow_blank=True, default="other")
    day_of_week = serializers.ChoiceField(choices=Deal.DAY_CHOICES, required=False)
    days_of_week = DaysOfWeekField(required=False)

    class Meta:
        model = Deal
        fields = [
            "title",
            "description",
            "price",
            "food_type",
            "day_of_week",
            "days_of_week",
            "start_time",
            "end_time",
            "has_time_slots",
            "location_branch",
            "discount_percentage",
            "image",
            "is_hot_deal",
            "expires_at",
        ]

    def to_internal_value(self, data):
        if hasattr(data, "dict"):
            data = data.dict()
        elif hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data)

        raw_food = data.get("food_type") if "food_type" in data else data.get("food_types")
        if raw_food is not None:
            data["food_type"] = normalize_food_type_input(raw_food)
        if "image" in data and isinstance(data["image"], str):
            data.pop("image", None)
        raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
        if raw_days is not None:
            norm_days = normalize_days_of_week_input(raw_days)
            data["days_of_week"] = norm_days
            data["day_of_week"] = compute_single_day_of_week(norm_days)
        elif "day_of_week" in data:
            day_norm = normalize_days_of_week_input(data["day_of_week"])
            data["day_of_week"] = compute_single_day_of_week(day_norm)
        return super().to_internal_value(data)

    def validate(self, attrs):
        price = attrs.get("price") if "price" in attrs else getattr(self.instance, "price", None)
        discount = attrs.get("discount_percentage") if "discount_percentage" in attrs else getattr(self.instance, "discount_percentage", "")
        if price is None and not str(discount or "").strip():
            raise serializers.ValidationError({
                "price": "Either a price or a discount offer must be provided."
            })
        return attrs


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