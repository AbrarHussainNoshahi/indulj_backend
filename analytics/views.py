from datetime import date, timedelta
from django.db.models.functions import TruncMonth, TruncDay, TruncYear

from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdmin, IsRestaurant, IsUser
from restaurants.models import Restaurant
from deals.models import Deal, SavedDeal
from happy_hours.models import HappyHour
from orders.models import Order
from notifications.models import Notification

import csv
from datetime import datetime, time

from django.db.models import DateTimeField
from django.http import HttpResponse
from django.utils.timesince import timesince


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def get_period_config(period):
    now = timezone.now()

    if period == "daily":
        return TruncDay, now - timedelta(days=14), "%b %d"

    if period == "yearly":
        return TruncYear, now - timedelta(days=365 * 3), "%Y"

    return TruncMonth, now - timedelta(days=30 * 6), "%b %Y"


def aggregate_by_period(qs, date_field, period="monthly", value_field=None):
    trunc_fn, start_date, label_format = get_period_config(period)

    qs = qs.filter(**{f"{date_field}__gte": start_date})

    if value_field:
        grouped = (
            qs.annotate(period=trunc_fn(date_field))
            .values("period")
            .annotate(value=Sum(value_field))
            .order_by("period")
        )
    else:
        grouped = (
            qs.annotate(period=trunc_fn(date_field))
            .values("period")
            .annotate(value=Count("id"))
            .order_by("period")
        )

    period_map = {}

    for row in grouped:
        if row["period"]:
            period_map[row["period"].strftime(label_format)] = float(row["value"] or 0)

    labels = []
    now = timezone.now()

    if period == "daily":
        for i in range(13, -1, -1):
            labels.append((now - timedelta(days=i)).strftime(label_format))

    elif period == "yearly":
        current_year = now.year
        labels = [str(current_year - 2), str(current_year - 1), str(current_year)]

    else:
        for i in range(5, -1, -1):
            labels.append((now - timedelta(days=30 * i)).strftime(label_format))

    return [
        {
            "label": label,
            "month": label,
            "value": period_map.get(label, 0),
        }
        for label in labels
    ]

def parse_int(value, default=6, minimum=1, maximum=24):
    try:
        value = int(value)
        return max(minimum, min(value, maximum))
    except Exception:
        return default


def month_start(dt):
    if hasattr(dt, "date"):
        dt = dt.date()
    return date(dt.year, dt.month, 1)


def shift_month(year, month, offset):
    month_index = (year * 12 + (month - 1)) + offset
    new_year = month_index // 12
    new_month = (month_index % 12) + 1
    return date(new_year, new_month, 1)


def month_labels(count=6):
    current = month_start(timezone.now())
    start = shift_month(current.year, current.month, -(count - 1))

    labels = []
    dates = []

    for i in range(count):
        d = shift_month(start.year, start.month, i)
        dates.append(d)
        labels.append(d.strftime("%b %Y"))

    return dates, labels


def last_n_months_data(qs, date_field, value_field=None, count=6):
    month_dates, labels = month_labels(count)
    start = month_dates[0]

    filter_kwargs = {f"{date_field}__gte": start}
    qs = qs.filter(**filter_kwargs)

    if value_field:
        grouped = (
            qs.annotate(month=TruncMonth(date_field))
            .values("month")
            .annotate(value=Sum(value_field))
            .order_by("month")
        )
    else:
        grouped = (
            qs.annotate(month=TruncMonth(date_field))
            .values("month")
            .annotate(value=Count("id"))
            .order_by("month")
        )

    month_map = {}

    for row in grouped:
        if row["month"]:
            key = row["month"].strftime("%b %Y")
            month_map[key] = float(row["value"] or 0)

    return [
        {
            "month": label,
            "value": month_map.get(label, 0),
        }
        for label in labels
    ]


def percentage_growth(current, previous):
    if previous > 0:
        return round(((current - previous) / previous) * 100, 1)

    if current > 0:
        return 100.0

    return 0.0


def get_user_restaurant(user):
    try:
        return user.restaurant
    except Exception:
        return Restaurant.objects.filter(owner=user).first()


def order_status_counts(qs):
    statuses = ["pending", "confirmed", "rejected", "cancelled", "completed"]

    return {
        status: qs.filter(status=status).count()
        for status in statuses
    }


def happy_hour_status_counts(qs):
    statuses = ["pending", "active", "upcoming", "rejected", "cancelled", "expired"]

    return {
        status: qs.filter(status=status).count()
        for status in statuses
    }


def deal_status_counts(qs):
    statuses = ["pending", "active", "rejected", "expired", "cancelled", "draft"]

    return {
        status: qs.filter(status=status).count()
        for status in statuses
    }


def money(value):
    return float(value or 0)


def paginate_list(data, page, page_size):
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "results": data[start:end],
        "count": len(data),
        "page": page,
        "page_size": page_size,
        "total_pages": (len(data) + page_size - 1) // page_size,
        "has_next": end < len(data),
        "has_prev": page > 1,
    }

# ══════════════════════════════════════════════════════════════
# ADMIN ANALYTICS
# ══════════════════════════════════════════════════════════════

class AdminDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        now = timezone.now()
        last_30 = now - timedelta(days=30)
        previous_30 = now - timedelta(days=60)

        total_users = User.objects.filter(role="user").count()
        total_restaurants = Restaurant.objects.count()
        total_orders = Order.objects.count()

        completed_orders = Order.objects.filter(status="completed")
        total_revenue = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        users_this_month = User.objects.filter(
            role="user",
            date_joined__gte=last_30,
        ).count()

        users_prev_month = User.objects.filter(
            role="user",
            date_joined__gte=previous_30,
            date_joined__lt=last_30,
        ).count()

        return Response(
            {
                "success": True,
                "data": {
                    "total_users": total_users,
                    "total_restaurants": total_restaurants,
                    "total_orders": total_orders,
                    "pending_orders": Order.objects.filter(status="pending").count(),
                    "completed_orders": completed_orders.count(),
                    "total_revenue": total_revenue,
                    "platform_growth": percentage_growth(
                        users_this_month,
                        users_prev_month,
                    ),
                    "pending_deals": Deal.objects.filter(status="pending").count(),
                    "active_deals": Deal.objects.filter(status="active").count(),
                    "pending_happy_hours": HappyHour.objects.filter(status="pending").count(),
                    "active_happy_hours": HappyHour.objects.filter(
                        status__in=["active", "upcoming"]
                    ).count(),
                    "unread_notifications": Notification.objects.filter(
                        is_read=False
                    ).count(),
                },
            }
        )


class AdminRevenueChartView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        months = parse_int(request.query_params.get("months"), default=6)

        data = last_n_months_data(
            Order.objects.filter(status="completed"),
            "updated_at",
            "total_amount",
            months,
        )

        return Response({"success": True, "data": data})


class AdminRevenueSourcesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        deal_revenue = money(
            Order.objects.filter(
                status="completed",
                deal__isnull=False,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        happy_hour_revenue = money(
            Order.objects.filter(
                status="completed",
                happy_hour__isnull=False,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        direct_revenue = money(
            Order.objects.filter(
                status="completed",
                deal__isnull=True,
                happy_hour__isnull=True,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        return Response(
            {
                "success": True,
                "data": [
                    {"label": "Deal Orders", "value": deal_revenue},
                    {"label": "Happy Hour Bookings", "value": happy_hour_revenue},
                    {"label": "Direct Orders", "value": direct_revenue},
                ],
            }
        )


class AdminSubmissionsChartView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        months = parse_int(request.query_params.get("months"), default=6)

        return Response(
            {
                "success": True,
                "data": {
                    "deals": last_n_months_data(
                        Deal.objects.all(),
                        "created_at",
                        None,
                        months,
                    ),
                    "happy_hours": last_n_months_data(
                        HappyHour.objects.all(),
                        "created_at",
                        None,
                        months,
                    ),
                    "orders": last_n_months_data(
                        Order.objects.all(),
                        "created_at",
                        None,
                        months,
                    ),
                },
            }
        )


class AdminUserGrowthView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        months = parse_int(request.query_params.get("months"), default=6)

        data = last_n_months_data(
            User.objects.filter(role="user"),
            "date_joined",
            None,
            months,
        )

        return Response({"success": True, "data": data})


class AdminRestaurantEarningsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        restaurants = (
            Restaurant.objects.annotate(
                total_revenue=Sum(
                    "orders__total_amount",
                    filter=Q(orders__status="completed"),
                ),
                total_completed_orders=Count(
                    "orders",
                    filter=Q(orders__status="completed"),
                    distinct=True,
                ),
            )
            .order_by("-total_revenue")[:20]
        )

        data = []

        for restaurant in restaurants:
            data.append(
                {
                    "id": restaurant.id,
                    "name": restaurant.name,
                    "city": restaurant.city,
                    "status": restaurant.status,
                    "rating": float(restaurant.rating or 0),
                    "total_reviews": restaurant.total_reviews or 0,
                    "total_revenue": money(restaurant.total_revenue),
                    "total_orders": restaurant.total_completed_orders or 0,
                    "total_deals": Deal.objects.filter(restaurant=restaurant).count(),
                    "active_deals": Deal.objects.filter(
                        restaurant=restaurant,
                        status="active",
                    ).count(),
                    "happy_hours": HappyHour.objects.filter(
                        restaurant=restaurant
                    ).count(),
                }
            )

        return Response({"success": True, "data": data})


class AdminPlatformSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        months = parse_int(request.query_params.get("months"), default=6)

        now = timezone.now()
        last_30 = now - timedelta(days=30)
        previous_30 = now - timedelta(days=60)

        total_users = User.objects.filter(role="user").count()
        total_restaurants = Restaurant.objects.count()
        total_orders = Order.objects.count()

        completed_orders = Order.objects.filter(status="completed")
        total_revenue = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        users_this_month = User.objects.filter(
            role="user",
            date_joined__gte=last_30,
        ).count()

        users_prev_month = User.objects.filter(
            role="user",
            date_joined__gte=previous_30,
            date_joined__lt=last_30,
        ).count()

        deal_revenue = money(
            completed_orders.filter(deal__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        happy_hour_revenue = money(
            completed_orders.filter(happy_hour__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        direct_revenue = money(
            completed_orders.filter(
                deal__isnull=True,
                happy_hour__isnull=True,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        top_restaurants_qs = (
            Restaurant.objects.annotate(
                revenue=Sum(
                    "orders__total_amount",
                    filter=Q(orders__status="completed"),
                ),
                total_completed_orders=Count(
                    "orders",
                    filter=Q(orders__status="completed"),
                    distinct=True,
                ),
            )
            .order_by("-revenue")[:10]
        )

        top_restaurants = []

        for restaurant in top_restaurants_qs:
            top_restaurants.append(
                {
                    "id": restaurant.id,
                    "name": restaurant.name,
                    "city": restaurant.city,
                    "status": restaurant.status,
                    "rating": float(restaurant.rating or 0),
                    "revenue": money(restaurant.revenue),
                    "orders": restaurant.total_completed_orders or 0,
                }
            )

        return Response(
            {
                "success": True,
                "data": {
                    "stats": {
                        "total_users": total_users,
                        "total_restaurants": total_restaurants,
                        "total_orders": total_orders,
                        "pending_orders": Order.objects.filter(status="pending").count(),
                        "completed_orders": completed_orders.count(),
                        "total_revenue": total_revenue,
                        "platform_growth": percentage_growth(
                            users_this_month,
                            users_prev_month,
                        ),
                        "pending_deals": Deal.objects.filter(status="pending").count(),
                        "active_deals": Deal.objects.filter(status="active").count(),
                        "pending_happy_hours": HappyHour.objects.filter(status="pending").count(),
                        "active_happy_hours": HappyHour.objects.filter(
                            status__in=["active", "upcoming"]
                        ).count(),
                    },
                    "charts": {
                        "revenue_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            "total_amount",
                            months,
                        ),
                        "orders_trend": last_n_months_data(
                            Order.objects.all(),
                            "created_at",
                            None,
                            months,
                        ),
                        "user_growth": last_n_months_data(
                            User.objects.filter(role="user"),
                            "date_joined",
                            None,
                            months,
                        ),
                        "deal_submissions": last_n_months_data(
                            Deal.objects.all(),
                            "created_at",
                            None,
                            months,
                        ),
                        "happy_hour_submissions": last_n_months_data(
                            HappyHour.objects.all(),
                            "created_at",
                            None,
                            months,
                        ),
                    },
                    "revenue_sources": [
                        {"label": "Deal Orders", "value": deal_revenue},
                        {"label": "Happy Hour Bookings", "value": happy_hour_revenue},
                        {"label": "Direct Orders", "value": direct_revenue},
                    ],
                    "order_statuses": order_status_counts(Order.objects.all()),
                    "deal_statuses": deal_status_counts(Deal.objects.all()),
                    "happy_hour_statuses": happy_hour_status_counts(
                        HappyHour.objects.all()
                    ),
                    "top_restaurants": top_restaurants,
                },
            }
        )

class AdminRevenueOrdersTrendView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        period = request.query_params.get("period", "monthly")
        orders = Order.objects.filter(status="completed")

        revenue_data = aggregate_by_period(
            orders,
            "updated_at",
            period,
            "total_amount",
        )

        orders_data = aggregate_by_period(
            orders,
            "updated_at",
            period,
        )

        orders_map = {item["label"]: item["value"] for item in orders_data}

        chart = [
            {
                "label": item["label"],
                "month": item["label"],
                "revenue": item["value"],
                "orders": orders_map.get(item["label"], 0),
            }
            for item in revenue_data
        ]

        return Response(
            {
                "success": True,
                "data": {
                    "stats": {
                        "total_revenue": float(
                            orders.aggregate(total=Sum("total_amount"))["total"] or 0
                        ),
                        "total_orders": orders.count(),
                    },
                    "chart": chart,
                },
            }
        )


class AdminDealsHappyHoursChartView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        period = request.query_params.get("period", "monthly")

        deals_data = aggregate_by_period(
            Deal.objects.all(),
            "created_at",
            period,
        )

        happy_hours_data = aggregate_by_period(
            HappyHour.objects.all(),
            "created_at",
            period,
        )

        hh_map = {item["label"]: item["value"] for item in happy_hours_data}

        data = [
            {
                "label": item["label"],
                "month": item["label"],
                "deals": item["value"],
                "happyHours": hh_map.get(item["label"], 0),
                "accepted": item["value"],
                "newDeals": hh_map.get(item["label"], 0),
            }
            for item in deals_data
        ]

        return Response({"success": True, "data": data})


class RestaurantRevenueOrdersTrendView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        period = request.query_params.get("period", "monthly")
        orders = Order.objects.filter(restaurant=restaurant, status="completed")

        revenue_data = aggregate_by_period(
            orders,
            "updated_at",
            period,
            "total_amount",
        )

        orders_data = aggregate_by_period(
            orders,
            "updated_at",
            period,
        )

        orders_map = {item["label"]: item["value"] for item in orders_data}

        chart = [
            {
                "label": item["label"],
                "month": item["label"],
                "name": item["label"],
                "revenue": item["value"],
                "orders": orders_map.get(item["label"], 0),
            }
            for item in revenue_data
        ]

        return Response(
            {
                "success": True,
                "data": {
                    "stats": {
                        "total_revenue": float(
                            orders.aggregate(total=Sum("total_amount"))["total"] or 0
                        ),
                        "total_orders": orders.count(),
                    },
                    "chart": chart,
                },
            }
        )


class RestaurantOptimizedDealsView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        deals = (
            Deal.objects.filter(restaurant=restaurant, status="active")
            .order_by("-views_count")[:3]
        )

        colors = ["#27AE60", "#FF4D4D", "#74E39A"]
        total_views = sum([deal.views_count or 0 for deal in deals]) or 1

        data = [
            {
                "name": deal.title,
                "value": round(((deal.views_count or 0) / total_views) * 100, 1),
                "color": colors[index % len(colors)],
            }
            for index, deal in enumerate(deals)
        ]

        return Response({"success": True, "data": data})


class RestaurantDealsPerformanceView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        deals = (
            Deal.objects.filter(restaurant=restaurant)
            .order_by("-views_count")[:7]
        )

        data = []

        for index, deal in enumerate(deals, 1):
            views = deal.views_count or 0
            redemptions = deal.redemptions_count or 0
            total = views + redemptions or 1

            data.append(
                {
                    "label": f"Deal {index}",
                    "title": deal.title[:24],
                    "views": views,
                    "redemptions": redemptions,
                    "performance": round((redemptions / total) * 100, 1),
                }
            )

        return Response({"success": True, "data": data})


class RestaurantHappyHoursAttendanceView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        period = request.query_params.get("period", "monthly")

        data = aggregate_by_period(
            HappyHour.objects.filter(
                restaurant=restaurant,
                status__in=["active", "upcoming"],
            ),
            "created_at",
            period,
        )

        return Response({"success": True, "data": data})

class AdminRestaurantAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found."},
                status=404,
            )

        months = parse_int(request.query_params.get("months"), default=6)
        restaurant_orders = Order.objects.filter(restaurant=restaurant)
        completed_orders = restaurant_orders.filter(status="completed")

        total_revenue = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        deal_revenue = money(
            completed_orders.filter(deal__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        happy_hour_revenue = money(
            completed_orders.filter(happy_hour__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        direct_revenue = money(
            completed_orders.filter(
                deal__isnull=True,
                happy_hour__isnull=True,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        return Response(
            {
                "success": True,
                "data": {
                    "restaurant": {
                        "id": restaurant.id,
                        "name": restaurant.name,
                        "city": restaurant.city,
                        "status": restaurant.status,
                        "rating": float(restaurant.rating or 0),
                        "total_reviews": restaurant.total_reviews or 0,
                    },
                    "stats": {
                        "total_revenue": total_revenue,
                        "total_orders": restaurant_orders.count(),
                        "completed_orders": completed_orders.count(),
                        "pending_orders": restaurant_orders.filter(
                            status="pending"
                        ).count(),
                        "total_deals": Deal.objects.filter(
                            restaurant=restaurant
                        ).count(),
                        "active_deals": Deal.objects.filter(
                            restaurant=restaurant,
                            status="active",
                        ).count(),
                        "total_happy_hours": HappyHour.objects.filter(
                            restaurant=restaurant
                        ).count(),
                    },
                    "charts": {
                        "revenue_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            "total_amount",
                            months,
                        ),
                        "orders_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            None,
                            months,
                        ),
                    },
                    "revenue_sources": [
                        {"label": "Deal Orders", "value": deal_revenue},
                        {"label": "Happy Hour Bookings", "value": happy_hour_revenue},
                        {"label": "Direct Orders", "value": direct_revenue},
                    ],
                    "order_statuses": order_status_counts(restaurant_orders),
                    "deal_statuses": deal_status_counts(
                        Deal.objects.filter(restaurant=restaurant)
                    ),
                    "happy_hour_statuses": happy_hour_status_counts(
                        HappyHour.objects.filter(restaurant=restaurant)
                    ),
                },
            }
        )


# ══════════════════════════════════════════════════════════════
# RESTAURANT ANALYTICS
# ══════════════════════════════════════════════════════════════

class RestaurantDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        deals = Deal.objects.filter(restaurant=restaurant)
        happy_hours = HappyHour.objects.filter(restaurant=restaurant)
        orders = Order.objects.filter(restaurant=restaurant)
        completed_orders = orders.filter(status="completed")

        total_revenue = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        total_views = deals.aggregate(total=Sum("views_count"))["total"] or 0
        total_redemptions = deals.aggregate(total=Sum("redemptions_count"))["total"] or 0

        conversion_rate = (
            round((total_redemptions / total_views) * 100, 1)
            if total_views > 0
            else 0
        )

        return Response(
            {
                "success": True,
                "data": {
                    "total_revenue": total_revenue,
                    "total_orders": orders.count(),
                    "pending_orders": orders.filter(status="pending").count(),
                    "completed_orders": completed_orders.count(),
                    "average_order_value": round(
                        total_revenue / completed_orders.count(),
                        2,
                    )
                    if completed_orders.count() > 0
                    else 0,
                    "total_views": total_views,
                    "total_redemptions": total_redemptions,
                    "conversion_rate": conversion_rate,
                    "active_deals": deals.filter(status="active").count(),
                    "expired_deals": deals.filter(status="expired").count(),
                    "pending_deals": deals.filter(status="pending").count(),
                    "active_happy_hours": happy_hours.filter(
                        status__in=["active", "upcoming"]
                    ).count(),
                    "pending_happy_hours": happy_hours.filter(
                        status="pending"
                    ).count(),
                    "rating": float(restaurant.rating or 0),
                    "total_reviews": restaurant.total_reviews or 0,
                },
            }
        )


class RestaurantAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {"success": False, "message": "Restaurant profile not found."},
                status=404,
            )

        months = parse_int(request.query_params.get("months"), default=6)

        deals = Deal.objects.filter(restaurant=restaurant)
        happy_hours = HappyHour.objects.filter(restaurant=restaurant)
        orders = Order.objects.filter(restaurant=restaurant)
        completed_orders = orders.filter(status="completed")

        total_revenue = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        deal_revenue = money(
            completed_orders.filter(deal__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        happy_hour_revenue = money(
            completed_orders.filter(happy_hour__isnull=False).aggregate(
                total=Sum("total_amount")
            )["total"]
        )

        direct_revenue = money(
            completed_orders.filter(
                deal__isnull=True,
                happy_hour__isnull=True,
            ).aggregate(total=Sum("total_amount"))["total"]
        )

        total_views = deals.aggregate(total=Sum("views_count"))["total"] or 0
        total_redemptions = deals.aggregate(total=Sum("redemptions_count"))["total"] or 0

        conversion_rate = (
            round((total_redemptions / total_views) * 100, 1)
            if total_views > 0
            else 0
        )

        top_deals = (
            deals.order_by("-views_count")[:8]
            .values(
                "id",
                "title",
                "views_count",
                "redemptions_count",
                "status",
                "price",
            )
        )

        deals_performance = [
            {
                "id": deal["id"],
                "title": deal["title"][:30],
                "views": deal["views_count"] or 0,
                "redemptions": deal["redemptions_count"] or 0,
                "status": deal["status"],
                "price": float(deal["price"] or 0),
            }
            for deal in top_deals
        ]

        reviews_qs = getattr(restaurant, "reviews", None)
        if reviews_qs:
            reviews = restaurant.reviews.all()
            avg_rating = float(reviews.aggregate(avg=Avg("rating"))["avg"] or 0)
            rating_rows = (
                reviews.values("rating")
                .annotate(count=Count("id"))
                .order_by("rating")
            )
            ratings_breakdown = {
                str(row["rating"]): row["count"]
                for row in rating_rows
            }
            total_reviews = reviews.count()
        else:
            avg_rating = float(restaurant.rating or 0)
            ratings_breakdown = {}
            total_reviews = restaurant.total_reviews or 0

        return Response(
            {
                "success": True,
                "data": {
                    "restaurant": {
                        "id": restaurant.id,
                        "name": restaurant.name,
                        "city": restaurant.city,
                        "status": restaurant.status,
                        "rating": float(restaurant.rating or 0),
                        "total_reviews": restaurant.total_reviews or 0,
                    },
                    "stats": {
                        "total_revenue": total_revenue,
                        "total_orders": orders.count(),
                        "completed_orders": completed_orders.count(),
                        "pending_orders": orders.filter(status="pending").count(),
                        "average_order_value": round(
                            total_revenue / completed_orders.count(),
                            2,
                        )
                        if completed_orders.count() > 0
                        else 0,
                        "total_views": total_views,
                        "total_redemptions": total_redemptions,
                        "conversion_rate": conversion_rate,
                        "avg_rating": round(avg_rating, 1),
                        "total_reviews": total_reviews,
                        "saved_deals": SavedDeal.objects.filter(
                            deal__restaurant=restaurant
                        ).count(),
                    },
                    "charts": {
                        "revenue_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            "total_amount",
                            months,
                        ),
                        "orders_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            None,
                            months,
                        ),
                        "deals_trend": last_n_months_data(
                            deals,
                            "created_at",
                            None,
                            months,
                        ),
                        "happy_hours_trend": last_n_months_data(
                            happy_hours,
                            "created_at",
                            None,
                            months,
                        ),
                        "deals_performance": deals_performance,
                    },
                    "revenue_sources": [
                        {"label": "Deal Orders", "value": deal_revenue},
                        {"label": "Happy Hour Bookings", "value": happy_hour_revenue},
                        {"label": "Direct Orders", "value": direct_revenue},
                    ],
                    "order_statuses": order_status_counts(orders),
                    "deal_statuses": deal_status_counts(deals),
                    "happy_hour_statuses": happy_hour_status_counts(happy_hours),
                    "ratings_breakdown": ratings_breakdown,
                },
            }
        )


# ══════════════════════════════════════════════════════════════
# USER ANALYTICS
# ══════════════════════════════════════════════════════════════

class UserDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        user = request.user

        orders = Order.objects.filter(user=user)
        happy_hours = HappyHour.objects.filter(submitted_by=user)
        saved_deals = SavedDeal.objects.filter(user=user)
        notifications = Notification.objects.filter(user=user)

        completed_orders = orders.filter(status="completed")
        total_spent = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        return Response(
            {
                "success": True,
                "data": {
                    "total_orders": orders.count(),
                    "pending_orders": orders.filter(status="pending").count(),
                    "completed_orders": completed_orders.count(),
                    "cancelled_orders": orders.filter(status="cancelled").count(),
                    "total_spent": total_spent,
                    "saved_deals": saved_deals.count(),
                    "planned_happy_hours": happy_hours.count(),
                    "pending_happy_hours": happy_hours.filter(status="pending").count(),
                    "accepted_happy_hours": happy_hours.filter(
                        status__in=["active", "upcoming"]
                    ).count(),
                    "rejected_happy_hours": happy_hours.filter(status="rejected").count(),
                    "cancelled_happy_hours": happy_hours.filter(status="cancelled").count(),
                    "unread_notifications": notifications.filter(is_read=False).count(),
                },
            }
        )


class UserAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        user = request.user
        months = parse_int(request.query_params.get("months"), default=6)

        orders = Order.objects.filter(user=user)
        completed_orders = orders.filter(status="completed")
        happy_hours = HappyHour.objects.filter(submitted_by=user)
        saved_deals = SavedDeal.objects.filter(user=user)
        notifications = Notification.objects.filter(user=user)

        total_spent = money(
            completed_orders.aggregate(total=Sum("total_amount"))["total"]
        )

        recent_orders = list(
            orders.select_related("restaurant", "deal", "happy_hour")
            .order_by("-created_at")[:5]
            .values(
                "id",
                "order_number",
                "order_type",
                "status",
                "total_amount",
                "booking_date",
                "booking_time",
                "restaurant__name",
                "deal__title",
                "happy_hour__title",
                "created_at",
            )
        )

        for order in recent_orders:
            order["total_amount"] = float(order["total_amount"] or 0)
            order["restaurant_name"] = order.pop("restaurant__name", "")
            order["deal_title"] = order.pop("deal__title", "")
            order["happy_hour_title"] = order.pop("happy_hour__title", "")

        recent_happy_hours = list(
            happy_hours.select_related("restaurant")
            .order_by("-created_at")[:5]
            .values(
                "id",
                "title",
                "status",
                "date",
                "start_time",
                "end_time",
                "restaurant__name",
                "created_at",
            )
        )

        for hh in recent_happy_hours:
            hh["restaurant_name"] = hh.pop("restaurant__name", "")

        return Response(
            {
                "success": True,
                "data": {
                    "stats": {
                        "total_orders": orders.count(),
                        "pending_orders": orders.filter(status="pending").count(),
                        "completed_orders": completed_orders.count(),
                        "cancelled_orders": orders.filter(status="cancelled").count(),
                        "total_spent": total_spent,
                        "saved_deals": saved_deals.count(),
                        "planned_happy_hours": happy_hours.count(),
                        "pending_happy_hours": happy_hours.filter(status="pending").count(),
                        "accepted_happy_hours": happy_hours.filter(
                            status__in=["active", "upcoming"]
                        ).count(),
                        "unread_notifications": notifications.filter(is_read=False).count(),
                    },
                    "charts": {
                        "orders_trend": last_n_months_data(
                            orders,
                            "created_at",
                            None,
                            months,
                        ),
                        "spending_trend": last_n_months_data(
                            completed_orders,
                            "updated_at",
                            "total_amount",
                            months,
                        ),
                        "happy_hours_trend": last_n_months_data(
                            happy_hours,
                            "created_at",
                            None,
                            months,
                        ),
                    },
                    "order_statuses": order_status_counts(orders),
                    "happy_hour_statuses": happy_hour_status_counts(happy_hours),
                    "recent_orders": recent_orders,
                    "recent_happy_hours": recent_happy_hours,
                    "saved_deals_recent": [
                        {
                            "id": saved.deal.id,
                            "title": saved.deal.title,
                            "restaurant_name": saved.deal.restaurant.name,
                            "price": float(saved.deal.price or 0),
                            "created_at": saved.created_at,
                        }
                        for saved in saved_deals.select_related(
                            "deal",
                            "deal__restaurant",
                        ).order_by("-created_at")[:5]
                        if saved.deal
                    ],
                },
            }
        )
        
        
# ══════════════════════════════════════════════════════════════
# RECENT ACTIVITY
# ══════════════════════════════════════════════════════════════

ACTIVITY_TYPE_LABELS = {
    "redemption": "Redemption",
    "booking": "Booking",
    "review": "Review",
    "view": "View",
    "revenue": "Revenue",
    "expiring": "Expiring",
}

ACTIVITY_STATUS_LABELS = {
    "completed": "Completed",
    "pending": "Pending",
    "success": "Success",
    "warning": "Warning",
}


def _activity_limit(request, default=10, maximum=100):
    try:
        value = int(request.query_params.get("limit", default))
        return max(1, min(value, maximum))
    except Exception:
        return default


def _has_model_field(model, field_name):
    return field_name in {field.name for field in model._meta.fields}


def _get_object_datetime(obj, *fields):
    for field in fields:
        value = getattr(obj, field, None)
        if value:
            return _coerce_datetime(value)

    return timezone.now()


def _coerce_datetime(value):
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return timezone.make_aware(datetime.combine(value, time.min))

    return timezone.now()


def _time_ago(value):
    dt = _coerce_datetime(value)
    now = timezone.now()

    if dt > now:
        return f"in {timesince(now, dt)}"

    return f"{timesince(dt, now)} ago"


def _activity_initials(name):
    clean = str(name or "").strip()

    if not clean:
        return "—"

    return "".join(part[0].upper() for part in clean.split()[:2])


def _activity_customer(user):
    if not user:
        return None

    name = (
        getattr(user, "full_name", None)
        or getattr(user, "email", None)
        or "Customer"
    )

    return {
        "name": name,
        "initials": _activity_initials(name),
        "email": getattr(user, "email", ""),
    }


def _order_item_name(order):
    if getattr(order, "deal", None):
        return order.deal.title

    if getattr(order, "happy_hour", None):
        return order.happy_hour.title

    items = getattr(order, "items", None) or []

    if isinstance(items, list) and items:
        first = items[0]
        return first.get("name") or first.get("title") or "Order"

    return "Order"


def _activity_row(
    *,
    uid,
    restaurant,
    item,
    customer=None,
    type_value,
    status_value,
    action,
    created_at,
):
    created_at = _coerce_datetime(created_at)

    customer_name = "—"
    customer_initials = "—"

    if customer:
        customer_name = customer.get("name") or "—"
        customer_initials = customer.get("initials") or _activity_initials(customer_name)

    return {
        "id": uid,
        "item": item or "—",
        "deal_name": item or "—",

        "restaurant": restaurant.name if restaurant else "—",
        "restaurant_id": restaurant.id if restaurant else None,

        "customer": customer,
        "customer_name": customer_name,
        "customerInitials": customer_initials,

        "type_value": type_value,
        "type": ACTIVITY_TYPE_LABELS.get(type_value, type_value.title()),

        "status_value": status_value,
        "status": ACTIVITY_STATUS_LABELS.get(status_value, status_value.title()),

        "action": action,

        "time_ago": _time_ago(created_at),
        "created_at": timezone.localtime(created_at).strftime("%b %d, %Y %I:%M %p"),
        "time": f"{_time_ago(created_at)}\n{timezone.localtime(created_at).strftime('%b %d, %Y %I:%M %p')}",
        "timestamp": created_at.isoformat(),

        "_sort_at": created_at,
    }


def _deal_expiry_field():
    for field_name in ["expires_at", "expiry_date", "end_date", "valid_until", "valid_to"]:
        if _has_model_field(Deal, field_name):
            return field_name

    return None


def _build_recent_activity(restaurant_qs, per_type_limit=50):
    restaurant_ids = list(restaurant_qs.values_list("id", flat=True))

    if not restaurant_ids:
        return []

    activities = []

    # ── 1. Order bookings: pending / confirmed orders ─────────
    booking_orders = (
        Order.objects.filter(
            restaurant_id__in=restaurant_ids,
            status__in=["pending", "confirmed"],
        )
        .select_related("restaurant", "user", "deal", "happy_hour")
        .order_by("-created_at")[:per_type_limit]
    )

    for order in booking_orders:
        action = "Table Booking" if order.order_type == "happy_hour" else "Deal Booking"

        activities.append(
            _activity_row(
                uid=f"booking-order-{order.id}",
                restaurant=order.restaurant,
                item=_order_item_name(order),
                customer=_activity_customer(order.user),
                type_value="booking",
                status_value="pending" if order.status == "pending" else "success",
                action=action,
                created_at=order.created_at,
            )
        )

    # ── 2. Completed deal redemptions ─────────────────────────
    completed_deal_orders = (
        Order.objects.filter(
            restaurant_id__in=restaurant_ids,
            status="completed",
            deal__isnull=False,
        )
        .select_related("restaurant", "user", "deal")
        .order_by("-updated_at")[:per_type_limit]
    )

    for order in completed_deal_orders:
        activities.append(
            _activity_row(
                uid=f"redemption-{order.id}",
                restaurant=order.restaurant,
                item=order.deal.title if order.deal else _order_item_name(order),
                customer=_activity_customer(order.user),
                type_value="redemption",
                status_value="completed",
                action="Deal Redeemed",
                created_at=_get_object_datetime(order, "completed_at", "updated_at", "created_at"),
            )
        )

    # ── 3. Revenue from completed orders ──────────────────────
    completed_orders = (
        Order.objects.filter(
            restaurant_id__in=restaurant_ids,
            status="completed",
        )
        .select_related("restaurant", "user", "deal", "happy_hour")
        .order_by("-updated_at")[:per_type_limit]
    )

    for order in completed_orders:
        activities.append(
            _activity_row(
                uid=f"revenue-{order.id}",
                restaurant=order.restaurant,
                item=_order_item_name(order),
                customer=None,
                type_value="revenue",
                status_value="success",
                action=f"Revenue Generated (${order.total_amount})",
                created_at=_get_object_datetime(order, "completed_at", "updated_at", "created_at"),
            )
        )

    # ── 4. Happy hour bookings / requests ─────────────────────
    happy_hours = (
        HappyHour.objects.filter(
            restaurant_id__in=restaurant_ids,
            status__in=["pending", "active", "upcoming"],
        )
        .select_related("restaurant", "submitted_by")
        .order_by("-updated_at")[:per_type_limit]
    )

    for happy_hour in happy_hours:
        activities.append(
            _activity_row(
                uid=f"happy-hour-{happy_hour.id}",
                restaurant=happy_hour.restaurant,
                item=happy_hour.title,
                customer=_activity_customer(happy_hour.submitted_by),
                type_value="booking",
                status_value="pending" if happy_hour.status == "pending" else "success",
                action="Table Booking" if happy_hour.status in ["active", "upcoming"] else "Happy Hour Request",
                created_at=_get_object_datetime(happy_hour, "updated_at", "created_at"),
            )
        )

    # ── 5. Reviews ────────────────────────────────────────────
    try:
        from restaurants.models import Review

        review_qs = Review.objects.filter(restaurant_id__in=restaurant_ids)

        if _has_model_field(Review, "is_hidden"):
            review_qs = review_qs.filter(is_hidden=False)

        select_fields = ["restaurant", "user"]

        if _has_model_field(Review, "deal"):
            select_fields.append("deal")

        reviews = review_qs.select_related(*select_fields).order_by("-created_at")[:per_type_limit]

        for review in reviews:
            review_deal = getattr(review, "deal", None)
            item = review_deal.title if review_deal else review.restaurant.name

            activities.append(
                _activity_row(
                    uid=f"review-{review.id}",
                    restaurant=review.restaurant,
                    item=item,
                    customer=_activity_customer(review.user),
                    type_value="review",
                    status_value="success",
                    action=f"{review.rating} Star Review",
                    created_at=review.created_at,
                )
            )

    except Exception:
        pass

    # ── 6. Deal views ─────────────────────────────────────────
    if _has_model_field(Deal, "views_count"):
        deal_order_field = "-updated_at" if _has_model_field(Deal, "updated_at") else "-created_at"

        viewed_deals = (
            Deal.objects.filter(
                restaurant_id__in=restaurant_ids,
                views_count__gt=0,
            )
            .select_related("restaurant")
            .order_by(deal_order_field)[:per_type_limit]
        )

        for deal in viewed_deals:
            activities.append(
                _activity_row(
                    uid=f"view-{deal.id}",
                    restaurant=deal.restaurant,
                    item=deal.title,
                    customer=None,
                    type_value="view",
                    status_value="success",
                    action=f"Deal Views ({deal.views_count})",
                    created_at=_get_object_datetime(deal, "updated_at", "created_at"),
                )
            )

    # ── 7. Expiring deals ─────────────────────────────────────
    expiry_field = _deal_expiry_field()

    if expiry_field:
        try:
            field = Deal._meta.get_field(expiry_field)
            now = timezone.now()
            soon = now + timedelta(days=7)

            if not isinstance(field, DateTimeField):
                now_value = timezone.localdate()
                soon_value = timezone.localdate() + timedelta(days=7)
            else:
                now_value = now
                soon_value = soon

            filter_kwargs = {
                "restaurant_id__in": restaurant_ids,
                "status": "active",
                f"{expiry_field}__isnull": False,
                f"{expiry_field}__gte": now_value,
                f"{expiry_field}__lte": soon_value,
            }

            expiring_deals = (
                Deal.objects.filter(**filter_kwargs)
                .select_related("restaurant")
                .order_by(expiry_field)[:per_type_limit]
            )

            for deal in expiring_deals:
                activities.append(
                    _activity_row(
                        uid=f"expiring-{deal.id}",
                        restaurant=deal.restaurant,
                        item=deal.title,
                        customer=None,
                        type_value="expiring",
                        status_value="warning",
                        action="Expiring Soon",
                        created_at=getattr(deal, expiry_field),
                    )
                )

        except Exception:
            pass

    activities.sort(key=lambda item: item["_sort_at"], reverse=True)

    return activities


def _filter_recent_activity(activities, request, default_limit=10, maximum=100):
    type_filter = request.query_params.get("type", "all")
    search = request.query_params.get("search", "").lower().strip()

    if type_filter and type_filter != "all":
        activities = [
            item for item in activities
            if item["type_value"] == type_filter
        ]

    if search:
        activities = [
            item for item in activities
            if search in str(item.get("item", "")).lower()
            or search in str(item.get("customer_name", "")).lower()
            or search in str(item.get("restaurant", "")).lower()
            or search in str(item.get("type", "")).lower()
            or search in str(item.get("status", "")).lower()
            or search in str(item.get("action", "")).lower()
        ]

    limit = _activity_limit(request, default=default_limit, maximum=maximum)
    activities = activities[:limit]

    for item in activities:
        item.pop("_sort_at", None)

    return activities


def _recent_activity_csv_response(activities, filename):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    writer.writerow([
        "Deal / Item",
        "Restaurant",
        "Customer",
        "Type",
        "Time",
        "Status",
        "Action",
    ])

    for item in activities:
        writer.writerow([
            item.get("item", "—"),
            item.get("restaurant", "—"),
            item.get("customer_name", "—"),
            item.get("type", "—"),
            item.get("created_at", "—"),
            item.get("status", "—"),
            item.get("action", "—"),
        ])

    return response


class RestaurantRecentActivityView(APIView):
    """
    GET /api/analytics/restaurant/recent-activity/
    Params:
      ?type=all|redemption|booking|review|view|revenue|expiring
      ?search=pizza
      ?limit=10
    """

    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant profile not found.",
                },
                status=404,
            )

        activities = _build_recent_activity(
            Restaurant.objects.filter(id=restaurant.id),
            per_type_limit=50,
        )

        data = _filter_recent_activity(
            activities,
            request,
            default_limit=10,
            maximum=100,
        )

        def get(self, request):
            restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response({
                "success": False,
                "message": "Restaurant profile not found."
            }, status=404)

        activities = _build_recent_activity(
            Restaurant.objects.filter(id=restaurant.id),
            per_type_limit=80,
        )

        # filters
        data = _filter_recent_activity(
            activities,
            request,
            default_limit=1000,   # IMPORTANT: remove limiting
            maximum=1000,
        )

        # pagination (NEW)
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))

        paginated = paginate_list(data, page, page_size)

        return Response({
            "success": True,
            **paginated
        })


class AdminRecentActivityView(APIView):
    """
    GET /api/analytics/admin/recent-activity/
    Params:
      ?type=all|redemption|booking|review|view|revenue|expiring
      ?search=pizza
      ?limit=10
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        activities = _build_recent_activity(
            Restaurant.objects.all(),
            per_type_limit=80,
        )

        data = _filter_recent_activity(
            activities,
            request,
            default_limit=10,
            maximum=100,
        )

        data = _filter_recent_activity(
            activities,
            request,
            default_limit=1000,
            maximum=1000,
        )

        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 10))

        paginated = paginate_list(data, page, page_size)

        return Response({
            "success": True,
            **paginated
        })


class RestaurantRecentActivityExportView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        restaurant = get_user_restaurant(request.user)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant profile not found.",
                },
                status=404,
            )

        activities = _build_recent_activity(
            Restaurant.objects.filter(id=restaurant.id),
            per_type_limit=500,
        )

        data = _filter_recent_activity(
            activities,
            request,
            default_limit=500,
            maximum=1000,
        )

        return _recent_activity_csv_response(
            data,
            f"{restaurant.name}_recent_activity.csv",
        )


class AdminRecentActivityExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        activities = _build_recent_activity(
            Restaurant.objects.all(),
            per_type_limit=500,
        )

        data = _filter_recent_activity(
            activities,
            request,
            default_limit=500,
            maximum=1000,
        )

        return _recent_activity_csv_response(
            data,
            "indulj_recent_activity.csv",
        )
        
