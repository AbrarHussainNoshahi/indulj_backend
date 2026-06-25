from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Order
from deals.models import Deal
from happy_hours.models import HappyHour


class OrderListSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)
    restaurant_city = serializers.CharField(source="restaurant.city", read_only=True)
    restaurant_address = serializers.CharField(source="restaurant.address", read_only=True)

    deal_title = serializers.SerializerMethodField()
    happy_hour_title = serializers.SerializerMethodField()
    item_title = serializers.SerializerMethodField()
    item_image_url = serializers.SerializerMethodField()

    status_label = serializers.SerializerMethodField()
    order_type_label = serializers.SerializerMethodField()
    time_label = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "user",
            "user_name",
            "user_email",
            "restaurant",
            "restaurant_name",
            "restaurant_city",
            "restaurant_address",
            "deal",
            "deal_title",
            "happy_hour",
            "happy_hour_title",
            "item_title",
            "item_image_url",
            "order_type",
            "order_type_label",
            "status",
            "status_label",
            "items",
            "quantity",
            "group_size",
            "booking_date",
            "booking_time",
            "time_label",
            "notes",
            "restaurant_response",
            "rejection_reason",
            "total_amount",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        return getattr(obj.user, "full_name", "") or getattr(obj.user, "email", "")

    def get_user_email(self, obj):
        return getattr(obj.user, "email", "")

    def get_deal_title(self, obj):
        return obj.deal.title if obj.deal else None

    def get_happy_hour_title(self, obj):
        return obj.happy_hour.title if obj.happy_hour else None

    def get_item_title(self, obj):
        if obj.deal:
            return obj.deal.title
        if obj.happy_hour:
            return obj.happy_hour.title
        return "Order"

    def get_item_image_url(self, obj):
        request = self.context.get("request")

        image = None

        if obj.deal and getattr(obj.deal, "image", None):
            image = obj.deal.image

        if obj.happy_hour and getattr(obj.happy_hour, "image", None):
            image = obj.happy_hour.image

        if image and request:
            return request.build_absolute_uri(image.url)

        if image:
            return image.url

        return None

    def get_status_label(self, obj):
        return obj.get_status_display()

    def get_order_type_label(self, obj):
        return obj.get_order_type_display()

    def get_time_label(self, obj):
        if obj.booking_time:
            return obj.booking_time.strftime("%H:%M")
        return None


class OrderDetailSerializer(OrderListSerializer):
    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + [
            "confirmed_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",
        ]


class CreateOrderSerializer(serializers.Serializer):
    deal = serializers.IntegerField(required=False, allow_null=True)
    happy_hour = serializers.IntegerField(required=False, allow_null=True)

    items = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    quantity = serializers.IntegerField(min_value=1, required=False, default=1)
    group_size = serializers.IntegerField(min_value=1, required=False, default=1)

    booking_date = serializers.DateField(required=False, allow_null=True)
    booking_time = serializers.TimeField(required=False, allow_null=True)

    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_items(self, value):
        for item in value:
            if "name" not in item:
                raise serializers.ValidationError("Each item must have a name.")
            if "quantity" not in item:
                raise serializers.ValidationError("Each item must have a quantity.")
            if "price" not in item:
                raise serializers.ValidationError("Each item must have a price.")
        return value

    def validate(self, attrs):
        deal_id = attrs.get("deal")
        happy_hour_id = attrs.get("happy_hour")

        if deal_id and happy_hour_id:
            raise serializers.ValidationError(
                "You can book either a deal or a happy hour, not both."
            )

        if not deal_id and not happy_hour_id:
            raise serializers.ValidationError(
                "Please select a deal or happy hour to book."
            )

        if deal_id:
            try:
                deal = Deal.objects.select_related("restaurant").get(
                    pk=deal_id,
                    status="active",
                    restaurant__status="active",
                )
            except Deal.DoesNotExist:
                raise serializers.ValidationError(
                    {"deal": "Active deal not found."}
                )

            quantity = attrs.get("quantity", 1)
            items = attrs.get("items", [])

            if not items:
                items = [
                    {
                        "name": deal.title,
                        "quantity": quantity,
                        "price": str(deal.price or 0),
                    }
                ]

            total_amount = Decimal("0.00")

            for item in items:
                price = Decimal(str(item.get("price", 0)))
                item_qty = int(item.get("quantity", 1))
                total_amount += price * item_qty

            attrs["deal_obj"] = deal
            attrs["restaurant"] = deal.restaurant
            attrs["order_type"] = "deal"
            attrs["items"] = items
            attrs["total_amount"] = total_amount

            if not attrs.get("booking_date"):
                attrs["booking_date"] = timezone.localdate()

        if happy_hour_id:
            try:
                happy_hour = HappyHour.objects.select_related("restaurant").get(
                    pk=happy_hour_id,
                    status__in=["active", "upcoming"],
                    is_public=True,
                    restaurant__status="active",
                )
            except HappyHour.DoesNotExist:
                raise serializers.ValidationError(
                    {"happy_hour": "Active happy hour not found."}
                )

            group_size = attrs.get("group_size", 1)
            items = attrs.get("items", [])

            if not items:
                items = [
                    {
                        "name": happy_hour.title,
                        "quantity": group_size,
                        "price": "0",
                    }
                ]

            attrs["happy_hour_obj"] = happy_hour
            attrs["restaurant"] = happy_hour.restaurant
            attrs["order_type"] = "happy_hour"
            attrs["items"] = items
            attrs["total_amount"] = Decimal("0.00")

            if not attrs.get("booking_date"):
                attrs["booking_date"] = happy_hour.date or timezone.localdate()

            if not attrs.get("booking_time"):
                attrs["booking_time"] = happy_hour.start_time

        return attrs


class OrderResponseSerializer(serializers.Serializer):
    response = serializers.CharField(required=False, allow_blank=True, default="")


class RejectOrderSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=True, allow_blank=False)