
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
from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsRestaurant, IsUser, IsUserOrAdmin
from restaurants.models import Restaurant
from restaurants.geocoding import ensure_restaurant_coordinates

from .models import Deal, SavedDeal, DealView, DealVote, DealAccuracyVote
from .serializers import (
    DealListSerializer,
    DealDetailSerializer,
    SubmitDealSerializer,
    CreateDealSerializer,
    RejectDealSerializer,
    SavedDealSerializer,
    AdminCreateDealSerializer,
    AdminUpdateDealSerializer,
    normalize_food_type_input,
    normalize_days_of_week_input,
    compute_single_day_of_week,
)

from django.utils import timezone
from datetime import timedelta
from notifications.utils import create_notification, notify_admins
from notifications.email_service import (
    send_deal_notification_emails,
    send_happy_hour_notification_emails,
    send_deal_planned_email,
)


def enforce_two_active_happy_hour_deals_rule(restaurant, new_hh=None):
    """
    Enforce: Each restaurant can have at most 2 active Happy Hour Deals on any given day.
    If activating new_hh causes any day to exceed 2 active Happy Hour Deals,
    the oldest active Happy Hour Deal(s) on that day are expired.
    """
    from happy_hours.models import HappyHour
    ALL_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    def expand_days(hh_obj):
        days = []
        raw_days = getattr(hh_obj, "days_of_week", None) or []
        if isinstance(raw_days, list) and len(raw_days) > 0:
            for d in raw_days:
                dl = str(d).lower().strip()
                if dl in ("everyday", "all", "daily"):
                    return set(ALL_DAYS)
                elif dl == "weekdays":
                    days.extend(["monday", "tuesday", "wednesday", "thursday", "friday"])
                elif dl == "weekends":
                    days.extend(["saturday", "sunday"])
                elif dl in ALL_DAYS:
                    days.append(dl)
        elif getattr(hh_obj, "date", None):
            days.append(hh_obj.date.strftime("%A").lower())
        elif getattr(hh_obj, "deal", None) and getattr(hh_obj.deal, "day_of_week", None):
            dl = str(hh_obj.deal.day_of_week).lower().strip()
            if dl in ("everyday", "all", "daily"):
                return set(ALL_DAYS)
            elif dl == "weekdays":
                days.extend(["monday", "tuesday", "wednesday", "thursday", "friday"])
            elif dl == "weekends":
                days.extend(["saturday", "sunday"])
            elif dl in ALL_DAYS:
                days.append(dl)
        return set(days) if days else set(ALL_DAYS)

    active_qs = HappyHour.objects.filter(
        restaurant=restaurant,
        is_deal=True,
        status="active"
    ).order_by("created_at", "id")

    if new_hh and getattr(new_hh, "pk", None):
        active_qs = active_qs.exclude(pk=new_hh.pk)

    active_list = list(active_qs)
    new_days = expand_days(new_hh) if new_hh else set(ALL_DAYS)

    expired_ids = set()
    for day in new_days:
        deals_on_day = [d for d in active_list if d.id not in expired_ids and day in expand_days(d)]
        while len(deals_on_day) >= 2:
            oldest = deals_on_day.pop(0)
            expired_ids.add(oldest.id)

    if expired_ids:
        HappyHour.objects.filter(id__in=expired_ids).update(status="expired")


def create_standalone_happy_hour_deal(restaurant, user, role, data, is_approved=True):
    from happy_hours.models import HappyHour
    from deals.image_enhancer import enhance_uploaded_image
    import datetime

    def parse_time_value(val):
        if not val:
            return None
        if isinstance(val, datetime.time):
            return val
        s = str(val).strip()
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
            try:
                return datetime.datetime.strptime(s, fmt).time()
            except ValueError:
                pass
        try:
            return datetime.datetime.strptime(s[:5], "%H:%M").time()
        except Exception:
            return None

    s_time = (
        parse_time_value(data.get("hh_start_time"))
        or parse_time_value(data.get("start_time"))
    )
    e_time = (
        parse_time_value(data.get("hh_end_time"))
        or parse_time_value(data.get("end_time"))
    )

    if not s_time or not e_time:
        op_hours = getattr(restaurant, "operating_hours", None) or {}
        if not s_time:
            open_str = op_hours.get("open") or op_hours.get("opening_time")
            s_time = parse_time_value(open_str) or datetime.time(16, 0)

        if not e_time:
            close_str = op_hours.get("close") or op_hours.get("closing_time")
            e_time = parse_time_value(close_str) or datetime.time(18, 0)

    raw_image = data.get("image")
    happy_hour_image = None
    if raw_image:
        try:
            happy_hour_image = enhance_uploaded_image(raw_image)
        except Exception:
            happy_hour_image = raw_image

    hh_discount = (
        data.get("hh_discount_offer")
        or data.get("discount_offer")
        or data.get("discount_percentage")
        or ""
    )

    raw_event = str(data.get("hh_event_type") or "casual").lower().replace(" ", "_")
    valid_events = [c[0] for c in HappyHour.EVENT_TYPE_CHOICES]
    hh_event = raw_event if raw_event in valid_events else "casual"

    raw_vibe = str(data.get("hh_vibe") or "casual").lower().replace(" ", "_")
    valid_vibes = [c[0] for c in HappyHour.VIBE_CHOICES]
    hh_vibe = raw_vibe if raw_vibe in valid_vibes else "casual"

    status_val = "active" if is_approved else "pending"
    hh_date = data.get("hh_date") or data.get("date") or None

    raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
    if raw_days:
        if isinstance(raw_days, str):
            import json
            try:
                raw_days = json.loads(raw_days)
            except Exception:
                raw_days = [d.strip().lower() for d in raw_days.split(",") if d.strip()]
        if not isinstance(raw_days, list):
            raw_days = [str(raw_days).lower()]
        hh_days_of_week = [str(d).lower().strip() for d in raw_days if str(d).strip()]
    else:
        hh_days_of_week = ["everyday"]

    title_val = (data.get("title") or f"{restaurant.name} Happy Hour Deal")[:250]
    desc_val = data.get("description") or f"Happy Hour Deal at {restaurant.name}"
    loc_val = (data.get("location_branch") or data.get("location") or getattr(restaurant, "address", "") or getattr(restaurant, "city", "") or "")[:490]

    hh = HappyHour.objects.create(
        deal=None,
        is_deal=True,
        restaurant=restaurant,
        submitted_by=user,
        created_by_role=role,
        title=title_val,
        description=desc_val,
        group_size=None,
        event_type=hh_event,
        vibe=hh_vibe,
        date=hh_date,
        start_time=s_time,
        end_time=e_time,
        days_of_week=hh_days_of_week,
        location=loc_val,
        discount_offer=(hh_discount or "")[:250],
        status=status_val,
        is_public=True,
        image=happy_hour_image,
    )

    try:
        from deals.duplicate_detector import detect_happy_hour_duplicates
        is_dup, match_hh, score, reasons = detect_happy_hour_duplicates(hh)
        if is_dup and match_hh:
            hh.is_potential_duplicate = True
            hh.duplicate_of = match_hh
            hh.duplicate_score = score
            hh.duplicate_reasons = reasons
            hh.save(update_fields=[
                "is_potential_duplicate",
                "duplicate_of",
                "duplicate_score",
                "duplicate_reasons",
            ])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Happy hour duplicate detection error: {e}")

    # Enforce: "Each restaurant can have at most 2 active Happy Hour Deals on any given day"
    if status_val == "active":
        enforce_two_active_happy_hour_deals_rule(restaurant, hh)

    if hh.status == "active":
        send_happy_hour_notification_emails(hh)

    return hh


def create_linked_happy_hour_from_deal(deal, restaurant, user, role, data, is_approved=True):
    from happy_hours.models import HappyHour
    from django.core.files.base import ContentFile
    import datetime

    def parse_time_value(val):
        if not val:
            return None
        if isinstance(val, datetime.time):
            return val
        s = str(val).strip()
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
            try:
                return datetime.datetime.strptime(s, fmt).time()
            except ValueError:
                pass
        try:
            return datetime.datetime.strptime(s[:5], "%H:%M").time()
        except Exception:
            return None

    s_time = (
        parse_time_value(data.get("hh_start_time"))
        or parse_time_value(data.get("start_time"))
        or getattr(deal, "start_time", None)
    )
    e_time = (
        parse_time_value(data.get("hh_end_time"))
        or parse_time_value(data.get("end_time"))
        or getattr(deal, "end_time", None)
    )

    if not s_time or not e_time:
        op_hours = getattr(restaurant, "operating_hours", None) or {}
        if not s_time:
            open_str = op_hours.get("open") or op_hours.get("opening_time")
            s_time = parse_time_value(open_str) or datetime.time(16, 0)

        if not e_time:
            close_str = op_hours.get("close") or op_hours.get("closing_time")
            e_time = parse_time_value(close_str) or datetime.time(18, 0)

    happy_hour_image = None
    if deal.image:
        try:
            deal.image.open()
            happy_hour_image = ContentFile(deal.image.read(), name=deal.image.name.split("/")[-1])
        except Exception:
            happy_hour_image = None

    hh_discount = data.get("hh_discount_offer")
    if not hh_discount:
        if getattr(deal, "discount_percentage", None):
            hh_discount = f"{deal.discount_percentage}% OFF"
        elif getattr(deal, "price", None):
            hh_discount = f"${deal.price}"
        else:
            hh_discount = ""

    raw_event = str(data.get("hh_event_type") or "casual").lower().replace(" ", "_")
    valid_events = [c[0] for c in HappyHour.EVENT_TYPE_CHOICES]
    hh_event = raw_event if raw_event in valid_events else "casual"

    raw_vibe = str(data.get("hh_vibe") or "casual").lower().replace(" ", "_")
    valid_vibes = [c[0] for c in HappyHour.VIBE_CHOICES]
    hh_vibe = raw_vibe if raw_vibe in valid_vibes else "casual"

    status_val = "active" if is_approved else "pending"

    hh_date = data.get("hh_date") or None

    # Multi-day parsing for Happy Hour Deals
    raw_days = data.get("days_of_week") or data.get("hh_days_of_week")
    if raw_days:
        if isinstance(raw_days, str):
            import json
            try:
                raw_days = json.loads(raw_days)
            except Exception:
                raw_days = [d.strip().lower() for d in raw_days.split(",") if d.strip()]
        if not isinstance(raw_days, list):
            raw_days = [str(raw_days).lower()]
        hh_days_of_week = [str(d).lower().strip() for d in raw_days if str(d).strip()]
    elif getattr(deal, "day_of_week", None):
        hh_days_of_week = [deal.day_of_week]
    else:
        hh_days_of_week = ["everyday"]

    hh = HappyHour.objects.create(
        deal=deal,
        is_deal=True,
        restaurant=restaurant,
        submitted_by=user,
        created_by_role=role,
        title=(deal.title or "Happy Hour Deal")[:250],
        description=deal.description or "",
        group_size=None,
        event_type=hh_event,
        vibe=hh_vibe,
        date=hh_date,
        start_time=s_time,
        end_time=e_time,
        days_of_week=hh_days_of_week,
        location=(data.get("location_branch") or getattr(deal, "location_branch", "") or restaurant.address or restaurant.city or "")[:490],
        discount_offer=(hh_discount or "")[:250],
        status=status_val,
        is_public=True,
        image=happy_hour_image,
    )

    # Enforce: "Each restaurant can have at most 2 active Happy Hour Deals on any given day"
    if status_val == "active":
        enforce_two_active_happy_hour_deals_rule(restaurant, hh)

    if hh.status == "active":
        send_happy_hour_notification_emails(hh)

    return hh


# PUBLIC

class PublicDealListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Deal.objects.filter(
            status="active",
            restaurant__status="active",
        ).exclude(
            linked_happy_hours__is_deal=True
        ).select_related("restaurant", "submitted_by")

        restaurant_id = request.query_params.get("restaurant")
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)

        food_type = request.query_params.get("food_type")
        if food_type:
            qs = qs.filter(Q(food_type__icontains=food_type) | Q(food_type__icontains=food_type.replace("_", " ")))

        day = request.query_params.get("day_of_week")
        if day:
            qs = qs.filter(day_of_week=day)

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        is_hot = request.query_params.get("is_hot_deal")
        if is_hot in ["true", "1", "yes"]:
            qs = qs.filter(is_hot_deal=True)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(restaurant__name__icontains=search) |
                Q(food_type__icontains=search) |
                Q(location_branch__icontains=search)
            )

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class PublicDealDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant", "submitted_by").get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.views_count += 1
        deal.save(update_fields=["views_count"])

        return Response({
            "success": True,
            "data": DealDetailSerializer(deal, context={"request": request}).data,
        })


class MapDealsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = (
            Deal.objects.filter(
                status="active",
                restaurant__latitude__isnull=False,
                restaurant__longitude__isnull=False,
            )
            .exclude(restaurant__status="suspended")
            .select_related("restaurant")
        )

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        day = request.query_params.get("day")
        if day:
            qs = qs.filter(day_of_week=day)

        data = [
            {
                "id": deal.id,
                "title": deal.title,
                "restaurant_id": deal.restaurant.id,
                "restaurant_name": deal.restaurant.name,
                "latitude": deal.restaurant.latitude,
                "longitude": deal.restaurant.longitude,
                "is_hot_deal": deal.is_hot_deal,
                "price": str(deal.price) if deal.price is not None else None,
                "food_type": deal.food_type,
                "day_of_week": deal.day_of_week,
                "is_verified": bool(deal.restaurant.owner_id is not None),
                "is_registered": bool(deal.restaurant.owner_id is not None),
                "restaurant_is_verified": bool(deal.restaurant.owner_id is not None),
                "operating_hours": deal.restaurant.operating_hours,
                "time": (f"{deal.start_time.strftime('%I:%M %p')} - {deal.end_time.strftime('%I:%M %p')}" if (deal.start_time and deal.end_time) else "Open Daily"),
                "number_of_deals": deal.restaurant.deals.filter(status="active").count(),
            }
            for deal in qs
        ]

        return Response({"success": True, "data": data})
    
class TrackDealView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk)
        except Deal.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        session_id = request.data.get("session_id") or None
        user = request.user if request.user.is_authenticated else None

        # prevent spam (30 min window)
        recent = DealView.objects.filter(
            deal=deal,
            user=user,
            session_id=session_id,
            created_at__gte=timezone.now() - timedelta(minutes=30),
        ).exists()

        if recent:
            return Response({"message": "already counted"}, status=200)

        try:
            DealView.objects.create(
                deal=deal,
                user=user,
                session_id=session_id,
                ip_address=self.get_client_ip(request),
            )

            deal.views_count = (deal.views_count or 0) + 1
            deal.save(update_fields=["views_count"])

        except IntegrityError:
            # fallback safety (VERY IMPORTANT)
            return Response({"message": "duplicate ignored"}, status=200)

        return Response({"message": "view counted"}, status=201)

    def get_client_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0]
        return request.META.get("REMOTE_ADDR")

# USER

class SubmitDealView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        req_data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        raw_post_hh = req_data.get("post_to_happy_hour")
        is_hh_deal = (raw_post_hh in [True, "true", "True", "1", 1]) or bool(req_data.get("is_happy_hour_deal") in [True, "true", "True", "1", 1])
        if is_hh_deal:
            req_data['price'] = None
            req_data['discount_percentage'] = ''
            req_data['discount_offer'] = ''
            req_data['hh_discount_offer'] = ''
        elif req_data.get('price') in ['', 'null', 'None']:
            req_data['price'] = None
        serializer = SubmitDealSerializer(data=req_data, context={"request": request, "is_happy_hour_deal": is_hh_deal})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        restaurant_name = data.get("restaurant_name") or data.get("location_branch")
        restaurant = None

        if restaurant_name:
            restaurant = Restaurant.objects.filter(name__iexact=restaurant_name, status="active").first()
            if not restaurant:
                restaurant = Restaurant.objects.filter(name__icontains=restaurant_name, status="active").first()

        loc = (data.get("location_branch") or request.data.get("location_branch") or "").strip()
        raw_city = (data.get("city") or request.data.get("city") or "").strip()

        # If city is not explicitly provided, extract candidate from location_branch
        if not raw_city and loc:
            parts = [p.strip() for p in loc.split(",") if p.strip()]
            if len(parts) >= 2:
                raw_city = parts[-2] if len(parts) > 2 else parts[-1]
            else:
                raw_city = parts[0]

        city_val = (raw_city or "New York")[:250]
        address_val = (loc or city_val)[:950]
        rest_name_val = (restaurant_name or "Partner Restaurant")[:250]

        lat_val = data.get("latitude") or request.data.get("latitude") or request.data.get("lat")
        lng_val = data.get("longitude") or request.data.get("longitude") or request.data.get("lng")
        if not restaurant:
            restaurant = Restaurant.objects.create(
                name=rest_name_val,
                city=city_val,
                address=address_val,
                latitude=lat_val if lat_val is not None else None,
                longitude=lng_val if lng_val is not None else None,
                status="active",
                operating_hours={"open": "09:00", "close": "23:00"}
            )
            ensure_restaurant_coordinates(restaurant)
        elif restaurant and lat_val and lng_val and (not restaurant.latitude or not restaurant.longitude):
            restaurant.latitude = lat_val
            restaurant.longitude = lng_val
            restaurant.save(update_fields=["latitude", "longitude"])
        elif restaurant and (not restaurant.latitude or not restaurant.longitude):
            ensure_restaurant_coordinates(restaurant)

        # Check / set operating hours
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            restaurant.operating_hours = {"open": "09:00", "close": "23:00"}
            restaurant.save(update_fields=["operating_hours"])

        days_of_week_val = data.get("days_of_week") or normalize_days_of_week_input(request.data.get("days_of_week") or request.data.get("hh_days_of_week")) or ["everyday"]
        day_of_week_val = data.get("day_of_week") or compute_single_day_of_week(days_of_week_val)

        # If submitting a Happy Hour Deal, create ONLY a HappyHour record (NOT a simple Deal)
        if is_hh_deal:
            hh = create_standalone_happy_hour_deal(
                restaurant=restaurant,
                user=request.user,
                role="user",
                data=request.data if hasattr(request, "data") else data,
                is_approved=False,
            )

            admin_notif_title = "Potential Duplicate Happy Hour Deal" if hh.is_potential_duplicate else "New Happy Hour Deal Submitted"
            admin_notif_msg = f"A new Happy Hour Deal '{hh.title}' has been submitted for approval."
            if hh.is_potential_duplicate and hh.duplicate_of:
                admin_notif_msg = f"⚠️ Potential Duplicate ({int(hh.duplicate_score)}% match with #{hh.duplicate_of.id}): '{hh.title}' submitted for {restaurant.name}."

            notify_admins(
                type="happy_hour",
                title=admin_notif_title,
                message=admin_notif_msg,
                related_happy_hour=hh,
                related_restaurant=restaurant,
                metadata={"is_deal": True, "action_url": "/admin/dashboard/deals?tab=happy_hour_deals"},
            )

            if restaurant.owner:
                create_notification(
                    user=restaurant.owner,
                    type="happy_hour",
                    title="New Happy Hour Deal Submitted",
                    message=f"A customer has submitted a new Happy Hour Deal '{hh.title}' for your restaurant. It is pending admin approval.",
                    related_happy_hour=hh,
                    metadata={"is_deal": True, "action_url": "/restaurant/dashboard/res_deals?tab=happy_hour_deals"},
                )

            from happy_hours.serializers import HappyHourDetailSerializer
            return Response(
                {
                    "message": "Happy hour deal submitted successfully. Waiting for admin approval.",
                    "data": HappyHourDetailSerializer(hh, context={"request": request}).data,
                    "is_happy_hour_deal": True,
                },
                status=status.HTTP_201_CREATED,
            )

        # If creating a Happy Hour Deal, create ONLY a HappyHour record (NOT a simple Deal)
        if is_hh_deal:
            is_active_hh = (deal_status == "active")
            hh = create_standalone_happy_hour_deal(
                restaurant=restaurant,
                user=request.user,
                role="admin",
                data=request.data if hasattr(request, "data") else data,
                is_approved=is_active_hh,
            )

            if not is_active_hh:
                notify_admins(
                    type="happy_hour",
                    title="New Happy Hour Deal Submitted by Sub-Admin",
                    message=f"Sub-admin {request.user.full_name or request.user.email} submitted happy hour deal '{hh.title}' for {restaurant.name} awaiting approval.",
                    related_happy_hour=hh,
                    metadata={"is_deal": True, "action_url": "/admin/dashboard/deals?tab=happy_hour_deals"},
                )

            from happy_hours.serializers import HappyHourDetailSerializer
            return Response(
                {
                    "success": True,
                    "message": "Happy hour deal created successfully.",
                    "data": HappyHourDetailSerializer(hh, context={"request": request}).data,
                    "is_happy_hour_deal": True,
                },
                status=status.HTTP_201_CREATED,
            )

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="user",
            title=(data.get("title") or f"{restaurant.name} Deal")[:250],
            description=data.get("description"),
            price=data.get("price"),
            food_type=normalize_food_type_input(
                request.data.get("food_type") or data.get("food_type") or request.data.get("food_types") or data.get("food_types")
            ),
            day_of_week=day_of_week_val,
            days_of_week=days_of_week_val,
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=(data.get("location_branch") or "")[:490],
            discount_percentage=(
                data.get("discount_percentage")
                or data.get("discount_offer")
                or request.data.get("discount_percentage")
                or request.data.get("discount_offer")
                or ""
            )[:95],
            image=data.get("image"),
            status="pending",
        )

        # Duplicate deal detection
        try:
            from .duplicate_detector import detect_deal_duplicates
            is_dup, match_deal, score, reasons = detect_deal_duplicates(deal)
            if is_dup and match_deal:
                deal.is_potential_duplicate = True
                deal.duplicate_of = match_deal
                deal.duplicate_score = score
                deal.duplicate_reasons = reasons
                deal.save(update_fields=[
                    "is_potential_duplicate",
                    "duplicate_of",
                    "duplicate_score",
                    "duplicate_reasons",
                ])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Duplicate detection check failed: {e}")

        admin_notif_title = "Potential Duplicate Deal Submitted" if deal.is_potential_duplicate else "New Deal Submitted"
        admin_notif_msg = f"A new deal '{deal.title}' has been submitted for approval."
        if deal.is_potential_duplicate and deal.duplicate_of:
            admin_notif_msg = f"⚠️ Potential Duplicate ({int(deal.duplicate_score)}% match with #{deal.duplicate_of.id}): '{deal.title}' submitted for {restaurant.name}."

        notify_admins(
            type="deal",
            title=admin_notif_title,
            message=admin_notif_msg,
            related_deal=deal,
            related_restaurant=restaurant,
        )

        if restaurant.owner:
            create_notification(
                user=restaurant.owner,
                type="deal",
                title="New Deal Submitted",
                message=f"A customer has submitted a new deal '{deal.title}' for your restaurant. It is pending admin approval.",
                related_deal=deal,
            )


        response_serializer = DealDetailSerializer(
            deal,
            context={"request": request},
        )

        return Response(
            {
                "message": "Deal submitted successfully. Waiting for admin approval.",
                "data": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

class MyDealsView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        qs = Deal.objects.filter(submitted_by=request.user).select_related("restaurant")

        status_filter = request.query_params.get("status")
        if status_filter == "happy_hour_deals":
            qs = qs.filter(linked_happy_hours__is_deal=True).distinct()
        else:
            qs = qs.exclude(linked_happy_hours__is_deal=True)
            if status_filter and status_filter != "all":
                qs = qs.filter(status=status_filter)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({"success": True, "data": serializer.data})


class DeleteMyDealView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def delete(self, request, pk):
        try:
            deal = Deal.objects.get(pk=pk, submitted_by=request.user)
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if deal.status == "active":
            return Response(
                {"success": False, "message": "Active deals cannot be deleted by user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})


class SaveDealView(APIView):
    permission_classes = [IsAuthenticated, IsUserOrAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        saved, created = SavedDeal.objects.get_or_create(
            user=request.user,
            deal=deal,
        )

        # Sync like vote and update likes_count
        DealVote.objects.update_or_create(
            deal=deal,
            user=request.user,
            defaults={"vote_type": "like"},
        )
        deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
        deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
        deal.save(update_fields=["likes_count", "dislikes_count"])

        return Response(
            {
                "success": True,
                "message": "Deal saved to favorites",
                "is_saved": True,
                "likes_count": deal.likes_count,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class UnsaveDealView(APIView):
    permission_classes = [IsAuthenticated, IsUserOrAdmin]

    def delete(self, request, pk):
        try:
            saved = SavedDeal.objects.get(user=request.user, deal_id=pk)
            saved.delete()
        except SavedDeal.DoesNotExist:
            pass

        # Sync like vote and update likes_count
        DealVote.objects.filter(deal_id=pk, user=request.user).delete()
        deal = Deal.objects.filter(pk=pk).first()
        likes_count = 0
        if deal:
            deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
            deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
            deal.save(update_fields=["likes_count", "dislikes_count"])
            likes_count = deal.likes_count

        return Response({
            "success": True,
            "message": "Deal removed from favorites",
            "is_saved": False,
            "likes_count": likes_count,
        })


class LikeDealView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Active deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        vote = DealVote.objects.filter(deal=deal, user=request.user).first()
        if vote:
            if vote.vote_type == "like":
                # Toggle off (remove like)
                vote.delete()
                SavedDeal.objects.filter(deal=deal, user=request.user).delete()
                deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
                deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
                deal.save(update_fields=["likes_count", "dislikes_count"])
                return Response({
                    "success": True,
                    "action": "unliked",
                    "user_vote": None,
                    "is_saved": False,
                    "likes_count": deal.likes_count,
                    "dislikes_count": deal.dislikes_count,
                    "message": "Like removed",
                })
            else:
                # Switch from dislike to like
                vote.vote_type = "like"
                vote.save(update_fields=["vote_type", "updated_at"])
                SavedDeal.objects.get_or_create(deal=deal, user=request.user)
                deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
                deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
                deal.save(update_fields=["likes_count", "dislikes_count"])
                return Response({
                    "success": True,
                    "action": "liked",
                    "user_vote": "like",
                    "is_saved": True,
                    "likes_count": deal.likes_count,
                    "dislikes_count": deal.dislikes_count,
                    "message": "Deal liked",
                })
        else:
            # New like
            DealVote.objects.create(deal=deal, user=request.user, vote_type="like")
            SavedDeal.objects.get_or_create(deal=deal, user=request.user)
            deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
            deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
            deal.save(update_fields=["likes_count", "dislikes_count"])
            return Response({
                "success": True,
                "action": "liked",
                "user_vote": "like",
                "is_saved": True,
                "likes_count": deal.likes_count,
                "dislikes_count": deal.dislikes_count,
                "message": "Deal liked",
            }, status=status.HTTP_200_OK)


class DislikeDealView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                status="active",
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Active deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        vote = DealVote.objects.filter(deal=deal, user=request.user).first()
        if vote:
            if vote.vote_type == "dislike":
                # Toggle off (remove dislike)
                vote.delete()
                deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
                deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
                deal.save(update_fields=["likes_count", "dislikes_count"])
                return Response({
                    "success": True,
                    "action": "undisliked",
                    "user_vote": None,
                    "likes_count": deal.likes_count,
                    "dislikes_count": deal.dislikes_count,
                    "message": "Dislike removed",
                })
            else:
                # Switch from like to dislike
                vote.vote_type = "dislike"
                vote.save(update_fields=["vote_type", "updated_at"])
                deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
                deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
                deal.save(update_fields=["likes_count", "dislikes_count"])
                return Response({
                    "success": True,
                    "action": "disliked",
                    "user_vote": "dislike",
                    "likes_count": deal.likes_count,
                    "dislikes_count": deal.dislikes_count,
                    "message": "Deal disliked",
                })
        else:
            # New dislike
            DealVote.objects.create(deal=deal, user=request.user, vote_type="dislike")
            deal.likes_count = DealVote.objects.filter(deal=deal, vote_type="like").count()
            deal.dislikes_count = DealVote.objects.filter(deal=deal, vote_type="dislike").count()
            deal.save(update_fields=["likes_count", "dislikes_count"])
            return Response({
                "success": True,
                "action": "disliked",
                "user_vote": "dislike",
                "likes_count": deal.likes_count,
                "dislikes_count": deal.dislikes_count,
                "message": "Deal disliked",
            }, status=status.HTTP_200_OK)


class VerifyDealAccuracyView(APIView):
    """
    Crowdsourced Deal Accuracy Verification.
    Replaces negative downvoting with a positive/outdated check:
    'Is this deal still accurate / available?' (Yes, it's live / No, it's not)
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                status__in=["active", "upcoming", "pending"],
                restaurant__status="active",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found or not active"},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_accurate_raw = request.data.get("is_accurate")
        if is_accurate_raw is None:
            return Response(
                {"success": False, "message": "is_accurate (boolean) is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_accurate = bool(is_accurate_raw)

        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        session_id = None
        if hasattr(request, "session"):
            if not request.session.session_key:
                try:
                    request.session.save()
                except Exception:
                    pass
            session_id = request.session.session_key

        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
        if ip_address and "," in ip_address:
            ip_address = ip_address.split(",")[0].strip()

        # Find existing vote by user, session, or IP
        existing_vote = None
        if user:
            existing_vote = DealAccuracyVote.objects.filter(deal=deal, user=user).first()
        elif session_id:
            existing_vote = DealAccuracyVote.objects.filter(deal=deal, session_id=session_id).first()
        elif ip_address:
            existing_vote = DealAccuracyVote.objects.filter(deal=deal, ip_address=ip_address).first()

        if existing_vote:
            if existing_vote.is_accurate == is_accurate:
                # Toggle off (unvote)
                existing_vote.delete()
                user_vote = None
                action = "unvoted"
            else:
                # Switch vote
                existing_vote.is_accurate = is_accurate
                if user and not existing_vote.user:
                    existing_vote.user = user
                existing_vote.save(update_fields=["is_accurate", "updated_at"] + (["user"] if user else []))
                user_vote = "accurate" if is_accurate else "inaccurate"
                action = "switched"
        else:
            # Create new vote
            DealAccuracyVote.objects.create(
                deal=deal,
                user=user,
                session_id=session_id,
                ip_address=ip_address,
                is_accurate=is_accurate,
            )
            user_vote = "accurate" if is_accurate else "inaccurate"
            action = "voted"

        # Update deal aggregates
        deal.accurate_votes_count = DealAccuracyVote.objects.filter(deal=deal, is_accurate=True).count()
        deal.inaccurate_votes_count = DealAccuracyVote.objects.filter(deal=deal, is_accurate=False).count()
        deal.is_reported_inaccurate = deal.inaccurate_votes_count > 0
        deal.last_verified_at = timezone.now()

        # Sync with legacy likes/dislikes counters for search/filtering
        deal.dislikes_count = deal.inaccurate_votes_count
        deal.save(update_fields=[
            "accurate_votes_count",
            "inaccurate_votes_count",
            "is_reported_inaccurate",
            "last_verified_at",
            "dislikes_count",
        ])

        return Response({
            "success": True,
            "action": action,
            "user_accuracy_vote": user_vote,
            "accurate_votes_count": deal.accurate_votes_count,
            "inaccurate_votes_count": deal.inaccurate_votes_count,
            "is_reported_inaccurate": deal.is_reported_inaccurate,
            "message": (
                "Thank you! You verified this deal is still live." if user_vote == "accurate"
                else "Thank you for the update! We've flagged this deal for admin review." if user_vote == "inaccurate"
                else "Verification vote removed."
            ),
        }, status=status.HTTP_200_OK)


class SavedDealsView(APIView):
    permission_classes = [IsAuthenticated, IsUserOrAdmin]

    def get(self, request):
        saved = SavedDeal.objects.filter(user=request.user, deal__restaurant__status="active").select_related(
            "deal__restaurant"
        )

        search = request.query_params.get("search")
        if search:
            saved = saved.filter(deal__title__icontains=search)

        serializer = SavedDealSerializer(saved, many=True, context={"request": request})

        return Response({"success": True, "data": serializer.data})


# RESTAURANT

class RestaurantDealListView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = Deal.objects.filter(restaurant=restaurant).exclude(linked_happy_hours__is_deal=True).select_related("submitted_by")

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class RestaurantCreateDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "Please set your restaurant's operating hours in your profile settings before creating a deal."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check Free tier 5 submissions limit
        is_premium = (restaurant.subscription_plan or "").lower() == "premium"
        if not is_premium:
            from happy_hours.models import HappyHour
            total_submissions = (
                Deal.objects.filter(restaurant=restaurant).count()
                + HappyHour.objects.filter(restaurant=restaurant, deal__isnull=True).count()
            )
            if total_submissions >= 5:
                return Response(
                    {
                        "success": False,
                        "message": "Free tier limit reached (5 deals & happy hours). Please upgrade to the Premium Plan ($99/mo) for unlimited submissions.",
                        "limit_reached": True,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        req_data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        raw_post_hh = req_data.get("post_to_happy_hour")
        is_hh_deal = (raw_post_hh in [True, "true", "True", "1", 1]) or bool(req_data.get("is_happy_hour_deal") in [True, "true", "True", "1", 1])
        if is_hh_deal:
            req_data['price'] = None
            req_data['discount_percentage'] = ''
            req_data['discount_offer'] = ''
            req_data['hh_discount_offer'] = ''
        else:
            if req_data.get('price') in ['', 'null', 'None']:
                req_data['price'] = None
            if not req_data.get('discount_percentage') and (req_data.get('discount_offer') or req_data.get('hh_discount_offer')):
                req_data['discount_percentage'] = req_data.get('discount_offer') or req_data.get('hh_discount_offer')
        raw_food = req_data.get('food_type') if 'food_type' in req_data else req_data.get('food_types')
        if raw_food is not None:
            req_data['food_type'] = normalize_food_type_input(raw_food)
        req_data.pop('food_types', None)
        raw_days = req_data.get('days_of_week') or req_data.get('hh_days_of_week')
        if raw_days is not None:
            norm_days = normalize_days_of_week_input(raw_days)
            req_data['days_of_week'] = norm_days
            req_data['day_of_week'] = compute_single_day_of_week(norm_days)
        elif 'day_of_week' in req_data:
            day_norm = normalize_days_of_week_input(req_data['day_of_week'])
            req_data['day_of_week'] = compute_single_day_of_week(day_norm)
            req_data['days_of_week'] = day_norm or [req_data['day_of_week']]
        if 'image' in req_data and isinstance(req_data['image'], str):
            del req_data['image']
        serializer = CreateDealSerializer(data=req_data, context={"request": request, "is_happy_hour_deal": is_hh_deal})

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # If submitting a Happy Hour Deal, create ONLY a HappyHour record (NOT a simple Deal)
        if is_hh_deal:
            hh = create_standalone_happy_hour_deal(
                restaurant=restaurant,
                user=request.user,
                role="restaurant",
                data=request.data if hasattr(request, "data") else req_data,
                is_approved=True,
            )

            notify_admins(
                type="happy_hour",
                title="New Happy Hour Deal Created",
                message=f"Restaurant '{restaurant.name}' created a new happy hour deal '{hh.title}'.",
                related_happy_hour=hh,
                related_restaurant=restaurant,
            )

            from happy_hours.serializers import HappyHourDetailSerializer
            return Response(
                {
                    "success": True,
                    "message": "Happy hour deal created successfully.",
                    "data": HappyHourDetailSerializer(hh, context={"request": request}).data,
                    "is_happy_hour_deal": True,
                },
                status=status.HTTP_201_CREATED,
            )

        deal = serializer.save(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="restaurant",
            status="active",
        )

        try:
            from .duplicate_detector import detect_deal_duplicates
            is_dup, match_deal, score, reasons = detect_deal_duplicates(deal)
            if is_dup and match_deal:
                deal.is_potential_duplicate = True
                deal.duplicate_of = match_deal
                deal.duplicate_score = score
                deal.duplicate_reasons = reasons
                deal.save(update_fields=[
                    "is_potential_duplicate",
                    "duplicate_of",
                    "duplicate_score",
                    "duplicate_reasons",
                ])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Duplicate detection check failed: {e}")

        send_deal_notification_emails(deal)

        notify_admins(
            type="deal",
            title="New Deal Created",
            message=f"Restaurant '{restaurant.name}' created a new deal '{deal.title}'.",
            related_deal=deal,
            related_restaurant=restaurant,
        )

        return Response(
            {
                "success": True,
                "message": "Deal created successfully.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RestaurantUpdateDeleteDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_deal(self, pk, user):
        try:
            return Deal.objects.get(
                pk=pk,
                restaurant__owner=user,
                created_by_role="restaurant",
            )
        except Deal.DoesNotExist:
            return None

    def put(self, request, pk):
        deal = self.get_deal(pk, request.user)

        if not deal:
            return Response(
                {
                    "success": False,
                    "message": "Deal not found or you cannot edit customer-submitted deal.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if hasattr(request.data, "dict"):
            req_data = request.data.dict()
        elif hasattr(request.data, "copy"):
            req_data = request.data.copy()
        else:
            req_data = dict(request.data)

        raw_post_hh = req_data.get("post_to_happy_hour")
        is_hh_deal = (
            raw_post_hh in [True, "true", "True", "1", 1]
            or bool(req_data.get("is_happy_hour_deal") in [True, "true", "True", "1", 1])
            or deal.linked_happy_hours.exists()
        )
        if is_hh_deal:
            req_data['price'] = None
            req_data['discount_percentage'] = ''
            req_data['discount_offer'] = ''
            req_data['hh_discount_offer'] = ''
        else:
            if req_data.get('price') in ['', 'null', 'None']:
                req_data['price'] = None
            if not req_data.get('discount_percentage') and (req_data.get('discount_offer') or req_data.get('hh_discount_offer')):
                req_data['discount_percentage'] = req_data.get('discount_offer') or req_data.get('hh_discount_offer')
        raw_food = req_data.get('food_type') if 'food_type' in req_data else req_data.get('food_types')
        if raw_food is not None:
            req_data['food_type'] = normalize_food_type_input(raw_food)
        req_data.pop('food_types', None)
        raw_days = req_data.get('days_of_week') or req_data.get('hh_days_of_week')
        if raw_days is not None:
            norm_days = normalize_days_of_week_input(raw_days)
            req_data['days_of_week'] = norm_days
            req_data['day_of_week'] = compute_single_day_of_week(norm_days)
        elif 'day_of_week' in req_data:
            day_norm = normalize_days_of_week_input(req_data['day_of_week'])
            req_data['day_of_week'] = compute_single_day_of_week(day_norm)
            req_data['days_of_week'] = day_norm or [req_data['day_of_week']]
        if 'image' in req_data and isinstance(req_data['image'], str):
            del req_data['image']
        serializer = CreateDealSerializer(deal, data=req_data, partial=True, context={"request": request, "is_happy_hour_deal": is_hh_deal})

        if serializer.is_valid():
            new_status = deal.status if deal.status in ["active", "draft", "cancelled"] else "active"
            serializer.save(status=new_status, rejection_reason="")

            return Response({
                "success": True,
                "message": "Deal updated successfully.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            })

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):
        deal = self.get_deal(pk, request.user)

        if not deal:
            return Response(
                {
                    "success": False,
                    "message": "Deal not found or you cannot delete customer-submitted deal.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})


class RestaurantApproveDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                restaurant__owner=request.user,
                status="pending",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found or not pending approval"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.status = "active"
        deal.rejection_reason = ""
        deal.save(update_fields=["status", "rejection_reason"])

        if deal.submitted_by:
            from accounts.models import PointsTransaction
            submitter = deal.submitted_by
            submitter.points += 50
            submitter.save(update_fields=["points"])
            PointsTransaction.objects.create(
                user=submitter,
                text=f"Deal submitted - {deal.title}",
                status="approved",
                points=50,
            )
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Approved! 🎉",
                message=f"Your deal '{deal.title}' has been approved by the restaurant.",
                related_deal=deal,
            )

        from happy_hours.models import HappyHour
        for hh in HappyHour.objects.filter(deal=deal, status="pending"):
            enforce_two_active_happy_hour_deals_rule(deal.restaurant, hh)
            hh.status = "active"
            hh.rejection_reason = ""
            hh.accepted_at = timezone.now()
            hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])
            send_happy_hour_notification_emails(hh)

        send_deal_notification_emails(deal)

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' approved successfully",
        })


class RestaurantRejectDealView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def post(self, request, pk):
        try:
            deal = Deal.objects.get(
                pk=pk,
                restaurant__owner=request.user,
                status="pending",
            )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found or not pending approval"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RejectDealSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.status = "rejected"
        deal.rejection_reason = serializer.validated_data.get("rejection_reason", "Rejected by restaurant")
        deal.save(update_fields=["status", "rejection_reason"])

        from happy_hours.models import HappyHour
        HappyHour.objects.filter(deal=deal, status="pending").update(
            status="rejected",
            rejection_reason=deal.rejection_reason,
            rejected_at=timezone.now()
        )

        if deal.submitted_by:
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Rejected",
                message=f"Your deal '{deal.title}' was rejected by the restaurant. Reason: {deal.rejection_reason}",
                related_deal=deal,
            )

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' rejected",
        })

# ADMIN

class AdminCreateDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        if hasattr(request.data, "dict"):
            req_data = request.data.dict()
        elif hasattr(request.data, "copy"):
            req_data = request.data.copy()
        else:
            req_data = dict(request.data)

        raw_post_hh = req_data.get("post_to_happy_hour")
        is_hh_deal = (raw_post_hh in [True, "true", "True", "1", 1]) or bool(req_data.get("is_happy_hour_deal") in [True, "true", "True", "1", 1])
        if is_hh_deal:
            req_data['price'] = None
            req_data['discount_percentage'] = ''
            req_data['discount_offer'] = ''
            req_data['hh_discount_offer'] = ''
        else:
            if req_data.get('price') in ['', 'null', 'None']:
                req_data['price'] = None
            if not req_data.get('discount_percentage') and (req_data.get('discount_offer') or req_data.get('hh_discount_offer')):
                req_data['discount_percentage'] = req_data.get('discount_offer') or req_data.get('hh_discount_offer')
        serializer = AdminCreateDealSerializer(data=req_data, context={"request": request, "is_happy_hour_deal": is_hh_deal})

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        restaurant_name = data["restaurant_name"]
        restaurant = Restaurant.objects.filter(
            name__iexact=restaurant_name,
            status="active",
        ).first()
        if not restaurant:
            restaurant = Restaurant.objects.filter(
                name__icontains=restaurant_name,
                status="active",
            ).first()

        deal_status = "active"
        if request.user.is_employee_admin:
            if restaurant and restaurant.registered_by_id == request.user.id:
                deal_status = "active"
            else:
                deal_status = "pending"
        elif request.user.is_super_admin:
            deal_status = "active"

        loc = (data.get("location_branch") or request.data.get("location_branch") or "").strip()
        raw_city = (data.get("city") or request.data.get("city") or "").strip()

        # If city is not explicitly provided, extract candidate from location_branch
        if not raw_city and loc:
            parts = [p.strip() for p in loc.split(",") if p.strip()]
            if len(parts) >= 2:
                raw_city = parts[-2] if len(parts) > 2 else parts[-1]
            else:
                raw_city = parts[0]

        city_val = (raw_city or "New York")[:250]
        address_val = (loc or city_val)[:950]
        rest_name_val = (restaurant_name or "Partner Restaurant")[:250]

        lat_val = data.get("latitude") or request.data.get("latitude") or request.data.get("lat")
        lng_val = data.get("longitude") or request.data.get("longitude") or request.data.get("lng")
        if not restaurant:
            restaurant = Restaurant.objects.create(
                name=rest_name_val,
                city=city_val,
                address=address_val,
                latitude=lat_val if lat_val is not None else None,
                longitude=lng_val if lng_val is not None else None,
                status="active",
                operating_hours={"open": "09:00", "close": "23:00"},
                registered_by=request.user if request.user.is_employee_admin else None
            )
            ensure_restaurant_coordinates(restaurant)
        elif restaurant and lat_val and lng_val and (not restaurant.latitude or not restaurant.longitude):
            restaurant.latitude = lat_val
            restaurant.longitude = lng_val
            restaurant.save(update_fields=["latitude", "longitude"])
        elif restaurant and (not restaurant.latitude or not restaurant.longitude):
            ensure_restaurant_coordinates(restaurant)
            if request.user.is_employee_admin:
                deal_status = "active"

        # Check / set operating hours
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            restaurant.operating_hours = {"open": "09:00", "close": "23:00"}
            restaurant.save(update_fields=["operating_hours"])

        days_of_week_val = data.get("days_of_week") or normalize_days_of_week_input(request.data.get("days_of_week") or request.data.get("hh_days_of_week")) or ["everyday"]
        day_of_week_val = data.get("day_of_week") or compute_single_day_of_week(days_of_week_val)

        # If creating a Happy Hour Deal, create ONLY a HappyHour record (NOT a simple Deal)
        if is_hh_deal:
            is_active_hh = (deal_status == "active")
            hh = create_standalone_happy_hour_deal(
                restaurant=restaurant,
                user=request.user,
                role="admin",
                data=request.data if hasattr(request, "data") else data,
                is_approved=is_active_hh,
            )

            if not is_active_hh:
                notify_admins(
                    type="happy_hour",
                    title="New Happy Hour Deal Submitted by Sub-Admin",
                    message=f"Sub-admin {request.user.full_name or request.user.email} submitted happy hour deal '{hh.title}' for {restaurant.name} awaiting approval.",
                    related_happy_hour=hh,
                    metadata={"is_deal": True, "action_url": "/admin/dashboard/deals?tab=happy_hour_deals"},
                )

            from happy_hours.serializers import HappyHourDetailSerializer
            return Response(
                {
                    "success": True,
                    "message": "Happy hour deal created successfully.",
                    "data": HappyHourDetailSerializer(hh, context={"request": request}).data,
                    "is_happy_hour_deal": True,
                },
                status=status.HTTP_201_CREATED,
            )

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="admin",
            title=(data.get("title") or f"{restaurant.name} Deal")[:250],
            description=data.get("description"),
            price=None if is_hh_deal else data.get("price"),
            food_type=normalize_food_type_input(
                request.data.get("food_type") or data.get("food_type") or request.data.get("food_types") or data.get("food_types")
            ),
            day_of_week=day_of_week_val,
            days_of_week=days_of_week_val,
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=(data.get("location_branch") or "")[:490],
            discount_percentage="" if is_hh_deal else (
                data.get("discount_percentage")
                or request.data.get("discount_percentage")
                or request.data.get("discount_offer")
                or request.data.get("hh_discount_offer")
                or ""
            )[:95],
            image=data.get("image"),
            is_hot_deal=data.get("is_hot_deal", False),
            expires_at=data.get("expires_at"),
            status=deal_status,
        )

        try:
            from .duplicate_detector import detect_deal_duplicates
            is_dup, match_deal, score, reasons = detect_deal_duplicates(deal)
            if is_dup and match_deal:
                deal.is_potential_duplicate = True
                deal.duplicate_of = match_deal
                deal.duplicate_score = score
                deal.duplicate_reasons = reasons
                deal.save(update_fields=[
                    "is_potential_duplicate",
                    "duplicate_of",
                    "duplicate_score",
                    "duplicate_reasons",
                ])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Admin deal duplicate detection check failed: {e}")

        if deal.status == "active":
            send_deal_notification_emails(deal)
        else:
            notify_admins(
                type="deal",
                title="New Deal Submitted by Sub-Admin",
                message=f"Sub-admin {request.user.full_name or request.user.email} submitted deal '{deal.title}' for {restaurant.name} awaiting approval.",
                related_deal=deal,
            )
            if restaurant.owner:
                create_notification(
                    user=restaurant.owner,
                    type="deal",
                    title="New Deal Submitted for Approval",
                    message=f"A new deal '{deal.title}' was submitted for your restaurant and is pending approval.",
                    related_deal=deal,
                )

        return Response(
            {
                "success": True,
                "message": (
                    "Deal created successfully."
                    if deal.status == "active"
                    else "Deal submitted for approval."
                ),
                "data": DealListSerializer(
                    deal,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminUpdateDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant", "submitted_by").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                if deal.submitted_by_id == request.user.id:
                    return deal
                return None
            return deal
        except Deal.DoesNotExist:
            return None

    def get(self, request, pk):
        deal = self.get_object(request, pk)
        if not deal:
            return Response(
                {"success": False, "message": "Deal not found or access denied."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "success": True,
            "data": DealListSerializer(deal, context={"request": request}).data,
        })

    def put(self, request, pk):
        deal = self.get_object(request, pk)
        if not deal:
            return Response(
                {"success": False, "message": "Deal not found or access denied."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if hasattr(request.data, "dict"):
            req_data = request.data.dict()
        elif hasattr(request.data, "copy"):
            req_data = request.data.copy()
        else:
            req_data = dict(request.data)

        raw_post_hh = req_data.get("post_to_happy_hour")
        is_hh_deal = (
            raw_post_hh in [True, "true", "True", "1", 1]
            or bool(req_data.get("is_happy_hour_deal") in [True, "true", "True", "1", 1])
            or deal.linked_happy_hours.exists()
        )
        if is_hh_deal:
            req_data['price'] = None
            req_data['discount_percentage'] = ''
            req_data['discount_offer'] = ''
            req_data['hh_discount_offer'] = ''
        else:
            if req_data.get("price") in ["", "null", "None"]:
                req_data["price"] = None
            if not req_data.get("discount_percentage") and (req_data.get("discount_offer") or req_data.get("hh_discount_offer")):
                req_data["discount_percentage"] = req_data.get("discount_offer") or req_data.get("hh_discount_offer")
        raw_food = req_data.get("food_type") if "food_type" in req_data else req_data.get("food_types")
        if raw_food is not None:
            req_data["food_type"] = normalize_food_type_input(raw_food)
        req_data.pop("food_types", None)
        raw_days = req_data.get("days_of_week") or req_data.get("hh_days_of_week")
        if raw_days is not None:
            norm_days = normalize_days_of_week_input(raw_days)
            req_data["days_of_week"] = norm_days
            req_data["day_of_week"] = compute_single_day_of_week(norm_days)
        elif "day_of_week" in req_data:
            day_norm = normalize_days_of_week_input(req_data["day_of_week"])
            req_data["day_of_week"] = compute_single_day_of_week(day_norm)
            req_data["days_of_week"] = day_norm or [req_data["day_of_week"]]
        if "image" in req_data and isinstance(req_data["image"], str):
            del req_data["image"]

        serializer = AdminUpdateDealSerializer(deal, data=req_data, partial=True, context={"request": request, "is_happy_hour_deal": is_hh_deal})
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_deal = serializer.save()

        # Keep any linked Happy Hour synced with updated fields
        from happy_hours.models import HappyHour
        linked_hhs = HappyHour.objects.filter(deal=updated_deal)
        for hh in linked_hhs:
            update_fields = []
            if "title" in serializer.validated_data:
                hh.title = updated_deal.title
                update_fields.append("title")
            if "description" in serializer.validated_data:
                hh.description = updated_deal.description or ""
                update_fields.append("description")
            if "start_time" in serializer.validated_data and updated_deal.start_time:
                hh.start_time = updated_deal.start_time
                update_fields.append("start_time")
            if "end_time" in serializer.validated_data and updated_deal.end_time:
                hh.end_time = updated_deal.end_time
                update_fields.append("end_time")
            if "location_branch" in serializer.validated_data:
                hh.location = updated_deal.location_branch
                update_fields.append("location")
            if "discount_percentage" in serializer.validated_data and updated_deal.discount_percentage:
                hh.discount_offer = f"{updated_deal.discount_percentage}% OFF"
                update_fields.append("discount_offer")
            if "status" in serializer.validated_data:
                hh.status = updated_deal.status
                update_fields.append("status")
            raw_days = request.data.get("days_of_week") or request.data.get("hh_days_of_week")
            if raw_days:
                import json
                if isinstance(raw_days, str):
                    try:
                        raw_days = json.loads(raw_days)
                    except Exception:
                        raw_days = [d.strip().lower() for d in raw_days.split(",") if d.strip()]
                if isinstance(raw_days, list):
                    hh.days_of_week = [str(d).lower().strip() for d in raw_days if str(d).strip()]
                    update_fields.append("days_of_week")
            if update_fields:
                hh.save(update_fields=update_fields)

        return Response({
            "success": True,
            "message": "Deal updated successfully.",
            "data": DealListSerializer(updated_deal, context={"request": request}).data,
        })


class AdminDealListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = Deal.objects.select_related("restaurant", "submitted_by").filter(restaurant__status="active")

        if request.user.is_employee_admin:
            qs = qs.filter(Q(restaurant__registered_by=request.user) | Q(submitted_by=request.user))
        elif request.user.is_super_admin:
            registered_by_param = request.query_params.get("registered_by")
            if registered_by_param:
                qs = qs.filter(restaurant__registered_by_id=registered_by_param)

        status_filter = request.query_params.get("status")
        if status_filter == "duplicates" or request.query_params.get("duplicates") in ["true", "1"]:
            qs = qs.filter(is_potential_duplicate=True).exclude(linked_happy_hours__is_deal=True)
        elif status_filter == "reported_inaccurate" or request.query_params.get("reported_inaccurate") in ["true", "1"]:
            qs = qs.filter(
                Q(is_reported_inaccurate=True) | Q(inaccurate_votes_count__gt=0) | Q(dislikes_count__gt=0)
            ).exclude(linked_happy_hours__is_deal=True)
        elif status_filter == "happy_hour_deals":
            qs = qs.filter(linked_happy_hours__is_deal=True).distinct()
        else:
            qs = qs.exclude(linked_happy_hours__is_deal=True)
            if status_filter and status_filter != "all":
                qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        food_type = request.query_params.get("food_type")
        if food_type:
            qs = qs.filter(Q(food_type__icontains=food_type) | Q(food_type__icontains=food_type.replace("_", " ")))

        restaurant = request.query_params.get("restaurant")
        if restaurant:
            qs = qs.filter(restaurant_id=restaurant)

        serializer = DealListSerializer(qs, many=True, context={"request": request})

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class AdminApproveDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk, status="pending")
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied. You can only approve deals for restaurants registered under your reference."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except (Deal.DoesNotExist, ValueError):
            from happy_hours.models import HappyHour
            hh_pk = int(str(pk).replace("hh-", "")) if str(pk).startswith("hh-") or str(pk).isdigit() else None
            if hh_pk:
                try:
                    hh = HappyHour.objects.select_related("restaurant", "submitted_by", "restaurant__owner").get(pk=hh_pk, is_deal=True, status="pending")
                    if request.user.is_employee_admin and hh.restaurant.registered_by_id != request.user.id:
                        return Response(
                            {"success": False, "message": "Permission denied. You can only approve deals for restaurants registered under your reference."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    enforce_two_active_happy_hour_deals_rule(hh.restaurant, hh)
                    hh.status = "active"
                    hh.rejection_reason = ""
                    hh.accepted_at = timezone.now()
                    hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])

                    if hh.submitted_by:
                        from accounts.models import PointsTransaction
                        submitter = hh.submitted_by
                        submitter.points += 50
                        submitter.save(update_fields=["points"])
                        PointsTransaction.objects.create(
                            user=submitter,
                            text=f"Deal submitted - {hh.title}",
                            status="approved",
                            points=50,
                        )
                        create_notification(
                            user=hh.submitted_by,
                            type="deal",
                            title="Deal Approved! 🎉",
                            message=f"Your Happy Hour Deal '{hh.title}' has been approved.",
                            related_happy_hour=hh,
                        )
                    if hh.restaurant.owner and hh.restaurant.owner != hh.submitted_by:
                        create_notification(
                            user=hh.restaurant.owner,
                            type="deal",
                            title="Deal Approved! 🎉",
                            message=f"Happy Hour Deal '{hh.title}' has been approved.",
                            related_happy_hour=hh,
                        )
                    send_happy_hour_notification_emails(hh)
                    return Response({
                        "success": True,
                        "message": f"Happy Hour Deal '{hh.title}' approved",
                    })
                except HappyHour.DoesNotExist:
                    pass

            return Response(
                {"success": False, "message": "Deal not found or not pending approval"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.status = "active"
        deal.rejection_reason = ""
        deal.save(update_fields=["status", "rejection_reason"])

        if deal.submitted_by:
            from accounts.models import PointsTransaction
            submitter = deal.submitted_by
            submitter.points += 50
            submitter.save(update_fields=["points"])
            PointsTransaction.objects.create(
                user=submitter,
                text=f"Deal submitted - {deal.title}",
                status="approved",
                points=50
            )

        if deal.submitted_by:
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Approved! 🎉",
                message=f"Your deal '{deal.title}' has been approved.",
                related_deal=deal,
            )
        if deal.restaurant.owner and deal.restaurant.owner != deal.submitted_by:
            create_notification(
                user=deal.restaurant.owner,
                type="deal",
                title="Deal Approved! 🎉",
                message=f"Your deal '{deal.title}' has been approved.",
                related_deal=deal,
            )
        from happy_hours.models import HappyHour
        for hh in HappyHour.objects.filter(deal=deal, status="pending"):
            enforce_two_active_happy_hour_deals_rule(deal.restaurant, hh)
            hh.status = "active"
            hh.rejection_reason = ""
            hh.accepted_at = timezone.now()
            hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])
            send_happy_hour_notification_emails(hh)

        send_deal_notification_emails(deal)

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' approved",
        })
        
class AdminToggleHotDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.is_hot_deal = not deal.is_hot_deal
        deal.save(update_fields=["is_hot_deal"])

        return Response({
            "success": True,
            "message": "Deal marked as hot" if deal.is_hot_deal else "Deal removed from hot deals",
            "is_hot_deal": deal.is_hot_deal,
        })


class AdminRejectDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied. You can only reject deals for restaurants registered under your reference."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except (Deal.DoesNotExist, ValueError):
            from happy_hours.models import HappyHour
            hh_pk = int(str(pk).replace("hh-", "")) if str(pk).startswith("hh-") or str(pk).isdigit() else None
            if hh_pk:
                try:
                    hh = HappyHour.objects.select_related("restaurant", "submitted_by", "restaurant__owner").get(pk=hh_pk, is_deal=True)
                    if request.user.is_employee_admin and hh.restaurant.registered_by_id != request.user.id:
                        return Response(
                            {"success": False, "message": "Permission denied. You can only reject deals for restaurants registered under your reference."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    serializer = RejectDealSerializer(data=request.data)
                    if not serializer.is_valid():
                        return Response(
                            {"success": False, "errors": serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    hh.status = "rejected"
                    hh.rejection_reason = serializer.validated_data["rejection_reason"]
                    hh.rejected_at = timezone.now()
                    hh.save(update_fields=["status", "rejection_reason", "rejected_at"])
                    if hh.submitted_by:
                        create_notification(
                            user=hh.submitted_by,
                            type="deal",
                            title="Deal Rejected",
                            message=f"Your Happy Hour Deal '{hh.title}' was rejected. Reason: {hh.rejection_reason}",
                            related_happy_hour=hh,
                        )
                    if hh.restaurant.owner and hh.restaurant.owner != hh.submitted_by:
                        create_notification(
                            user=hh.restaurant.owner,
                            type="deal",
                            title="Deal Rejected",
                            message=f"Happy Hour Deal '{hh.title}' was rejected. Reason: {hh.rejection_reason}",
                            related_happy_hour=hh,
                        )
                    return Response({
                        "success": True,
                        "message": f"Happy Hour Deal '{hh.title}' rejected",
                    })
                except HappyHour.DoesNotExist:
                    pass
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RejectDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal.status = "rejected"
        deal.rejection_reason = serializer.validated_data["rejection_reason"]
        deal.save(update_fields=["status", "rejection_reason"])

        from happy_hours.models import HappyHour
        HappyHour.objects.filter(deal=deal, status="pending").update(
            status="rejected",
            rejection_reason=deal.rejection_reason,
            rejected_at=timezone.now()
        )

        if deal.submitted_by:
            create_notification(
                user=deal.submitted_by,
                type="deal",
                title="Deal Rejected",
                message=f"Your deal '{deal.title}' was rejected. Reason: {deal.rejection_reason}",
                related_deal=deal,
            )
        if deal.restaurant.owner and deal.restaurant.owner != deal.submitted_by:
            create_notification(
                user=deal.restaurant.owner,
                type="deal",
                title="Deal Rejected",
                message=f"Your deal '{deal.title}' was rejected. Reason: {deal.rejection_reason}",
                related_deal=deal,
            )

        return Response({
            "success": True,
            "message": f"Deal '{deal.title}' rejected",
        })


class AdminAcceptAllDealsView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        # Safeguard: Exclude flagged potential duplicates from bulk auto-accept to ensure manual admin review
        pending_qs = Deal.objects.filter(status="pending", is_potential_duplicate=False).select_related("restaurant")
        if request.user.is_employee_admin:
            pending_qs = pending_qs.filter(restaurant__registered_by=request.user)
        pending = list(pending_qs)
        count = len(pending)

        skipped_duplicates = Deal.objects.filter(status="pending", is_potential_duplicate=True).count()

        Deal.objects.filter(id__in=[d.id for d in pending]).update(status="active", rejection_reason="")

        from happy_hours.models import HappyHour
        for deal in pending:
            deal.status = "active"
            send_deal_notification_emails(deal)
            for hh in HappyHour.objects.filter(deal=deal, status="pending"):
                enforce_two_active_happy_hour_deals_rule(deal.restaurant, hh)
                hh.status = "active"
                hh.rejection_reason = ""
                hh.accepted_at = timezone.now()
                hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])
                send_happy_hour_notification_emails(hh)

        standalone_pending_hhs = list(HappyHour.objects.filter(is_deal=True, status="pending", is_potential_duplicate=False).select_related("restaurant"))
        if request.user.is_employee_admin:
            standalone_pending_hhs = [h for h in standalone_pending_hhs if h.restaurant.registered_by_id == request.user.id]
        for hh in standalone_pending_hhs:
            enforce_two_active_happy_hour_deals_rule(hh.restaurant, hh)
            hh.status = "active"
            hh.rejection_reason = ""
            hh.accepted_at = timezone.now()
            hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])
            send_happy_hour_notification_emails(hh)
        count += len(standalone_pending_hhs)

        skipped_msg = f" ({skipped_duplicates} flagged duplicate(s) held for manual review)" if skipped_duplicates > 0 else ""
        return Response({
            "success": True,
            "message": f"{count} pending deals approved{skipped_msg}",
            "skipped_duplicates_count": skipped_duplicates,
        })


class AdminDeleteDealView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            deal.delete()
            return Response({"success": True, "message": "Deal deleted"})
        except (Deal.DoesNotExist, ValueError):
            from happy_hours.models import HappyHour
            hh_pk = int(str(pk).replace("hh-", "")) if str(pk).startswith("hh-") or str(pk).isdigit() else None
            if hh_pk:
                try:
                    hh = HappyHour.objects.select_related("restaurant").get(pk=hh_pk, is_deal=True)
                    if request.user.is_employee_admin and hh.restaurant.registered_by_id != request.user.id:
                        return Response(
                            {"success": False, "message": "Permission denied."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    hh.delete()
                    return Response({"success": True, "message": "Happy Hour Deal deleted"})
                except HappyHour.DoesNotExist:
                    pass
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


class AdminDismissDealDuplicateView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            deal.is_potential_duplicate = False
            deal.duplicate_reasons = []
            deal.duplicate_score = 0.0
            deal.save(update_fields=["is_potential_duplicate", "duplicate_reasons", "duplicate_score"])

            return Response({
                "success": True,
                "message": f"Duplicate flag dismissed for '{deal.title}'.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            })
        except Deal.DoesNotExist:
            from happy_hours.models import HappyHour
            try:
                hh = HappyHour.objects.select_related("restaurant").get(pk=pk, is_deal=True)
                if request.user.is_employee_admin and hh.restaurant and hh.restaurant.registered_by_id != request.user.id:
                    return Response(
                        {"success": False, "message": "Permission denied."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                hh.is_potential_duplicate = False
                hh.duplicate_reasons = []
                hh.duplicate_score = 0.0
                hh.save(update_fields=["is_potential_duplicate", "duplicate_reasons", "duplicate_score"])
                return Response({
                    "success": True,
                    "message": f"Duplicate flag dismissed for '{hh.title}'.",
                    "data": {"id": hh.id, "is_potential_duplicate": False},
                })
            except HappyHour.DoesNotExist:
                return Response(
                    {"success": False, "message": "Deal not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )


class AdminDismissInaccuracyView(APIView):
    """
    Allows Admin to review reported inaccurate deals and dismiss the report flag
    after verifying or updating details.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            deal = Deal.objects.select_related("restaurant").get(pk=pk)
            if request.user.is_employee_admin and deal.restaurant.registered_by_id != request.user.id:
                return Response(
                    {"success": False, "message": "Permission denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            deal.is_reported_inaccurate = False
            deal.inaccurate_votes_count = 0
            deal.dislikes_count = 0
            deal.save(update_fields=["is_reported_inaccurate", "inaccurate_votes_count", "dislikes_count"])
            DealAccuracyVote.objects.filter(deal=deal, is_accurate=False).delete()
            DealVote.objects.filter(deal=deal, vote_type="dislike").delete()

            return Response({
                "success": True,
                "message": f"Inaccuracy reports cleared for '{deal.title}'. Deal marked as accurate.",
                "data": DealListSerializer(deal, context={"request": request}).data,
            })
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found."},
                status=status.HTTP_404_NOT_FOUND,
            )


class AdminCheckDealDuplicatesView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        from .duplicate_detector import detect_deal_duplicates, detect_happy_hour_duplicates
        from happy_hours.models import HappyHour
        import logging
        logger = logging.getLogger(__name__)

        deals_qs = Deal.objects.filter(status__in=["active", "pending"]).order_by("id")
        if request.user.is_employee_admin:
            deals_qs = deals_qs.filter(restaurant__registered_by=request.user)

        flagged_deals = 0
        for deal in deals_qs:
            try:
                is_dup, match_deal, score, reasons = detect_deal_duplicates(deal)
                if is_dup and match_deal:
                    deal.is_potential_duplicate = True
                    deal.duplicate_of = match_deal
                    deal.duplicate_score = score
                    deal.duplicate_reasons = reasons
                    deal.save(update_fields=[
                        "is_potential_duplicate",
                        "duplicate_of",
                        "duplicate_score",
                        "duplicate_reasons",
                    ])
                    flagged_deals += 1
            except Exception as e:
                logger.warning(f"Error checking duplicate for Deal #{deal.id}: {e}")

        # Also scan standalone happy hour deals
        hh_qs = HappyHour.objects.filter(is_deal=True, status__in=["active", "upcoming", "pending"]).order_by("id")
        if request.user.is_employee_admin:
            hh_qs = hh_qs.filter(restaurant__registered_by=request.user)

        flagged_hhs = 0
        for hh in hh_qs:
            try:
                is_dup, match_hh, score, reasons = detect_happy_hour_duplicates(hh)
                if is_dup and match_hh:
                    hh.is_potential_duplicate = True
                    hh.duplicate_of = match_hh
                    hh.duplicate_score = score
                    hh.duplicate_reasons = reasons
                    hh.save(update_fields=[
                        "is_potential_duplicate",
                        "duplicate_of",
                        "duplicate_score",
                        "duplicate_reasons",
                    ])
                    flagged_hhs += 1
            except Exception as e:
                logger.warning(f"Error checking duplicate for HH #{hh.id}: {e}")

        total_flagged = flagged_deals + flagged_hhs
        return Response({
            "success": True,
            "message": f"Duplicate scan complete. {total_flagged} potential duplicate(s) detected.",
            "flagged_deals": flagged_deals,
            "flagged_happy_hours": flagged_hhs,
            "total_flagged": total_flagged,
        })
