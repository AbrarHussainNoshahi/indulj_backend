
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
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsRestaurant, IsUser
from restaurants.models import Restaurant

from .models import Deal, SavedDeal, DealView
from .serializers import (
    DealListSerializer,
    DealDetailSerializer,
    SubmitDealSerializer,
    CreateDealSerializer,
    RejectDealSerializer,
    SavedDealSerializer,
    AdminCreateDealSerializer,
)

from django.utils import timezone
from datetime import timedelta
from notifications.utils import create_notification, notify_admins
from notifications.email_service import (
    send_deal_notification_emails,
    send_happy_hour_notification_emails,
    send_deal_planned_email,
)


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

    # Enforce: "Each restaurant should have only one active Happy Hour Deal at a time."
    if status_val == "active":
        HappyHour.objects.filter(
            restaurant=restaurant,
            is_deal=True,
            status="active"
        ).update(status="expired")

    hh_date = data.get("hh_date") or None

    hh = HappyHour.objects.create(
        deal=deal,
        is_deal=True,
        restaurant=restaurant,
        submitted_by=user,
        created_by_role=role,
        title=deal.title,
        description=deal.description or "",
        group_size=int(data.get("hh_group_size") or 1),
        event_type=hh_event,
        vibe=hh_vibe,
        date=hh_date,
        start_time=s_time,
        end_time=e_time,
        days_of_week=[deal.day_of_week] if getattr(deal, "day_of_week", None) else ["everyday"],
        location=data.get("location_branch") or getattr(deal, "location_branch", "") or restaurant.address or restaurant.city or "",
        discount_offer=hh_discount,
        status=status_val,
        is_public=True,
        image=happy_hour_image,
    )

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
            qs = qs.filter(title__icontains=search)

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
        qs = Deal.objects.filter(
            status="active",
            restaurant__status="active",
            restaurant__latitude__isnull=False,
            restaurant__longitude__isnull=False,
        ).select_related("restaurant")

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
                "restaurant_name": deal.restaurant.name,
                "latitude": deal.restaurant.latitude,
                "longitude": deal.restaurant.longitude,
                "is_hot_deal": deal.is_hot_deal,
                "price": str(deal.price),
                "food_type": deal.food_type,
                "day_of_week": deal.day_of_week,
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
        serializer = SubmitDealSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        restaurant_name = data.get("restaurant_name") or data.get("location_branch")
        restaurant = None

        if restaurant_name:
            restaurant = Restaurant.objects.filter(name__iexact=restaurant_name, status="active").first()
            if not restaurant:
                restaurant = Restaurant.objects.filter(name__icontains=restaurant_name, status="active").first()

        if not restaurant:
            restaurant = Restaurant.objects.create(
                name=restaurant_name or "Partner Restaurant",
                city=data.get("location_branch") or "New York",
                address=data.get("location_branch") or "",
                status="active",
                operating_hours={"open": "09:00", "close": "23:00"}
            )

        # Check / set operating hours
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            restaurant.operating_hours = {"open": "09:00", "close": "23:00"}
            restaurant.save(update_fields=["operating_hours"])

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="user",
            title=data.get("title") or f"{restaurant.name} Deal",
            description=data.get("description"),
            price=data.get("price"),
            food_type=normalize_food_type_input(request.data.get("food_type") or data.get("food_type")),
            day_of_week=data.get("day_of_week"),
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=data.get("location_branch", ""),
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

        raw_post_hh = request.data.get("post_to_happy_hour")
        post_to_hh = data.get("post_to_happy_hour") or (raw_post_hh in [True, "true", "True", "1", 1])
        if post_to_hh:
            create_linked_happy_hour_from_deal(
                deal=deal,
                restaurant=restaurant,
                user=request.user,
                role="user",
                data=request.data,
                is_approved=False
            )

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

        try:
            send_deal_planned_email(deal)
        except Exception as err:
            import logging
            logging.getLogger(__name__).error(f"Failed to dispatch deal email: {err}")

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
    permission_classes = [IsAuthenticated, IsUser]

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

        if not created:
            return Response(
                {"success": False, "message": "Deal already saved"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"success": True, "message": "Deal saved"},
            status=status.HTTP_201_CREATED,
        )


class UnsaveDealView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def delete(self, request, pk):
        try:
            saved = SavedDeal.objects.get(user=request.user, deal_id=pk)
        except SavedDeal.DoesNotExist:
            return Response(
                {"success": False, "message": "Saved deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        saved.delete()
        return Response({"success": True, "message": "Deal unsaved"})


class SavedDealsView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

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

        qs = Deal.objects.filter(restaurant=restaurant).select_related("submitted_by")

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

        req_data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'food_type' in req_data:
            req_data['food_type'] = normalize_food_type_input(req_data['food_type'])
        serializer = CreateDealSerializer(data=req_data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deal = serializer.save(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="restaurant",
            status="active",
        )

        raw_post_hh = request.data.get("post_to_happy_hour")
        if raw_post_hh in [True, "true", "True", "1", 1]:
            create_linked_happy_hour_from_deal(
                deal=deal,
                restaurant=restaurant,
                user=request.user,
                role="restaurant",
                data=request.data,
                is_approved=True
            )

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

        req_data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'food_type' in req_data:
            req_data['food_type'] = normalize_food_type_input(req_data['food_type'])
        serializer = CreateDealSerializer(deal, data=req_data, partial=True)

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
            HappyHour.objects.filter(
                restaurant=deal.restaurant,
                is_deal=True,
                status="active"
            ).exclude(pk=hh.pk).update(status="expired")
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
        serializer = AdminCreateDealSerializer(data=request.data)

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

        if restaurant and request.user.is_employee_admin and restaurant.registered_by_id != request.user.id:
            return Response(
                {"success": False, "message": "Permission denied. You can only create deals for restaurants registered under your reference."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not restaurant:
            restaurant = Restaurant.objects.create(
                name=restaurant_name,
                city=data.get("location_branch") or "New York",
                address=data.get("location_branch") or "",
                status="active",
                operating_hours={"open": "09:00", "close": "23:00"},
                registered_by=request.user if request.user.is_employee_admin else None
            )

        # Check / set operating hours
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            restaurant.operating_hours = {"open": "09:00", "close": "23:00"}
            restaurant.save(update_fields=["operating_hours"])

        deal = Deal.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="admin",
            title=data["title"],
            description=data["description"],
            price=data["price"],
            food_type=normalize_food_type_input(request.data.get("food_type") or data.get("food_type")),
            day_of_week=data["day_of_week"],
            has_time_slots=data.get("has_time_slots", False),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            location_branch=data.get("location_branch", ""),
            discount_percentage=data.get("discount_percentage", ""),
            image=data.get("image"),
            is_hot_deal=data.get("is_hot_deal", False),
            expires_at=data.get("expires_at"),
            status=data.get("status", "active"),
        )

        post_to_happy_hour = data.get("post_to_happy_hour", False) or (request.data.get("post_to_happy_hour") in [True, "true", "True", "1", 1])
        if post_to_happy_hour:
            hh = create_linked_happy_hour_from_deal(
                deal=deal,
                restaurant=restaurant,
                user=request.user,
                role="admin",
                data=request.data if hasattr(request, "data") else data,
                is_approved=(deal.status == "active")
            )




        if deal.status == "active":
            send_deal_notification_emails(deal)

        return Response(
            {
                "success": True,
                "message": "Deal created successfully." if not post_to_happy_hour else "Deal and Happy Hour created successfully.",
                "data": DealListSerializer(
                    deal,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminDealListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = Deal.objects.select_related("restaurant", "submitted_by").filter(restaurant__status="active")

        if request.user.is_employee_admin:
            qs = qs.filter(restaurant__registered_by=request.user)
        elif request.user.is_super_admin:
            registered_by_param = request.query_params.get("registered_by")
            if registered_by_param:
                qs = qs.filter(restaurant__registered_by_id=registered_by_param)

        status_filter = request.query_params.get("status")
        if status_filter == "duplicates" or request.query_params.get("duplicates") in ["true", "1"]:
            qs = qs.filter(is_potential_duplicate=True)
        elif status_filter and status_filter != "all":
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
            HappyHour.objects.filter(
                restaurant=deal.restaurant,
                is_deal=True,
                status="active"
            ).exclude(pk=hh.pk).update(status="expired")
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
        except Deal.DoesNotExist:
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
                HappyHour.objects.filter(
                    restaurant=deal.restaurant,
                    is_deal=True,
                    status="active"
                ).exclude(pk=hh.pk).update(status="expired")
                hh.status = "active"
                hh.rejection_reason = ""
                hh.accepted_at = timezone.now()
                hh.save(update_fields=["status", "rejection_reason", "accepted_at", "updated_at"])
                send_happy_hour_notification_emails(hh)

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
        except Deal.DoesNotExist:
            return Response(
                {"success": False, "message": "Deal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        deal.delete()
        return Response({"success": True, "message": "Deal deleted"})