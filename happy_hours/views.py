from django.utils import timezone
from rest_framework import status
from notifications.utils import create_notification, notify_admins, check_and_expire_happy_hours
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
        try:
            happy_hour = HappyHour.objects.select_related(
                "restaurant",
                "submitted_by",
            ).get(
                pk=pk,
                status__in=["active", "upcoming"],
                is_public=True,
                restaurant__status="active",
            )
        except HappyHour.DoesNotExist:
            return Response(
                {"success": False, "message": "Happy hour not found"},
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
    permission_classes = [IsAuthenticated, IsUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = PlanHappyHourSerializer(data=request.data)
        print("REQUEST DATA:", request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        try:
            restaurant = Restaurant.objects.get(
                pk=data["restaurant"],
                status="active",
            )
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if restaurant operating hours are set
        operating_hours = restaurant.operating_hours
        if not operating_hours or not isinstance(operating_hours, dict) or not (operating_hours.get("open") or operating_hours.get("opening_time")) or not (operating_hours.get("close") or operating_hours.get("closing_time")):
            return Response(
                {
                    "success": False,
                    "message": "This restaurant has not configured its operating hours yet. Happy hours cannot be created for it."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        happy_hour = HappyHour.objects.create(
            restaurant=restaurant,
            submitted_by=request.user,
            created_by_role="user",

            title=data["title"],
            description=data.get("description", ""),

            event_type=data["event_type"],
            group_size=data["group_size"],

            start_time=data["start_time"],
            end_time=data["end_time"],
            date=data["date"],

            vibe=data["vibe"],
            location=data.get("location", ""),
            phone_number=data.get("phone_number", ""),

            is_public=data["is_public"],
            image=data.get("image"),
            specials=data.get("specials", []),

            status="pending",
        )

        self._notify_restaurant(happy_hour)

        return Response(
            {
                "success": True,
                "message": "Happy hour planned! Restaurant has been notified.",
                "data": HappyHourListSerializer(
                    happy_hour,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _notify_restaurant(self, happy_hour):
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

        pending = HappyHour.objects.filter(
            restaurant=restaurant,
            status="pending",
            created_by_role="user",
        )

        count = pending.count()
        pending.update(status="upcoming", accepted_at=timezone.now())

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
            happy_hour = HappyHour.objects.get(pk=pk)
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

        happy_hour.status = "upcoming"
        happy_hour.accepted_at = timezone.now()
        happy_hour.rejection_reason = ""
        happy_hour.save(update_fields=["status", "accepted_at", "rejection_reason"])

        return Response({
            "success": True,
            "message": "Happy hour accepted by admin.",
        })


class AdminRejectHappyHourView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            happy_hour = HappyHour.objects.get(pk=pk)
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

        return Response({
            "success": True,
            "message": "Happy hour rejected by admin.",
        })


class AdminAcceptAllHappyHoursView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        pending = HappyHour.objects.filter(status="pending").select_related("restaurant")
        count = 0
        for hh in pending:
            restaurant = hh.restaurant
            operating_hours = restaurant.operating_hours
            if operating_hours and isinstance(operating_hours, dict) and (operating_hours.get("open") or operating_hours.get("opening_time")) and (operating_hours.get("close") or operating_hours.get("closing_time")):
                hh.status = "upcoming"
                hh.accepted_at = timezone.now()
                hh.rejection_reason = ""
                hh.save(update_fields=["status", "accepted_at", "rejection_reason"])
                count += 1

        return Response({
            "success": True,
            "message": f"{count} happy hours accepted",
        })