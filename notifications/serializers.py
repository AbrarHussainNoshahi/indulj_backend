from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    status = serializers.ReadOnlyField()
    related_order_number = serializers.SerializerMethodField()
    related_deal_title = serializers.SerializerMethodField()
    related_happy_hour_title = serializers.SerializerMethodField()
    related_restaurant_name = serializers.SerializerMethodField()
    related_title = serializers.SerializerMethodField()
    action_url = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'type',
            'title',
            'message',
            'status',
            'is_read',
            'read_at',
            'related_order',
            'related_order_number',
            'related_deal',
            'related_deal_title',
            'related_happy_hour',
            'related_happy_hour_title',
            'related_restaurant',
            'related_restaurant_name',
            'related_title',
            'action_url',
            'metadata',
            'created_at',
        ]

    def get_related_order_number(self, obj):
        return obj.related_order.order_number if obj.related_order else None

    def get_related_deal_title(self, obj):
        return obj.related_deal.title if obj.related_deal else None

    def get_related_happy_hour_title(self, obj):
        return obj.related_happy_hour.title if obj.related_happy_hour else None

    def get_related_restaurant_name(self, obj):
        return obj.related_restaurant.name if obj.related_restaurant else None

    def get_related_title(self, obj):
        if obj.related_order:
            return obj.related_order.order_number
        if obj.related_deal:
            return obj.related_deal.title
        if obj.related_happy_hour:
            return obj.related_happy_hour.title
        if obj.related_restaurant:
            return obj.related_restaurant.name
        return None

    def get_action_url(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        role = getattr(user, 'role', 'user') if user else 'user'

        if obj.type == 'order':
            if role == 'restaurant':
                return '/restaurant/dashboard/res_orders'
            elif role == 'admin':
                return '/admin/dashboard/orders'
            else:
                return '/dashboard/orders'

        elif obj.type == 'happy_hour':
            if role == 'restaurant':
                return '/restaurant/dashboard/res_happy-hours'
            elif role == 'admin':
                return '/admin/dashboard/happy-hours'
            else:
                return '/dashboard/happy-hours'

        elif obj.type == 'deal':
            if role == 'restaurant':
                return '/restaurant/dashboard/res_deals'
            elif role == 'admin':
                return '/admin/dashboard/deals'
            else:
                return '/dashboard/submitted-deals'

        elif obj.type == 'restaurant':
            if role == 'admin':
                return '/admin/dashboard/restaurants'
            elif role == 'restaurant':
                return '/restaurant/dashboard'
            else:
                return '/restaurants'

        return ''
