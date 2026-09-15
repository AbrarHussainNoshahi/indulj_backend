from django.utils import timezone
from rest_framework import status
from notifications.utils import create_notification, notify_admins, check_and_expire_happy_hours
from notifications.email_service import send_happy_hour_notification_emails
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsRestaurant, IsUser
from restaurants.models import Restaurant

from .models import HappyHour
from .serializers import (
    AdminUpdateHappyHourSerializer,
    CreateHappyHourSerializer,
    HappyHourDetailSerializer,
    HappyHourListSerializer,
    PlanHappyHourSerializer,
    RejectHappyHourSerializer,
    RestaurantResponseSerializer,
)


class PublicHappyHourListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        check_and_expire_happy_hours()
        qs = HappyHour.objects.filter(
            status__in=["active", "upcoming"],
            is_public=True,
            restaurant__status="active",
        ).select_related("restaurant", "submitted_by")

        restaurant_id = request.query_params.get("restaurant")
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        vibe = request.query_params.get("vibe")
        if vibe:
            qs = qs.filter(vibe=vibe)

        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        is_featured = request.query_params.get("is_featured")
        if is_featured in ["true", "1", "yes"]:
            qs = qs.filter(is_featured=True)

        serializer = HappyHourListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class PublicHappyHourDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        check_and_expire_happy_hours()
        try:
            happy_hour = HappyHour.objects.select_related(
                "restaurant",
                "submitted_by",
            ).get(pk=pk)
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Visible if active/upcoming & public & active restaurant,
        # OR if requested by creator, restaurant owner, or admin
        is_public_viewable = (
            happy_hour.status in ["active", "upcoming"]
            and happy_hour.is_public
            and getattr(happy_hour.restaurant, "status", None) == "active"
        )
        is_authorized = (
            request.user.is_authenticated
            and (
                happy_hour.submitted_by_id == request.user.id
                or getattr(happy_hour.restaurant, "owner_id", None) == request.user.id
                or getattr(request.user, "role", None) == "admin"
                or request.user.is_staff
            )
        )

        if not (is_public_viewable or is_authorized):
            return Response(
                {"success": False, "message": "Happy hour not found or awaiting approval."},
                status=status.HTTP_404_NOT_FOUND,
            )

        happy_hour.views_count += 1
        happy_hour.save(update_fields=["views_count"])

        return Response({
            "success": True,
            "data": HappyHourDetailSerializer(
                happy_hour,
                context={"request": request},
            ).data,
        })


class MapHappyHoursView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = HappyHour.objects.filter(
            status__in=["active", "upcoming"],
            is_public=True,
            restaurant__status="active",
            restaurant__latitude__isnull=False,
            restaurant__longitude__isnull=False,
        ).select_related("restaurant")

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(restaurant__city__icontains=city)

        data = [
            {
                "id": item.id,
                "title": item.title,
                "restaurant_name": item.restaurant.name,
                "latitude": item.restaurant.latitude,
                "longitude": item.restaurant.longitude,
                "date": item.date,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "is_featured": item.is_featured,
                "vibe": item.vibe,
            }
            for item in qs
        ]

        return Response({"success": True, "data": data})


class PlanHappyHourView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = PlanHappyHourSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        # Resolve restaurant
        rest_input = data.get("restaurant") or data.get("restaurant_name") or data.get("location")
        restaurant = None

        if rest_input:
            if str(rest_input).isdigit():
                restaurant = Restaurant.objects.filter(pk=int(rest_input), status="active").first()
            if not restaurant:
                restaurant = Restaurant.objects.filter(name__icontains=str(rest_input), status="active").first()

        if not restaurant:
            restaurant = Restaurant.objects.filter(status="active").first()

        if not restaurant:
            restaurant = Restaurant.objects.create(
                name=str(rest_input) if rest_input else "Partner Restaurant",
                city=data.get("location") or "New York",
                status="active",
                operating_hours={"open": "09:00", "close": "23:00"}
            )

        # Check / set operating hours
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            restaurant.operating_hours = {"open": "09:00", "close": "23:00"}
            restaurant.save(update_fields=["operating_hours"])

        date_val = data.get("date") or timezone.localdate()
        title_val = data.get("title") or f"{restaurant.name} Happy Hour"
        start_time_val = data.get("start_time") or "17:00:00"
        end_time_val = data.get("end_time") or "20:00:00"

        happy_hour = HappyHour.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="user",
            title=title_val,
            description=data.get("description", ""),
            event_type=data.get("event_type", "casual"),
            group_size=data.get("group_size", 1),
            start_time=start_time_val,
            end_time=end_time_val,
            date=date_val,
            vibe=data.get("vibe", "casual"),
            location=data.get("location", ""),
            phone_number=data.get("phone_number", ""),
            is_public=data.get("is_public", True),
            image=data.get("image"),
            specials=data.get("specials", []),
            status="pending",
        )

        # Also create deal if requested
        raw_also = request.data.get("also_add_to_deals")
        also_add_deals = data.get("also_add_to_deals") or (raw_also in [True, "true", "True", "1", 1])

        if also_add_deals:
            try:
                from deals.models import Deal
                day_name = date_val.strftime("%A").lower() if hasattr(date_val, "strftime") else "everyday"
                valid_days = [c[0] for c in Deal.DAY_CHOICES]
                if day_name not in valid_days:
                    day_name = "everyday"

                price_val = data.get("price") or request.data.get("price") or 0.00
                Deal.objects.create(
                    restaurant=restaurant,
                    submitted_by=request.user,
                    created_by_role="user",
                    title=f"{title_val}",
                    description=data.get("description") or f"Happy Hour Special: {title_val}",
                    food_type="other",
                    price=price_val,
                    day_of_week=day_name,
                    has_time_slots=True,
                    start_time=start_time_val,
                    end_time=end_time_val,
                    image=data.get("image"),
                    location_branch=data.get("location", ""),
                    status="pending",
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to auto-create deal from happy hour: {e}")

        try:
            self._notify_restaurant(happy_hour)
        except Exception:
            pass

        return Response(
            {
                "success": True,
                "message": "Happy hour planned! Restaurant has been notified." if not also_add_deals else "Happy hour and Deal created successfully! Restaurant has been notified.",
                "data": HappyHourListSerializer(
                    happy_hour,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _notify_restaurant(self, happy_hour):
        if happy_hour.submitted_by:
            create_notification(
                user=happy_hour.submitted_by,
                type="happy_hour",
                title="Happy Hour Request Submitted",
                message=f"Your request for '{happy_hour.title}' at {happy_hour.restaurant.name} has been submitted for review.",
                related_happy_hour=happy_hour,
            )
        if happy_hour.restaurant and happy_hour.restaurant.owner and happy_hour.restaurant.owner != happy_hour.submitted_by:
            create_notification(
                user=happy_hour.restaurant.owner,
                type="happy_hour",
                title="New Happy Hour Request",
                message=f"{happy_hour.submitted_by.full_name} wants to plan {happy_hour.title} for {happy_hour.group_size} people.",
                related_happy_hour=happy_hour,
            )
        notify_admins(
            type="happy_hour",
            title="New Happy Hour Request",
            message=f"{happy_hour.submitted_by.full_name} wants to plan {happy_hour.title} for {happy_hour.group_size} people.",
            related_happy_hour=happy_hour,
        )

class MyHappyHoursView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def get(self, request):
        check_and_expire_happy_hours()
        qs = HappyHour.objects.filter(
            submitted_by=request.user,
        ).select_related("restaurant")

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        serializer = HappyHourListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response({"success": True, "data": serializer.data})


class DeleteMyHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def delete(self, request, pk):
        try:
            happy_hour = HappyHour.objects.get(
                pk=pk,
                submitted_by=request.user,
                created_by_role="user",
            )
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if happy_hour.status in ["active", "upcoming"]:
            return Response(
                {
                    "success": False,
                    "message": "Accepted happy hours cannot be deleted by user.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        happy_hour.delete()
        return Response({"success": True, "message": "Happy hour deleted"})

class CancelMyHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsUser]

    def post(self, request, pk):
        try:
            hh = HappyHour.objects.get(pk=pk, submitted_by=request.user)

            if hh.status != "pending":
                return Response({
                    "success": False,
                    "message": "Only pending happy hours can be cancelled"
                }, status=400)

            hh.status = "cancelled"
            hh.save()

            create_notification(
                user=hh.restaurant.owner,
                type="happy_hour",
                title="Happy Hour Cancelled",
                message=f"{request.user.full_name} cancelled their happy hour request.",
                related_happy_hour=hh,
            )

            return Response({
                "success": True,
                "message": "Happy hour cancelled successfully"
            })

        except HappyHour.DoesNotExist:
            return Response({
                "success": False,
                "message": "Not found"
            }, status=404)


class RestaurantHappyHourListView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def get(self, request):
        check_and_expire_happy_hours()
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {"success": False, "message": "Restaurant not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        qs = HappyHour.objects.filter(
            restaurant=restaurant,
        ).select_related("submitted_by")

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        serializer = HappyHourListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class RestaurantCreateHappyHourView(APIView):
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
                    "message": "Please set your restaurant's operating hours in your profile settings before creating a happy hour."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateHappyHourSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        happy_hour = serializer.save(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="restaurant",
        )

        if not happy_hour.status:
            happy_hour.status = "active"
            happy_hour.save(update_fields=["status"])

        if happy_hour.is_public and happy_hour.status in ["active", "upcoming"]:
            send_happy_hour_notification_emails(happy_hour)

        return Response(
            {
                "success": True,
                "message": "Happy hour created.",
                "data": HappyHourListSerializer(
                    happy_hour,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RestaurantUpdateDeleteHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_item(self, pk, user):
        try:
            return HappyHour.objects.get(
                pk=pk,
                restaurant__owner=user,
                created_by_role="restaurant",
            )
        except HappyHour.DoesNotExist:
            return None

    def put(self, request, pk):
        happy_hour = self.get_item(pk, request.user)

        if not happy_hour:
            return Response(
                {
                    "success": False,
                    "message": "Happy hour not found or cannot edit user request.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = happy_hour.restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "Please set your restaurant's operating hours in your profile settings before creating/updating a happy hour."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CreateHappyHourSerializer(
            happy_hour,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response({
                "success": True,
                "message": "Happy hour updated.",
                "data": HappyHourListSerializer(
                    happy_hour,
                    context={"request": request},
                ).data,
            })

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):
        happy_hour = self.get_item(pk, request.user)

        if not happy_hour:
            return Response(
                {
                    "success": False,
                    "message": "Happy hour not found or cannot delete user request.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        happy_hour.delete()
        return Response({"success": True, "message": "Happy hour deleted"})


class RestaurantAcceptHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def post(self, request, pk):
        try:
            happy_hour = HappyHour.objects.get(
                pk=pk,
                restaurant__owner=request.user,
                status="pending",
                created_by_role="user",
            )
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found or not pending"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = happy_hour.restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "Please set your restaurant's operating hours in your profile settings before accepting a happy hour."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RestaurantResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        happy_hour.status = "upcoming"
        happy_hour.restaurant_response = serializer.validated_data.get("response", "")
        happy_hour.accepted_at = timezone.now()
        happy_hour.rejection_reason = ""
        happy_hour.save(
            update_fields=[
                "status",
                "restaurant_response",
                "accepted_at",
                "rejection_reason",
            ]
        )

        if happy_hour.submitted_by:
            create_notification(
                user=happy_hour.submitted_by,
                type="happy_hour",
                title="Happy Hour Accepted",
                message=f"{happy_hour.restaurant.name} accepted your happy hour request.",
                related_happy_hour=happy_hour,
            )

        notify_admins(
            type="happy_hour",
            title="Happy Hour Accepted by Restaurant",
            message=f"{happy_hour.restaurant.name} accepted happy hour '{happy_hour.title}'.",
            related_happy_hour=happy_hour,
        )

        if happy_hour.is_public and happy_hour.status in ["active", "upcoming"]:
            send_happy_hour_notification_emails(happy_hour)

        return Response({
            "success": True,
            "message": "Happy hour accepted.",
            "data": HappyHourListSerializer(
                happy_hour,
                context={"request": request},
            ).data,
        })


class RestaurantRejectHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def post(self, request, pk):
        try:
            happy_hour = HappyHour.objects.get(
                pk=pk,
                restaurant__owner=request.user,
                status="pending",
                created_by_role="user",
            )
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found or not pending"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RejectHappyHourSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        happy_hour.status = "rejected"
        happy_hour.rejection_reason = serializer.validated_data["rejection_reason"]
        happy_hour.rejected_at = timezone.now()
        happy_hour.save(update_fields=["status", "rejection_reason", "rejected_at"])

        if happy_hour.submitted_by:
            create_notification(
                user=happy_hour.submitted_by,
                type="happy_hour",
                title="Happy Hour Rejected",
                message=f"{happy_hour.restaurant.name} rejected your happy hour request. Reason: {happy_hour.rejection_reason}",
                related_happy_hour=happy_hour,
            )

        notify_admins(
            type="happy_hour",
            title="Happy Hour Rejected by Restaurant",
            message=f"{happy_hour.restaurant.name} rejected happy hour '{happy_hour.title}'.",
            related_happy_hour=happy_hour,
        )

        return Response({
            "success": True,
            "message": "Happy hour rejected.",
            "data": HappyHourListSerializer(
                happy_hour,
                context={"request": request},
            ).data,
        })


class RestaurantAcceptAllHappyHoursView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

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
                    "message": "Please set your restaurant's operating hours in your profile settings before accepting happy hours."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        pending = list(HappyHour.objects.filter(
            restaurant=restaurant,
            status="pending",
            created_by_role="user",
        ))

        count = len(pending)
        HappyHour.objects.filter(id__in=[h.id for h in pending]).update(status="upcoming", accepted_at=timezone.now())

        for hh in pending:
            hh.status = "upcoming"
            if hh.is_public:
                send_happy_hour_notification_emails(hh)

        return Response({
            "success": True,
            "message": f"{count} happy hours accepted",
        })


class AdminHappyHourListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        check_and_expire_happy_hours()
        qs = HappyHour.objects.select_related("restaurant", "submitted_by").all()

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        restaurant = request.query_params.get("restaurant")
        if restaurant:
            qs = qs.filter(restaurant_id=restaurant)

        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        serializer = HappyHourListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response({
            "success": True,
            "count": qs.count(),
            "data": serializer.data,
        })


class AdminHappyHourDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk):
        try:
            return HappyHour.objects.select_related("restaurant", "submitted_by").get(pk=pk)
        except HappyHour.DoesNotExist:
            return None

    def get(self, request, pk):
        happy_hour = self.get_object(pk)

        if not happy_hour:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "success": True,
            "data": HappyHourDetailSerializer(
                happy_hour,
                context={"request": request},
            ).data,
        })

    def put(self, request, pk):
        happy_hour = self.get_object(pk)

        if not happy_hour:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        restaurant = happy_hour.restaurant
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": f"Restaurant '{restaurant.name}' has not configured its operating hours yet. Happy hours cannot be updated for it."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminUpdateHappyHourSerializer(
            happy_hour,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response({
                "success": True,
                "message": "Happy hour updated.",
                "data": HappyHourDetailSerializer(
                    happy_hour,
                    context={"request": request},
                ).data,
            })

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):
        happy_hour = self.get_object(pk)

        if not happy_hour:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        happy_hour.delete()

        return Response({"success": True, "message": "Happy hour deleted"})


class AdminAcceptHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            happy_hour = HappyHour.objects.select_related("restaurant", "submitted_by", "restaurant__owner").get(pk=pk)
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        restaurant = happy_hour.restaurant
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": f"Restaurant '{restaurant.name}' has not configured its operating hours yet. Happy hours cannot be approved for it."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
        target_date = happy_hour.date or now.date()
        target_status = "upcoming"
        if happy_hour.start_time and happy_hour.end_time:
            if target_date == now.date():
                if happy_hour.start_time <= now.time() < happy_hour.end_time:
                    target_status = "active"
                elif now.time() >= happy_hour.end_time:
                    target_status = "expired"

        happy_hour.status = target_status
        happy_hour.accepted_at = timezone.now()
        happy_hour.rejection_reason = ""
        happy_hour.save(update_fields=["status", "accepted_at", "rejection_reason"])

        # Notify creator user and award points
        if happy_hour.submitted_by:
            create_notification(
                user=happy_hour.submitted_by,
                type="happy_hour",
                title="Happy Hour Approved! 🎉",
                message=f"Your happy hour '{happy_hour.title}' at {happy_hour.restaurant.name} has been approved.",
                related_happy_hour=happy_hour,
            )
            try:
                from accounts.models import PointsTransaction
                submitter = happy_hour.submitted_by
                submitter.points = (submitter.points or 0) + 50
                submitter.save(update_fields=["points"])
                PointsTransaction.objects.create(
                    user=submitter,
                    text=f"Happy hour approved - {happy_hour.title}",
                    status="approved",
                    points=50,
                )
            except Exception:
                pass

        # Notify restaurant owner if different from submitter
        if happy_hour.restaurant.owner and happy_hour.restaurant.owner != happy_hour.submitted_by:
            create_notification(
                user=happy_hour.restaurant.owner,
                type="happy_hour",
                title="Happy Hour Approved",
                message=f"Happy hour '{happy_hour.title}' has been approved by admin.",
                related_happy_hour=happy_hour,
            )

        if happy_hour.is_public and happy_hour.status in ["active", "upcoming"]:
            send_happy_hour_notification_emails(happy_hour)

        return Response({
            "success": True,
            "message": "Happy hour accepted by admin.",
        })


class AdminRejectHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            happy_hour = HappyHour.objects.select_related("restaurant", "submitted_by", "restaurant__owner").get(pk=pk)
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RejectHappyHourSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        happy_hour.status = "rejected"
        happy_hour.rejection_reason = serializer.validated_data["rejection_reason"]
        happy_hour.rejected_at = timezone.now()
        happy_hour.save(update_fields=["status", "rejection_reason", "rejected_at"])

        if happy_hour.submitted_by:
            create_notification(
                user=happy_hour.submitted_by,
                type="happy_hour",
                title="Happy Hour Rejected",
                message=f"Your happy hour '{happy_hour.title}' was rejected by admin. Reason: {happy_hour.rejection_reason}",
                related_happy_hour=happy_hour,
            )

        if happy_hour.restaurant.owner and happy_hour.restaurant.owner != happy_hour.submitted_by:
            create_notification(
                user=happy_hour.restaurant.owner,
                type="happy_hour",
                title="Happy Hour Rejected",
                message=f"Happy hour '{happy_hour.title}' was rejected by admin. Reason: {happy_hour.rejection_reason}",
                related_happy_hour=happy_hour,
            )

        return Response({
            "success": True,
            "message": "Happy hour rejected by admin.",
        })


class AdminAcceptAllHappyHoursView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        pending = HappyHour.objects.filter(status="pending").select_related("restaurant", "submitted_by", "restaurant__owner")
        count = 0
        now = timezone.localtime(timezone.now()) if timezone.is_aware(timezone.now()) else timezone.now()
        for hh in pending:
            restaurant = hh.restaurant
            operating_hours = restaurant.operating_hours
            if operating_hours and isinstance(operating_hours, dict) and (operating_hours.get("open") or operating_hours.get("opening_time")) and (operating_hours.get("close") or operating_hours.get("closing_time")):
                target_date = hh.date or now.date()
                target_status = "upcoming"
                if hh.start_time and hh.end_time and target_date == now.date():
                    if hh.start_time <= now.time() < hh.end_time:
                        target_status = "active"
                    elif now.time() >= hh.end_time:
                        target_status = "expired"

                hh.status = target_status
                hh.accepted_at = timezone.now()
                hh.rejection_reason = ""
                hh.save(update_fields=["status", "accepted_at", "rejection_reason"])
                count += 1

                if hh.submitted_by:
                    create_notification(
                        user=hh.submitted_by,
                        type="happy_hour",
                        title="Happy Hour Approved! 🎉",
                        message=f"Your happy hour '{hh.title}' at {hh.restaurant.name} has been approved.",
                        related_happy_hour=hh,
                    )
                    try:
                        from accounts.models import PointsTransaction
                        submitter = hh.submitted_by
                        submitter.points = (submitter.points or 0) + 50
                        submitter.save(update_fields=["points"])
                        PointsTransaction.objects.create(
                            user=submitter,
                            text=f"Happy hour approved - {hh.title}",
                            status="approved",
                            points=50,
                        )
                    except Exception:
                        pass

                if hh.restaurant.owner and hh.restaurant.owner != hh.submitted_by:
                    create_notification(
                        user=hh.restaurant.owner,
                        type="happy_hour",
                        title="Happy Hour Approved",
                        message=f"Happy hour '{hh.title}' has been approved by admin.",
                        related_happy_hour=hh,
                    )

                if hh.is_public and hh.status in ["active", "upcoming"]:
                    send_happy_hour_notification_emails(hh)

        return Response({
            "success": True,
            "message": f"{count} happy hours accepted",
        })