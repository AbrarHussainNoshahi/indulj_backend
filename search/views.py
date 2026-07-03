from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q

from restaurants.models import Restaurant
from deals.models import Deal
from happy_hours.models import HappyHour


def build_absolute_image(request, image):
    if image:
        return request.build_absolute_uri(image.url)
    return None


def day_filter_q(day):
    day = (day or "").strip().lower()

    if not day:
        return Q()

    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    weekends = ["saturday", "sunday"]

    q = Q(day_of_week=day) | Q(day_of_week="everyday")

    if day in weekdays:
        q |= Q(day_of_week="weekdays")

    if day in weekends:
        q |= Q(day_of_week="weekends")

    return q


class GlobalSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        q = request.query_params.get("q", "").strip()

        if not q or len(q) < 2:
            return Response(
                {
                    "success": False,
                    "message": "Search query must be at least 2 characters.",
                },
                status=400,
            )

        restaurants = (
            Restaurant.objects.filter(status="active")
            .filter(
                Q(name__icontains=q)
                | Q(city__icontains=q)
                | Q(address__icontains=q)
                | Q(description__icontains=q)
                | Q(categories__icontains=q)
            )
            .order_by("-rating")[:6]
        )

        restaurants_data = [
            {
                "id": r.id,
                "type": "restaurant",
                "name": r.name,
                "city": r.city,
                "address": r.address,
                "rating": float(r.rating or 0),
                "total_reviews": r.total_reviews,
                "categories": r.categories,
                "latitude": float(r.latitude) if r.latitude is not None else None,
                "longitude": float(r.longitude) if r.longitude is not None else None,
                "logo_url": build_absolute_image(request, getattr(r, "logo", None)),
            }
            for r in restaurants
        ]

        deals = (
            Deal.objects.filter(status="active")
            .filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(food_type__icontains=q)
                | Q(restaurant__name__icontains=q)
                | Q(restaurant__city__icontains=q)
            )
            .select_related("restaurant")
            .order_by("-is_hot_deal", "-created_at")[:6]
        )

        deals_data = [
            {
                "id": d.id,
                "type": "deal",
                "title": d.title,
                "description": d.description,
                "price": float(d.price),
                "food_type": d.food_type,
                "day_of_week": d.day_of_week,
                "is_hot_deal": d.is_hot_deal,
                "restaurant_id": d.restaurant.id,
                "restaurant_name": d.restaurant.name,
                "restaurant_city": d.restaurant.city,
                "latitude": float(d.restaurant.latitude)
                if d.restaurant.latitude is not None
                else None,
                "longitude": float(d.restaurant.longitude)
                if d.restaurant.longitude is not None
                else None,
                "image_url": build_absolute_image(request, d.image),
            }
            for d in deals
        ]

        happy_hours = (
            HappyHour.objects.filter(
                status__in=["active", "upcoming"],
                is_public=True,
            )
            .filter(
                Q(title__icontains=q)
                | Q(event_type__icontains=q)
                | Q(vibe__icontains=q)
                | Q(restaurant__name__icontains=q)
                | Q(restaurant__city__icontains=q)
            )
            .select_related("restaurant")
            .order_by("-created_at")[:6]
        )

        happy_hours_data = [
            {
                "id": hh.id,
                "type": "happy_hour",
                "title": hh.title,
                "event_type": hh.event_type,
                "vibe": hh.vibe,
                "group_size": hh.group_size,
                "restaurant_id": hh.restaurant.id,
                "restaurant_name": hh.restaurant.name,
                "restaurant_city": hh.restaurant.city,
                "start_time": str(hh.start_time),
                "end_time": str(hh.end_time),
            }
            for hh in happy_hours
        ]

        return Response(
            {
                "success": True,
                "query": q,
                "total": len(restaurants_data)
                + len(deals_data)
                + len(happy_hours_data),
                "data": {
                    "restaurants": restaurants_data,
                    "deals": deals_data,
                    "happy_hours": happy_hours_data,
                },
            }
        )


class SearchRestaurantsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Restaurant.objects.filter(status="active")

        q = request.query_params.get("q", "").strip()
        city = request.query_params.get("city", "").strip()
        category = request.query_params.get("category", "").strip()
        min_rating = request.query_params.get("min_rating")

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(address__icontains=q)
                | Q(description__icontains=q)
                | Q(categories__icontains=q)
            )

        if city:
            qs = qs.filter(city__icontains=city)

        if category:
            qs = qs.filter(categories__icontains=category)

        if min_rating:
            qs = qs.filter(rating__gte=float(min_rating))

        qs = qs.order_by("-rating")[:30]

        data = [
            {
                "id": r.id,
                "name": r.name,
                "city": r.city,
                "address": r.address,
                "rating": float(r.rating or 0),
                "total_reviews": r.total_reviews,
                "categories": r.categories,
                "latitude": float(r.latitude) if r.latitude is not None else None,
                "longitude": float(r.longitude) if r.longitude is not None else None,
                "logo_url": build_absolute_image(request, getattr(r, "logo", None)),
            }
            for r in qs
        ]

        return Response(
            {
                "success": True,
                "count": len(data),
                "data": data,
            }
        )


class SearchDealsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Deal.objects.filter(status="active").select_related("restaurant")

        q = request.query_params.get("q", "").strip()
        city = request.query_params.get("city", "").strip()
        food_type = request.query_params.get("food_type", "").strip()
        day = request.query_params.get("day_of_week", "").strip().lower()
        price_min = request.query_params.get("price_min")
        price_max = request.query_params.get("price_max")
        is_hot = request.query_params.get("is_hot")

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(food_type__icontains=q)
                | Q(restaurant__name__icontains=q)
            )

        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        if food_type:
            qs = qs.filter(food_type=food_type)

        if day:
            qs = qs.filter(day_filter_q(day))

        if price_min:
            qs = qs.filter(price__gte=float(price_min))

        if price_max:
            qs = qs.filter(price__lte=float(price_max))

        if is_hot == "true":
            qs = qs.filter(is_hot_deal=True)

        qs = qs.order_by("-is_hot_deal", "-created_at")[:50]

        data = [
            {
                "id": d.id,
                "title": d.title,
                "description": d.description,
                "price": float(d.price),
                "food_type": d.food_type,
                "day_of_week": d.day_of_week,
                "start_time": str(d.start_time) if d.start_time else None,
                "end_time": str(d.end_time) if d.end_time else None,
                "is_hot_deal": d.is_hot_deal,
                "discount_percentage": d.discount_percentage,
                "views_count": d.views_count,
                "restaurant_id": d.restaurant.id,
                "restaurant_name": d.restaurant.name,
                "restaurant_city": d.restaurant.city,
                "restaurant_address": d.restaurant.address,
                "latitude": float(d.restaurant.latitude)
                if d.restaurant.latitude is not None
                else None,
                "longitude": float(d.restaurant.longitude)
                if d.restaurant.longitude is not None
                else None,
                "image_url": build_absolute_image(request, d.image),
            }
            for d in qs
        ]

        return Response(
            {
                "success": True,
                "count": len(data),
                "data": data,
            }
        )


class SearchHappyHoursView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = HappyHour.objects.filter(
            status__in=["active", "upcoming"],
            is_public=True,
        ).select_related("restaurant")

        q = request.query_params.get("q", "").strip()
        city = request.query_params.get("city", "").strip()
        vibe = request.query_params.get("vibe", "").strip()
        event_type = request.query_params.get("event_type", "").strip()
        group_size = request.query_params.get("group_size_min")

        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(event_type__icontains=q)
                | Q(restaurant__name__icontains=q)
            )

        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        if vibe:
            qs = qs.filter(vibe=vibe)

        if event_type:
            qs = qs.filter(event_type=event_type)

        if group_size:
            qs = qs.filter(group_size__gte=int(group_size))

        qs = qs.order_by("-created_at")[:30]

        data = [
            {
                "id": hh.id,
                "title": hh.title,
                "event_type": hh.event_type,
                "vibe": hh.vibe,
                "group_size": hh.group_size,
                "start_time": str(hh.start_time),
                "end_time": str(hh.end_time),
                "is_public": hh.is_public,
                "discount_offer": hh.discount_offer,
                "restaurant_id": hh.restaurant.id,
                "restaurant_name": hh.restaurant.name,
                "restaurant_city": hh.restaurant.city,
            }
            for hh in qs
        ]

        return Response(
            {
                "success": True,
                "count": len(data),
                "data": data,
            }
        )


class MapDataView(APIView):
    """
    GET /api/search/map/?city=Miami&day=sunday&type=deals
    """

    permission_classes = [AllowAny]

    def get(self, request):
        city = request.query_params.get("city", "").strip()
        day = request.query_params.get("day", "").strip().lower()
        data_type = request.query_params.get("type", "deals").strip()

        result = {
            "deals": [],
            "restaurants": [],
        }

        if data_type in ["all", "deals"]:
            deal_qs = (
                Deal.objects.filter(
                    status="active",
                    restaurant__status="active",
                    restaurant__latitude__isnull=False,
                    restaurant__longitude__isnull=False,
                )
                .select_related("restaurant")
                .order_by("-is_hot_deal", "-created_at")
            )

            if city:
                deal_qs = deal_qs.filter(restaurant__city__icontains=city)

            if day:
                deal_qs = deal_qs.filter(day_filter_q(day))

            result["deals"] = [
                {
                    "id": d.id,
                    "type": "deal",
                    "title": d.title,
                    "description": d.description,
                    "price": float(d.price),
                    "food_type": d.food_type,
                    "day_of_week": d.day_of_week,
                    "start_time": str(d.start_time) if d.start_time else None,
                    "end_time": str(d.end_time) if d.end_time else None,
                    "is_hot_deal": d.is_hot_deal,
                    "discount_percentage": d.discount_percentage,
                    "restaurant_id": d.restaurant.id,
                    "restaurant_name": d.restaurant.name,
                    "restaurant_city": d.restaurant.city,
                    "restaurant_address": d.restaurant.address,
                    "latitude": float(d.restaurant.latitude),
                    "longitude": float(d.restaurant.longitude),
                    "pin_type": "hot" if d.is_hot_deal else "regular",
                    "image_url": build_absolute_image(request, d.image),
                }
                for d in deal_qs
            ]

        if data_type in ["all", "restaurants"]:
            rest_qs = Restaurant.objects.filter(
                status="active",
                latitude__isnull=False,
                longitude__isnull=False,
            ).order_by("-rating")

            if city:
                rest_qs = rest_qs.filter(city__icontains=city)

            result["restaurants"] = [
                {
                    "id": r.id,
                    "type": "restaurant",
                    "name": r.name,
                    "city": r.city,
                    "address": r.address,
                    "rating": float(r.rating or 0),
                    "total_reviews": r.total_reviews,
                    "categories": r.categories,
                    "latitude": float(r.latitude),
                    "longitude": float(r.longitude),
                    "logo_url": build_absolute_image(request, getattr(r, "logo", None)),
                    "pin_type": "restaurant",
                }
                for r in rest_qs
            ]

        return Response(
            {
                "success": True,
                "filters": {
                    "city": city,
                    "day": day,
                    "type": data_type,
                },
                "count": {
                    "deals": len(result["deals"]),
                    "restaurants": len(result["restaurants"]),
                },
                "data": result,
            }
        )


class MapCitiesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cities = (
            Restaurant.objects.filter(status="active", city__gt="")
            .values_list("city", flat=True)
            .distinct()
            .order_by("city")
        )

        return Response(
            {
                "success": True,
                "data": list(cities),
            }
        )